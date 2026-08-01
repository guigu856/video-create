"""以 LanceDB 单表保存原子知识、结构化元数据和正文向量。"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import lancedb  # type: ignore[import-untyped]
import pyarrow as pa  # type: ignore[import-untyped]
from filelock import FileLock
from filelock import Timeout as FileLockTimeout
from lancedb.index import Bitmap, BTree, LabelList  # type: ignore[import-untyped]
from pydantic import ValidationError

from video_create_plugin.errors import PluginError

from .embedding import MODEL_DIMENSION, LocalEmbeddingService
from .models import (
    ApplicableStage,
    KnowledgeSearchHit,
    KnowledgeSearchQuery,
    KnowledgeUnit,
    StoredKnowledgeUnit,
)

_TABLE_NAME = "knowledge_units"
_INDEX_OPTIMIZE_INTERVAL = 20
_LOGGER = logging.getLogger(__name__)
_LOCKS_GUARD = threading.Lock()
_WRITE_LOCKS: dict[Path, threading.RLock] = {}


class KnowledgeStore:
    def __init__(self, database_dir: Path) -> None:
        self._database_dir = database_dir.resolve()
        self._write_lock = _shared_lock(self._database_dir)
        self._process_lock = FileLock(str(self._database_dir / ".write.lock"), timeout=60)
        self._table_instance: Any | None = None
        self._modifications_since_optimization = 0

    @contextmanager
    def serialized_write(self) -> Iterator[None]:
        with self._write_lock:
            self._database_dir.mkdir(parents=True, exist_ok=True)
            with self._process_access():
                self._table_locked().checkout_latest()
                yield

    def merge(self, units: tuple[StoredKnowledgeUnit, ...]) -> None:
        if not units:
            return
        rows = [unit.model_dump(mode="json") for unit in units]
        table = self._table()
        table.merge_insert("knowledge_id").when_matched_update_all().when_not_matched_insert_all().execute(rows)
        self._modifications_since_optimization += 1
        optimized = _maintain_indices(
            table,
            optimize=self._modifications_since_optimization >= _INDEX_OPTIMIZE_INTERVAL,
        )
        if optimized:
            self._modifications_since_optimization = 0

    def repair_indices(self) -> None:
        if _maintain_indices(self._table()):
            self._modifications_since_optimization = 0

    def list_all(self) -> tuple[KnowledgeUnit, ...]:
        with self._refreshed_read() as table:
            units = tuple(_public(_stored(row)) for row in table.search().to_list())
        return tuple(sorted(units, key=lambda unit: unit.knowledge_id))

    def list_stored(self, *, where: str | None = None) -> tuple[StoredKnowledgeUnit, ...]:
        with self._refreshed_read() as table:
            query = table.search()
            if where is not None:
                query = query.where(where)
            units = tuple(_stored(row) for row in query.to_list())
        return tuple(sorted(units, key=lambda unit: unit.knowledge_id))

    def get(self, knowledge_id: str) -> KnowledgeUnit:
        return _public(self.get_stored(knowledge_id))

    def get_stored(self, knowledge_id: str) -> StoredKnowledgeUnit:
        unit = self.get_stored_optional(knowledge_id)
        if unit is None:
            raise KeyError(knowledge_id)
        return unit

    def get_stored_optional(self, knowledge_id: str) -> StoredKnowledgeUnit | None:
        with self._refreshed_read() as table:
            rows = (
                table.search()
                .where(f"knowledge_id = {_literal(knowledge_id)}")
                .limit(2)
                .to_list()
            )
        if not rows:
            return None
        if len(rows) != 1:
            raise PluginError("knowledge_store_invalid", "知识 ID 在数据库中不唯一")
        return _stored(rows[0])

    def archive(self, knowledge_id: str) -> KnowledgeUnit:
        with self.serialized_write():
            unit = self.get_stored(knowledge_id)
            archived = unit.model_copy(
                update={"status": "archived", "updated_at_us": time.time_ns() // 1000}
            )
            self.merge((archived,))
            return _public(archived)

    def active_for_stage(self, stage: ApplicableStage) -> tuple[KnowledgeUnit, ...]:
        where = f"status = 'active' AND stage = {_literal(stage)}"
        return tuple(_public(unit) for unit in self.list_stored(where=where))

    def search(
        self,
        query: KnowledgeSearchQuery,
        query_vector: tuple[float, ...],
    ) -> tuple[KnowledgeSearchHit, ...]:
        if len(query_vector) != MODEL_DIMENSION or not all(
            math.isfinite(value) for value in query_vector
        ):
            raise PluginError("embedding_vector_invalid", "查询向量维度无效")
        filters = ["status = 'active'", f"stage = {_literal(query.stage)}"]
        if query.video_types:
            values = ", ".join(_literal(value) for value in query.video_types)
            filters.append(f"array_has_any(video_types, [{values}])")
        if query.knowledge_types:
            values = ", ".join(_literal(value) for value in query.knowledge_types)
            filters.append(f"knowledge_type IN ({values})")
        with self._refreshed_read() as table:
            rows = (
                table.search(list(query_vector), vector_column_name="vector")
                .distance_type("cosine")
                .where(" AND ".join(filters), prefilter=True)
                .limit(query.limit)
                .to_list()
            )
        hits: list[KnowledgeSearchHit] = []
        for row in rows:
            distance = float(row.pop("_distance"))
            unit = _public(_stored(row))
            hits.append(
                KnowledgeSearchHit.model_validate(
                    {
                        **unit.model_dump(mode="json"),
                        "similarity": max(-1.0, min(1.0, 1 - distance)),
                    }
                )
            )
        return tuple(hits)

    def prepare_embedding_rebuild(
        self,
        embedding: LocalEmbeddingService,
    ) -> tuple[StoredKnowledgeUnit, ...]:
        spaces = self._embedding_spaces()
        if not spaces:
            return ()
        current = embedding.metadata
        target = (current.model, current.version, current.sha256, current.dimension)
        if spaces == {target}:
            return ()
        if len(spaces) != 1:
            raise PluginError("embedding_space_invalid", "知识表包含多个向量空间")
        units = self.list_stored()
        vectors = embedding.embed_documents(tuple(unit.content for unit in units))
        if len(vectors) != len(units):
            raise PluginError("embedding_vector_invalid", "重建向量数量与知识数量不一致")
        return tuple(
            unit.model_copy(
                update={
                    "embedding_model": current.model,
                    "embedding_version": current.version,
                    "embedding_sha256": current.sha256,
                    "embedding_dimension": current.dimension,
                    "vector": vector,
                    "updated_at_us": time.time_ns() // 1000,
                }
            )
            for unit, vector in zip(units, vectors, strict=True)
        )

    def ensure_embedding_space(self, embedding: LocalEmbeddingService) -> None:
        self.merge(self.prepare_embedding_rebuild(embedding))

    def _embedding_spaces(self) -> set[tuple[str, str, str, int]]:
        columns = (
            "embedding_model",
            "embedding_version",
            "embedding_sha256",
            "embedding_dimension",
        )
        with self._refreshed_read() as table:
            rows = table.search().select(list(columns)).to_list()
        return {
            (
                row["embedding_model"],
                row["embedding_version"],
                row["embedding_sha256"],
                row["embedding_dimension"],
            )
            for row in rows
        }

    def _table(self) -> Any:
        if self._table_instance is not None:
            return self._table_instance
        with self._write_lock:
            self._database_dir.mkdir(parents=True, exist_ok=True)
            with self._process_access():
                return self._table_locked()

    def _table_locked(self) -> Any:
        if self._table_instance is None:
            database = lancedb.connect(self._database_dir)
            if _TABLE_NAME in database.list_tables().tables:
                table = database.open_table(_TABLE_NAME)
                if not table.schema.equals(_schema(), check_metadata=False):
                    raise PluginError(
                        "knowledge_store_invalid",
                        "知识表结构与当前合同不一致",
                    )
            else:
                table = database.create_table(_TABLE_NAME, schema=_schema())
            _ensure_indices(table)
            self._table_instance = table
        return self._table_instance

    @contextmanager
    def _refreshed_read(self) -> Iterator[Any]:
        with self._write_lock:
            self._database_dir.mkdir(parents=True, exist_ok=True)
            with self._process_access():
                table = self._table_locked()
                table.checkout_latest()
                yield table

    @contextmanager
    def _process_access(self) -> Iterator[None]:
        try:
            with self._process_lock:
                yield
        except FileLockTimeout as error:
            raise PluginError(
                "knowledge_store_busy",
                "知识库正在处理另一项读写操作",
            ) from error


def _schema() -> pa.Schema:
    evidence = pa.struct(
        [
            pa.field("resource_uri", pa.string(), nullable=False),
            pa.field("start_ms", pa.int64()),
            pa.field("end_ms", pa.int64()),
        ]
    )
    provenance = pa.struct(
        [
            pa.field("analysis_id", pa.string(), nullable=False),
            pa.field("source_media_sha256", pa.string(), nullable=False),
            pa.field("analysis_version", pa.string(), nullable=False),
        ]
    )
    return pa.schema(
        [
            pa.field("knowledge_id", pa.string(), nullable=False),
            pa.field("stage", pa.string(), nullable=False),
            pa.field("knowledge_type", pa.string(), nullable=False),
            pa.field("content", pa.string(), nullable=False),
            pa.field(
                "video_types",
                pa.list_(pa.field("item", pa.string(), nullable=False)),
                nullable=False,
            ),
            pa.field(
                "evidence_refs",
                pa.list_(pa.field("item", evidence, nullable=False)),
                nullable=False,
            ),
            pa.field(
                "provenances",
                pa.list_(pa.field("item", provenance, nullable=False)),
                nullable=False,
            ),
            pa.field("confidence", pa.string(), nullable=False),
            pa.field("status", pa.string(), nullable=False),
            pa.field("embedding_model", pa.string(), nullable=False),
            pa.field("embedding_version", pa.string(), nullable=False),
            pa.field("embedding_sha256", pa.string(), nullable=False),
            pa.field("embedding_dimension", pa.int32(), nullable=False),
            pa.field(
                "vector",
                pa.list_(pa.float32(), MODEL_DIMENSION),
                nullable=False,
            ),
            pa.field("created_at_us", pa.int64(), nullable=False),
            pa.field("updated_at_us", pa.int64(), nullable=False),
        ]
    )


def _ensure_indices(table: Any) -> bool:
    existing = {index.name for index in table.list_indices()}
    created = False
    for column, config in (
        ("knowledge_id", BTree()),
        ("stage", Bitmap()),
        ("knowledge_type", Bitmap()),
        ("status", Bitmap()),
        ("video_types", LabelList()),
    ):
        name = f"{column}_idx"
        if name not in existing:
            table.create_index(column, config=config, name=name, replace=False)
            created = True
    return created


def _maintain_indices(table: Any, *, optimize: bool = False) -> bool:
    try:
        if _ensure_indices(table) or optimize:
            table.optimize()
            return True
    except Exception as error:
        _LOGGER.warning("知识索引维护失败: %s", type(error).__name__)
    return False


def _stored(row: dict[str, Any]) -> StoredKnowledgeUnit:
    payload = dict(row)
    payload.pop("_distance", None)
    vector = payload.get("vector")
    to_list = getattr(vector, "tolist", None)
    if callable(to_list):
        payload["vector"] = to_list()
    try:
        return StoredKnowledgeUnit.model_validate(payload)
    except (ValidationError, TypeError, ValueError) as error:
        raise PluginError("knowledge_vector_invalid", "知识行或向量结构无效") from error


def _public(unit: StoredKnowledgeUnit) -> KnowledgeUnit:
    return KnowledgeUnit.model_validate(unit.model_dump(exclude={"vector"}))


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _shared_lock(path: Path) -> threading.RLock:
    with _LOCKS_GUARD:
        return _WRITE_LOCKS.setdefault(path, threading.RLock())
