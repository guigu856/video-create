"""校验用户确认、报告来源和阶段投影后发布并检索知识。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from video_create_plugin.contracts import FileRef
from video_create_plugin.errors import PluginError
from video_create_plugin.knowledge.models import (
    KnowledgeCollection,
    KnowledgeSearchQuery,
    KnowledgeSearchResult,
    KnowledgeUnit,
    KnowledgeUnitDraft,
    PublicationPreview,
    PublicationRequest,
)
from video_create_plugin.knowledge.store import KnowledgeStore
from video_create_plugin.reporting.models import (
    ApplicableStage,
    ReferenceReportManifest,
    ReferenceStudyReport,
)
from video_create_plugin.reporting.validator import validate_reference_report


class KnowledgeService:
    def __init__(self, workspace_root: Path, store: KnowledgeStore) -> None:
        self._workspace_root = workspace_root.resolve()
        self._store = store

    def preview(
        self,
        manifest_file: FileRef,
        drafts: tuple[KnowledgeUnitDraft, ...],
    ) -> PublicationPreview:
        manifest, report = self._load_report(manifest_file)
        available_evidence = {entry.evidence_id for entry in report.evidence_bundle.entries}
        projected = {
            (
                item.applicable_stage,
                item.knowledge_type,
                item.content,
                item.evidence_refs,
            )
            for item in report.creation_context_projection.all_items()
        }
        report_file = manifest.file_for("structured_report")
        units: list[KnowledgeUnit] = []
        for draft in drafts:
            missing = sorted(set(draft.evidence_refs) - available_evidence)
            if missing:
                raise PluginError(
                    "evidence_not_found",
                    "知识条目包含不存在的证据",
                    details={"evidence_refs": ",".join(missing)},
                )
            collection = self._validate_draft(draft, projected)
            identity = _knowledge_identity(report_file.sha256, draft)
            units.append(
                KnowledgeUnit(
                    **draft.model_dump(),
                    knowledge_id=f"knowledge_{identity[:16]}",
                    source_report_path=report_file.path,
                    source_report_sha256=report_file.sha256,
                    source_media_sha256=report.source_media_sha256,
                    analysis_version=report.analysis_version,
                    collection=collection,
                )
            )
        return PublicationPreview(units=tuple(units))

    def publish(self, request: PublicationRequest) -> PublicationPreview:
        if not request.user_confirmed:
            raise PluginError(
                "knowledge_publication_rejected",
                "知识发布需要用户明确确认",
            )
        preview = self.preview(request.manifest_file, request.units)
        self._store.save(preview.units)
        return preview

    def search(self, query: KnowledgeSearchQuery) -> KnowledgeSearchResult:
        return KnowledgeSearchResult(items=self._store.search_creation(query))

    def read_report(self, reference: FileRef) -> str:
        return self._validated_path(reference).read_text(encoding="utf-8")

    def _load_report(
        self,
        manifest_file: FileRef,
    ) -> tuple[ReferenceReportManifest, ReferenceStudyReport]:
        manifest_path = self._validated_path(manifest_file)
        manifest = ReferenceReportManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        for item in manifest.files:
            self._validated_path(item.file)
        report_file = manifest.file_for("structured_report")
        report = ReferenceStudyReport.model_validate_json(
            self._validated_path(report_file).read_text(encoding="utf-8")
        )
        validate_reference_report(report, self._workspace_root)
        if manifest.source_media_sha256 != report.source_media_sha256:
            raise PluginError(
                "knowledge_publication_rejected",
                "报告清单与结构化报告媒体哈希不一致",
            )
        return manifest, report

    def _validated_path(self, reference: FileRef) -> Path:
        path = (self._workspace_root / reference.path).resolve()
        if not path.is_relative_to(self._workspace_root) or not path.is_file():
            raise PluginError(
                "file_not_found",
                "知识来源文件不存在",
                details={"path": reference.path},
            )
        if _sha256(path) != reference.sha256:
            raise PluginError(
                "file_hash_mismatch",
                "知识来源文件哈希不匹配",
                details={"path": reference.path},
            )
        return path

    @staticmethod
    def _validate_draft(
        draft: KnowledgeUnitDraft,
        projected: set[tuple[ApplicableStage, str, str, tuple[str, ...]]],
    ) -> KnowledgeCollection:
        if draft.visibility == "creation_shared":
            if draft.transferability != "reusable_mechanism":
                raise PluginError(
                    "knowledge_publication_rejected",
                    "创作共享知识必须是可迁移机制",
                )
            if draft.source_time_range is not None:
                raise PluginError(
                    "knowledge_publication_rejected",
                    "创作共享知识不携带参考片时间线建议",
                )
            if any(
                (stage, draft.knowledge_type, draft.content, draft.evidence_refs) not in projected
                for stage in draft.applicable_stages
            ):
                raise PluginError(
                    "knowledge_publication_rejected",
                    "创作共享知识必须来自已校验阶段投影",
                )
            return "creation_knowledge"
        if draft.visibility == "evidence_only" and draft.transferability == "reference_specific":
            return "reference_evidence"
        raise PluginError(
            "knowledge_publication_rejected",
            "知识可见性与可迁移性组合无效",
        )


def _knowledge_identity(report_sha256: str, draft: KnowledgeUnitDraft) -> str:
    payload = (
        report_sha256,
        ",".join(draft.applicable_stages),
        draft.knowledge_type,
        draft.content,
        ",".join(draft.evidence_refs),
    )
    return hashlib.sha256("|".join(payload).encode()).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
