"""以 SQLite 保存知识事实源和可重建的确定性文本检索投影。"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path

from .models import KnowledgeSearchQuery, KnowledgeUnit

_EMBEDDING_MODEL = "hash_char_ngram_v1"
_EMBEDDING_DIMENSION = 128


class KnowledgeStore:
    def __init__(self, database_path: Path) -> None:
        self._path = database_path.resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save(self, units: tuple[KnowledgeUnit, ...]) -> tuple[KnowledgeUnit, ...]:
        with self._connect() as connection:
            for unit in units:
                connection.execute(
                    """
                    INSERT INTO knowledge_units(
                        knowledge_id, payload, status, collection, knowledge_type, embedding
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(knowledge_id) DO UPDATE SET
                        payload=excluded.payload,
                        status=excluded.status,
                        collection=excluded.collection,
                        knowledge_type=excluded.knowledge_type,
                        embedding=excluded.embedding
                    """,
                    (
                        unit.knowledge_id,
                        unit.model_dump_json(),
                        unit.status,
                        unit.collection,
                        unit.knowledge_type,
                        json.dumps(_embedding(unit.content), separators=(",", ":")),
                    ),
                )
                connection.execute(
                    "DELETE FROM knowledge_stages WHERE knowledge_id = ?",
                    (unit.knowledge_id,),
                )
                connection.executemany(
                    "INSERT INTO knowledge_stages(knowledge_id, stage) VALUES (?, ?)",
                    ((unit.knowledge_id, stage) for stage in unit.applicable_stages),
                )
        return units

    def list_all(self) -> tuple[KnowledgeUnit, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM knowledge_units ORDER BY knowledge_id"
            ).fetchall()
        return tuple(KnowledgeUnit.model_validate_json(row[0]) for row in rows)

    def archive(self, knowledge_id: str) -> KnowledgeUnit:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM knowledge_units WHERE knowledge_id = ?",
                (knowledge_id,),
            ).fetchone()
            if row is None:
                raise KeyError(knowledge_id)
            unit = KnowledgeUnit.model_validate_json(row[0]).model_copy(
                update={"status": "archived"}
            )
            connection.execute(
                "UPDATE knowledge_units SET payload = ?, status = 'archived' "
                "WHERE knowledge_id = ?",
                (unit.model_dump_json(), knowledge_id),
            )
        return unit

    def search_creation(
        self,
        query: KnowledgeSearchQuery,
    ) -> tuple[KnowledgeUnit, ...]:
        placeholders = ",".join("?" for _ in query.knowledge_types)
        sql = f"""
            SELECT DISTINCT u.payload, u.embedding
            FROM knowledge_units u
            JOIN knowledge_stages s ON s.knowledge_id = u.knowledge_id
            WHERE u.status = 'active'
              AND u.collection = 'creation_knowledge'
              AND s.stage = ?
              AND u.knowledge_type IN ({placeholders})
        """
        parameters = (query.stage, *query.knowledge_types)
        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        requested_embedding = _embedding(query.text) if query.text.strip() else None
        ranked: list[tuple[float, KnowledgeUnit]] = []
        for payload, embedding_json in rows:
            unit = KnowledgeUnit.model_validate_json(payload)
            if not _matches_tags(unit.video_type_tags, query.video_type_tags):
                continue
            if not _matches_tags(unit.technique_tags, query.technique_tags):
                continue
            if not _matches_tags(unit.music_layer_tags, query.music_layer_tags):
                continue
            if query.energy_phase is not None and unit.energy_phase != query.energy_phase:
                continue
            score = (
                _cosine(requested_embedding, json.loads(embedding_json))
                if requested_embedding is not None
                else 0
            )
            ranked.append((score, unit))
        ranked.sort(key=lambda item: (-item[0], item[1].knowledge_id))
        return tuple(unit for _, unit in ranked[: query.limit])

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_units(
                    knowledge_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    collection TEXT NOT NULL,
                    knowledge_type TEXT NOT NULL,
                    embedding TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_stages(
                    knowledge_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    PRIMARY KEY(knowledge_id, stage),
                    FOREIGN KEY(knowledge_id) REFERENCES knowledge_units(knowledge_id)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS index_metadata(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO index_metadata(key, value) VALUES (?, ?)",
                ("embedding_model", _EMBEDDING_MODEL),
            )
            connection.execute(
                "INSERT OR REPLACE INTO index_metadata(key, value) VALUES (?, ?)",
                ("embedding_dimension", str(_EMBEDDING_DIMENSION)),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _matches_tags(actual: tuple[str, ...], requested: tuple[str, ...]) -> bool:
    return not requested or set(requested).issubset(actual)


def _embedding(text: str) -> list[float]:
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    characters = [character for character in normalized if not character.isspace()]
    tokens = re.findall(r"\w+", normalized)
    tokens.extend(
        "".join(characters[index : index + 2]) for index in range(max(0, len(characters) - 1))
    )
    vector = [0.0] * _EMBEDDING_DIMENSION
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % _EMBEDDING_DIMENSION
        vector[index] += 1 if digest[4] & 1 else -1
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(first * second for first, second in zip(left, right))
