"""组装参考来源、分析 Job、报告与知识服务的本地运行时。"""

from __future__ import annotations

from pathlib import Path

from video_create_plugin.analysis.service import AnalysisJobService
from video_create_plugin.analysis.source import SourceMediaResolver
from video_create_plugin.knowledge.store import KnowledgeStore
from video_create_plugin.reporting.evidence import build_evidence_bundle
from video_create_plugin.repository.jobs import AnalysisJobRepository

from .knowledge import KnowledgeService
from .reference_reporting import ReferenceReportingService


class ReferenceRuntime:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.source = SourceMediaResolver(self.workspace_root)
        self.jobs = AnalysisJobRepository(self.workspace_root)
        self.analysis = AnalysisJobService(self.workspace_root, self.jobs)
        self.reporting = ReferenceReportingService(self.workspace_root)
        self.knowledge_store = KnowledgeStore(
            self.workspace_root / "output/plugin/knowledge.sqlite3"
        )
        self.knowledge = KnowledgeService(self.workspace_root, self.knowledge_store)

    def read_evidence(self, analysis_id: str, evidence_id: str) -> str | bytes:
        job = next(
            (item for item in self.jobs.list() if item.analysis_id == analysis_id),
            None,
        )
        if job is None:
            raise FileNotFoundError(analysis_id)
        bundle = build_evidence_bundle(job, self.workspace_root)
        entry = next(
            (item for item in bundle.entries if item.evidence_id == evidence_id),
            None,
        )
        if entry is None:
            raise FileNotFoundError(evidence_id)
        path = (self.workspace_root / entry.file.path).resolve()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".pcm"}:
            return path.read_bytes()
        return path.read_text(encoding="utf-8")
