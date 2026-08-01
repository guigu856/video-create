"""组装参考来源、分析证据与 LanceDB 知识服务的稳定本地运行时。"""

from __future__ import annotations

from pathlib import Path

from video_create_plugin.analysis.evidence import (
    build_evidence_bundle,
    verified_evidence_path,
)
from video_create_plugin.analysis.service import AnalysisJobService
from video_create_plugin.analysis.source import SourceMediaResolver
from video_create_plugin.errors import PluginError
from video_create_plugin.knowledge.embedding import LocalEmbeddingService
from video_create_plugin.knowledge.store import KnowledgeStore
from video_create_plugin.repository.jobs import AnalysisJobRepository

from .knowledge import KnowledgeService


class ReferenceRuntime:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.expanduser().resolve()
        self.source = SourceMediaResolver(self.workspace_root)
        self.jobs = AnalysisJobRepository(self.workspace_root)
        self.analysis = AnalysisJobService(self.workspace_root, self.jobs)
        self.knowledge_store = KnowledgeStore(self.workspace_root / "knowledge.lancedb")
        self.knowledge = KnowledgeService(
            self.workspace_root,
            self.jobs,
            self.knowledge_store,
            LocalEmbeddingService(),
        )

    def read_evidence(self, analysis_id: str, evidence_id: str) -> str | bytes:
        job = next(
            (item for item in self.jobs.list() if item.analysis_id == analysis_id),
            None,
        )
        if job is None:
            raise PluginError(
                "analysis_job_not_found",
                "分析 Job 不存在",
                details={"analysis_id": analysis_id},
            )
        bundle = build_evidence_bundle(job, self.workspace_root)
        entry = next(
            (item for item in bundle.entries if item.evidence_id == evidence_id),
            None,
        )
        if entry is None:
            raise PluginError(
                "evidence_not_found",
                "分析证据不存在",
                details={"evidence_id": evidence_id},
            )
        path = verified_evidence_path(self.workspace_root, entry)
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".pcm"}:
            return path.read_bytes()
        return path.read_text(encoding="utf-8")
