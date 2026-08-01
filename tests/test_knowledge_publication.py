"""验证 LanceDB 单库中的整批原子发布与显式知识合并。"""

from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import lancedb
import pytest
from filelock import FileLock
from reference_analysis_fixtures import materialize_succeeded_analysis

from video_create_plugin.application.knowledge import KnowledgeService
from video_create_plugin.errors import PluginError
from video_create_plugin.knowledge.embedding import EmbeddingMetadata
from video_create_plugin.knowledge.models import (
    KnowledgeEvidenceRef,
    KnowledgePublishRequest,
    KnowledgeSearchQuery,
    KnowledgeUnitDraft,
)
from video_create_plugin.knowledge.store import KnowledgeStore


class FakeEmbeddingService:
    metadata = EmbeddingMetadata(
        model="fake-zh",
        version="test-1",
        sha256="1" * 64,
        dimension=512,
    )

    def __init__(self) -> None:
        self.document_batches: list[tuple[str, ...]] = []

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.document_batches.append(texts)
        return tuple(_fake_vector(text) for text in texts)

    def embed_query(self, text: str) -> tuple[float, ...]:
        return _fake_vector(text)


def _fake_vector(text: str) -> tuple[float, ...]:
    vector = [0.0] * 512
    vector[0 if any(term in text for term in ("快切", "重拍", "密度")) else 1] = 1.0
    return tuple(vector)


def make_service(
    root: Path,
    *,
    analysis_id: str = "analysis_example",
) -> tuple[KnowledgeService, KnowledgeStore, FakeEmbeddingService]:
    repository, _ = materialize_succeeded_analysis(root, analysis_id=analysis_id)
    embedding = FakeEmbeddingService()
    store = KnowledgeStore(root / "knowledge.lancedb")
    service = KnowledgeService(root, repository, store, embedding)  # type: ignore[arg-type]
    return service, store, embedding


def draft(
    *,
    local_id: str = "K001",
    analysis_id: str = "analysis_example",
    evidence_id: str = "frame_000001",
    existing_knowledge_id: str | None = None,
    stage: str = "stage3",
    video_types: tuple[str, ...] = ("动漫 MAD",),
    knowledge_type: str = "editing_sentence",
    content: str = "连续快切积累视觉密度，再以较长镜头承接重拍释放。",
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> KnowledgeUnitDraft:
    return KnowledgeUnitDraft.model_validate(
        {
            "local_id": local_id,
            "existing_knowledge_id": existing_knowledge_id,
            "stage": stage,
            "video_types": video_types,
            "knowledge_type": knowledge_type,
            "content": content,
            "evidence_refs": (
                KnowledgeEvidenceRef(
                    resource_uri=(
                        f"video-create://analysis/{analysis_id}/{evidence_id}"
                    ),
                    start_ms=start_ms,
                    end_ms=end_ms,
                ),
            ),
            "confidence": "high",
        }
    )


def publish(
    service: KnowledgeService,
    *units: KnowledgeUnitDraft,
    analysis_id: str = "analysis_example",
):
    return service.publish(KnowledgePublishRequest(analysis_id=analysis_id, units=units))


def test_new_publication_persists_one_row_and_one_vector(tmp_path: Path) -> None:
    service, store, embedding = make_service(tmp_path)

    result = publish(service, draft(video_types=("动漫 MAD", "燃向混剪")))

    assert result.items[0].action == "created"
    assert result.items[0].local_id == "K001"
    assert embedding.document_batches == [
        ("连续快切积累视觉密度，再以较长镜头承接重拍释放。",)
    ]
    units = store.list_all()
    assert len(units) == 1
    assert units[0].video_types == ("动漫 MAD", "燃向混剪")
    assert units[0].provenances[0].analysis_id == "analysis_example"
    assert not (tmp_path / "output/plugin/knowledge.sqlite3").exists()

    restarted = KnowledgeStore(tmp_path / "knowledge.lancedb")
    assert restarted.get(units[0].knowledge_id) == units[0]


def test_publication_updates_all_scalar_indices(tmp_path: Path) -> None:
    service, _, _ = make_service(tmp_path)

    publish(service, draft())

    table = lancedb.connect(tmp_path / "knowledge.lancedb").open_table("knowledge_units")
    indices = table.list_indices()
    assert {index.name for index in indices} == {
        "knowledge_id_idx",
        "knowledge_type_idx",
        "stage_idx",
        "status_idx",
        "video_types_idx",
    }
    assert all(index.num_indexed_rows == 1 for index in indices)
    assert all(index.num_unindexed_rows == 0 for index in indices)


def test_index_maintenance_failure_keeps_committed_publication_usable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, store, _ = make_service(tmp_path)
    table = store._table()

    def fail_index_creation(*_: object, **__: object) -> None:
        raise RuntimeError("index maintenance failed")

    create_index = table.create_index
    monkeypatch.setattr(table, "create_index", fail_index_creation)

    result = publish(service, draft())
    monkeypatch.setattr(table, "create_index", create_index)

    assert result.items[0].action == "created"
    assert [unit.knowledge_id for unit in store.list_all()] == [
        result.items[0].knowledge_id
    ]
    found = service.search(
        KnowledgeSearchQuery(
            stage="stage3",
            video_types=("动漫 MAD",),
            knowledge_types=("editing_sentence",),
            text="重拍前使用连续快切积累密度",
        )
    )
    assert [unit.knowledge_id for unit in found.items] == [result.items[0].knowledge_id]
    assert len(table.list_indices()) == 5


def test_file_lock_timeout_has_a_stable_store_error(tmp_path: Path) -> None:
    _, store, _ = make_service(tmp_path)
    database = tmp_path / "knowledge.lancedb"
    database.mkdir(parents=True, exist_ok=True)
    store._process_lock = FileLock(str(database / ".write.lock"), timeout=0.01)
    external_lock = FileLock(str(database / ".write.lock"))

    with external_lock, pytest.raises(PluginError) as caught:
        store.list_all()

    assert caught.value.code == "knowledge_store_busy"


def test_any_invalid_unit_leaves_the_batch_unwritten(tmp_path: Path) -> None:
    service, store, _ = make_service(tmp_path)

    with pytest.raises(PluginError) as caught:
        publish(
            service,
            draft(local_id="K001"),
            draft(local_id="K002", evidence_id="missing_evidence"),
        )

    assert caught.value.code == "evidence_not_found"
    assert store.list_all() == ()


@pytest.mark.parametrize(
    ("unit", "code"),
    [
        (draft(analysis_id="analysis_other"), "evidence_analysis_mismatch"),
        (
            draft(
                evidence_id="audio_signals",
                start_ms=900,
                end_ms=1_100,
            ),
            "evidence_time_out_of_range",
        ),
    ],
)
def test_invalid_evidence_ownership_or_range_is_rejected(
    tmp_path: Path,
    unit: KnowledgeUnitDraft,
    code: str,
) -> None:
    service, store, _ = make_service(tmp_path)

    with pytest.raises(PluginError) as caught:
        publish(service, unit)

    assert caught.value.code == code
    assert store.list_all() == ()


def test_explicit_merge_preserves_canonical_content_and_vector(tmp_path: Path) -> None:
    service, store, embedding = make_service(tmp_path)
    created = publish(service, draft())
    knowledge_id = created.items[0].knowledge_id
    before = store.get_stored(knowledge_id)
    materialize_succeeded_analysis(tmp_path, analysis_id="analysis_second")

    merged = publish(
        service,
        draft(
            local_id="K002",
            analysis_id="analysis_second",
            evidence_id="frame_000002",
            existing_knowledge_id=knowledge_id,
            video_types=("电影混剪",),
            content="这段输入正文只用于说明合并意图，不覆盖规范正文。",
        ),
        analysis_id="analysis_second",
    )
    after = store.get_stored(knowledge_id)

    assert merged.items[0].action == "merged"
    assert after.content == before.content
    assert after.vector == before.vector
    assert after.confidence == before.confidence
    assert after.created_at_us == before.created_at_us
    assert after.video_types == ("动漫 MAD", "电影混剪")
    assert {item.analysis_id for item in after.provenances} == {
        "analysis_example",
        "analysis_second",
    }
    assert len(after.evidence_refs) == 2
    assert len(embedding.document_batches) == 1


def test_repeated_explicit_merge_is_idempotent(tmp_path: Path) -> None:
    service, store, _ = make_service(tmp_path)
    knowledge_id = publish(service, draft()).items[0].knowledge_id
    materialize_succeeded_analysis(tmp_path, analysis_id="analysis_second")
    merge_draft = draft(
        local_id="K002",
        analysis_id="analysis_second",
        evidence_id="frame_000002",
        existing_knowledge_id=knowledge_id,
        video_types=("电影混剪",),
    )

    publish(service, merge_draft, analysis_id="analysis_second")
    first = store.get_stored(knowledge_id)
    publish(service, merge_draft, analysis_id="analysis_second")
    second = store.get_stored(knowledge_id)

    assert second == first


def test_merge_contract_mismatch_does_not_change_existing_row(tmp_path: Path) -> None:
    service, store, _ = make_service(tmp_path)
    knowledge_id = publish(service, draft()).items[0].knowledge_id
    before = store.get_stored(knowledge_id)

    with pytest.raises(PluginError) as caught:
        publish(
            service,
            draft(
                local_id="K002",
                existing_knowledge_id=knowledge_id,
                knowledge_type="motion_pattern",
            ),
        )

    assert caught.value.code == "knowledge_merge_invalid"
    assert store.get_stored(knowledge_id) == before


def test_valid_millisecond_interval_is_preserved(tmp_path: Path) -> None:
    service, store, _ = make_service(tmp_path)

    publish(
        service,
        draft(
            evidence_id="audio_signals",
            start_ms=100,
            end_ms=200,
        ),
    )

    reference = store.list_all()[0].evidence_refs[0]
    assert (reference.start_ms, reference.end_ms) == (100, 200)


def test_concurrent_explicit_merges_keep_both_updates(tmp_path: Path) -> None:
    service, store, _ = make_service(tmp_path)
    knowledge_id = publish(service, draft()).items[0].knowledge_id
    materialize_succeeded_analysis(tmp_path, analysis_id="analysis_second")
    materialize_succeeded_analysis(tmp_path, analysis_id="analysis_third")

    def merge(analysis_id: str, video_type: str, evidence_id: str) -> None:
        publish(
            service,
            draft(
                local_id="K002",
                analysis_id=analysis_id,
                evidence_id=evidence_id,
                existing_knowledge_id=knowledge_id,
                video_types=(video_type,),
            ),
            analysis_id=analysis_id,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(merge, "analysis_second", "电影混剪", "frame_000001"),
            executor.submit(merge, "analysis_third", "游戏混剪", "frame_000002"),
        )
        for future in futures:
            future.result()

    unit = store.get(knowledge_id)
    assert set(unit.video_types) == {"动漫 MAD", "电影混剪", "游戏混剪"}
    assert {item.analysis_id for item in unit.provenances} == {
        "analysis_example",
        "analysis_second",
        "analysis_third",
    }


def test_embedding_upgrade_and_merge_keep_the_current_vector_space(tmp_path: Path) -> None:
    service, store, _ = make_service(tmp_path)
    knowledge_id = publish(service, draft()).items[0].knowledge_id
    old = store.get_stored(knowledge_id).model_copy(
        update={
            "embedding_model": "old-model",
            "embedding_version": "old-version",
            "embedding_sha256": "2" * 64,
        }
    )
    store.merge((old,))
    materialize_succeeded_analysis(tmp_path, analysis_id="analysis_second")

    publish(
        service,
        draft(
            local_id="K002",
            analysis_id="analysis_second",
            evidence_id="frame_000002",
            existing_knowledge_id=knowledge_id,
            video_types=("电影混剪",),
        ),
        analysis_id="analysis_second",
    )

    after = store.get_stored(knowledge_id)
    assert (
        after.embedding_model,
        after.embedding_version,
        after.embedding_sha256,
    ) == ("fake-zh", "test-1", "1" * 64)
    assert after.video_types == ("动漫 MAD", "电影混剪")


def test_separate_process_writers_preserve_both_merges(tmp_path: Path) -> None:
    service, store, _ = make_service(tmp_path)
    knowledge_id = publish(service, draft()).items[0].knowledge_id
    database = tmp_path / "knowledge.lancedb"
    script = """
import sys
import time
from pathlib import Path

from video_create_plugin.knowledge.models import KnowledgeEvidenceRef, KnowledgeProvenance
from video_create_plugin.knowledge.store import KnowledgeStore

database, knowledge_id, analysis_id, video_type = sys.argv[1:]
store = KnowledgeStore(Path(database))
with store.serialized_write():
    row = store.get_stored(knowledge_id)
    time.sleep(0.6)
    evidence = KnowledgeEvidenceRef(
        resource_uri=f"video-create://analysis/{analysis_id}/frame_000001"
    )
    provenance = KnowledgeProvenance(
        analysis_id=analysis_id,
        source_media_sha256="3" * 64,
        analysis_version="1.0",
    )
    store.merge((row.model_copy(update={
        "video_types": (*row.video_types, video_type),
        "evidence_refs": (*row.evidence_refs, evidence),
        "provenances": (*row.provenances, provenance),
        "updated_at_us": row.updated_at_us + 1,
    }),))
"""
    processes = tuple(
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(database),
                knowledge_id,
                analysis_id,
                video_type,
            ],
            cwd=Path(__file__).parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        for analysis_id, video_type in (
            ("analysis_second", "电影混剪"),
            ("analysis_third", "游戏混剪"),
        )
    )
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stdout + stderr

    unit = KnowledgeStore(database).get(knowledge_id)
    assert set(unit.video_types) == {"动漫 MAD", "电影混剪", "游戏混剪"}
    assert {item.analysis_id for item in unit.provenances} == {
        "analysis_example",
        "analysis_second",
        "analysis_third",
    }
