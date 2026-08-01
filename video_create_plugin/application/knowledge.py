"""从已完成分析机械校验证据并原子发布、汇总和检索知识。"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Literal, TypeVar

from video_create_plugin.analysis.evidence import build_evidence_bundle
from video_create_plugin.analysis.jobs import AnalysisJob
from video_create_plugin.analysis.models import EvidenceEntry
from video_create_plugin.errors import PluginError
from video_create_plugin.knowledge.embedding import LocalEmbeddingService
from video_create_plugin.knowledge.models import (
    ApplicableStage,
    KnowledgeEvidenceRef,
    KnowledgeProvenance,
    KnowledgePublishItem,
    KnowledgePublishRequest,
    KnowledgePublishResult,
    KnowledgeSearchQuery,
    KnowledgeSearchResult,
    KnowledgeTypeCount,
    StageTypesResult,
    StoredKnowledgeUnit,
    VideoTypeSummary,
)
from video_create_plugin.knowledge.store import KnowledgeStore
from video_create_plugin.repository.jobs import AnalysisJobRepository

T = TypeVar("T")


class KnowledgeService:
    def __init__(
        self,
        workspace_root: Path,
        jobs: AnalysisJobRepository,
        store: KnowledgeStore,
        embedding: LocalEmbeddingService,
    ) -> None:
        self._workspace_root = workspace_root.resolve()
        self._jobs = jobs
        self._store = store
        self._embedding = embedding

    def publish(self, request: KnowledgePublishRequest) -> KnowledgePublishResult:
        with self._store.serialized_write():
            job = self._completed_job(request.analysis_id)
            bundle = build_evidence_bundle(job, self._workspace_root)
            available = {entry.evidence_id: entry for entry in bundle.entries}
            for draft in request.units:
                self._validate_evidence_refs(job, available, draft.evidence_refs)

            target_ids = tuple(
                draft.existing_knowledge_id
                for draft in request.units
                if draft.existing_knowledge_id is not None
            )
            if len(target_ids) != len(set(target_ids)):
                raise PluginError(
                    "knowledge_merge_invalid",
                    "同一批发布不得多次合并同一知识",
                )
            rebuilt = self._store.prepare_embedding_rebuild(self._embedding)
            rebuilt_by_id = {unit.knowledge_id: unit for unit in rebuilt}
            targets: dict[str, StoredKnowledgeUnit] = {}
            for draft in request.units:
                if draft.existing_knowledge_id is None:
                    continue
                target = rebuilt_by_id.get(
                    draft.existing_knowledge_id
                ) or self._store.get_stored_optional(draft.existing_knowledge_id)
                if target is None:
                    raise PluginError("knowledge_not_found", "待合并知识不存在")
                if target.status != "active":
                    raise PluginError("knowledge_merge_invalid", "归档知识不可继续合并")
                if target.stage != draft.stage or target.knowledge_type != draft.knowledge_type:
                    raise PluginError(
                        "knowledge_merge_invalid",
                        "待合并知识的阶段或知识类型不一致",
                    )
                targets[target.knowledge_id] = target

            new_drafts = tuple(
                draft for draft in request.units if draft.existing_knowledge_id is None
            )
            vectors = (
                self._embedding.embed_documents(tuple(draft.content for draft in new_drafts))
                if new_drafts
                else ()
            )
            if len(vectors) != len(new_drafts):
                raise PluginError("embedding_vector_invalid", "正文与生成向量数量不一致")
            vector_by_local_id = {
                draft.local_id: vector
                for draft, vector in zip(new_drafts, vectors, strict=True)
            }
            metadata = self._embedding.metadata
            provenance = KnowledgeProvenance(
                analysis_id=job.analysis_id,
                source_media_sha256=bundle.source_media_sha256,
                analysis_version=bundle.analysis_version,
            )
            now = time.time_ns() // 1000
            rows = {unit.knowledge_id: unit for unit in rebuilt}
            results: list[KnowledgePublishItem] = []
            batch_ids: set[str] = set()
            for draft in request.units:
                action: Literal["created", "merged"]
                if draft.existing_knowledge_id is None:
                    knowledge_id = self._new_knowledge_id(batch_ids)
                    row = StoredKnowledgeUnit(
                        knowledge_id=knowledge_id,
                        stage=draft.stage,
                        video_types=draft.video_types,
                        knowledge_type=draft.knowledge_type,
                        content=draft.content,
                        evidence_refs=draft.evidence_refs,
                        provenances=(provenance,),
                        confidence=draft.confidence,
                        embedding_model=metadata.model,
                        embedding_version=metadata.version,
                        embedding_sha256=metadata.sha256,
                        embedding_dimension=metadata.dimension,
                        vector=vector_by_local_id[draft.local_id],
                        created_at_us=now,
                        updated_at_us=now,
                    )
                    action = "created"
                else:
                    knowledge_id = draft.existing_knowledge_id
                    target = targets[knowledge_id]
                    video_types = _stable_union(target.video_types, draft.video_types)
                    evidence_refs = _stable_union(target.evidence_refs, draft.evidence_refs)
                    provenances = _stable_union(target.provenances, (provenance,))
                    changed = (
                        video_types != target.video_types
                        or evidence_refs != target.evidence_refs
                        or provenances != target.provenances
                    )
                    row = target.model_copy(
                        update={
                            "video_types": video_types,
                            "evidence_refs": evidence_refs,
                            "provenances": provenances,
                            "updated_at_us": now if changed else target.updated_at_us,
                        }
                    )
                    action = "merged"
                batch_ids.add(knowledge_id)
                rows[knowledge_id] = row
                results.append(
                    KnowledgePublishItem(
                        local_id=draft.local_id,
                        knowledge_id=knowledge_id,
                        action=action,
                    )
                )
            self._store.merge(tuple(rows.values()))
            return KnowledgePublishResult(items=tuple(results))

    def list_stage_types(self, stage: ApplicableStage) -> StageTypesResult:
        counts: dict[str, dict[str, set[str]]] = {}
        for unit in self._store.active_for_stage(stage):
            for video_type in unit.video_types:
                counts.setdefault(video_type, {}).setdefault(unit.knowledge_type, set()).add(
                    unit.knowledge_id
                )
        return StageTypesResult(
            stage=stage,
            video_types=tuple(
                VideoTypeSummary(
                    name=video_type,
                    knowledge_types=tuple(
                        KnowledgeTypeCount(name=knowledge_type, count=len(knowledge_ids))
                        for knowledge_type, knowledge_ids in sorted(types.items())
                    ),
                )
                for video_type, types in sorted(counts.items())
            ),
        )

    def search(self, query: KnowledgeSearchQuery) -> KnowledgeSearchResult:
        with self._store.serialized_write():
            self._store.ensure_embedding_space(self._embedding)
            self._store.repair_indices()
        vector = self._embedding.embed_query(query.text)
        return KnowledgeSearchResult(items=self._store.search(query, vector))

    def _completed_job(self, analysis_id: str) -> AnalysisJob:
        job = next(
            (item for item in self._jobs.list() if item.analysis_id == analysis_id),
            None,
        )
        if job is None:
            raise PluginError(
                "analysis_job_not_found",
                "分析 Job 不存在",
                details={"analysis_id": analysis_id},
            )
        if job.status != "succeeded":
            raise PluginError("analysis_incomplete", "分析 Job 完成后才能发布知识")
        return job

    @staticmethod
    def _validate_evidence_refs(
        job: AnalysisJob,
        available: dict[str, EvidenceEntry],
        references: tuple[KnowledgeEvidenceRef, ...],
    ) -> None:
        for reference in references:
            suffix = reference.resource_uri.removeprefix("video-create://analysis/")
            analysis_id, evidence_id = suffix.split("/", 1)
            if analysis_id != job.analysis_id:
                raise PluginError(
                    "evidence_analysis_mismatch",
                    "证据引用不属于本次分析",
                )
            entry = available.get(evidence_id)
            if entry is None:
                raise PluginError(
                    "evidence_not_found",
                    "知识条目引用了未知证据",
                    details={"evidence_id": evidence_id},
                )
            if reference.start_ms is None or reference.end_ms is None:
                continue
            start_us = reference.start_ms * 1000
            end_us = reference.end_ms * 1000
            if end_us > job.source.probe.duration_us:
                raise PluginError(
                    "evidence_time_out_of_range",
                    "证据时间范围超出来源媒体",
                )
            if entry.time_range is not None and (
                start_us < entry.time_range.start_us or end_us > entry.time_range.end_us
            ):
                raise PluginError(
                    "evidence_time_out_of_range",
                    "证据时间范围超出引用证据",
                )

    def _new_knowledge_id(self, batch_ids: set[str]) -> str:
        while True:
            knowledge_id = f"knowledge_{uuid.uuid4().hex[:16]}"
            if (
                knowledge_id not in batch_ids
                and self._store.get_stored_optional(knowledge_id) is None
            ):
                return knowledge_id


def _stable_union(existing: tuple[T, ...], added: tuple[T, ...]) -> tuple[T, ...]:
    return existing + tuple(item for item in added if item not in existing)
