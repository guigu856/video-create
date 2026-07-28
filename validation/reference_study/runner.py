"""编排真实分析与 Agent 报告输入，并把知识发布保留为确认后的独立动作。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from video_create_plugin.analysis.jobs import AnalysisJob
from video_create_plugin.analysis.models import SourceMedia
from video_create_plugin.application.reference_runtime import ReferenceRuntime
from video_create_plugin.contracts import PluginModel
from video_create_plugin.errors import PluginError
from video_create_plugin.knowledge.models import (
    KnowledgeUnitDraft,
    PublicationPreview,
    PublicationRequest,
)
from video_create_plugin.reporting.evidence import build_evidence_bundle
from video_create_plugin.reporting.models import (
    EvidenceBundle,
    ReferenceReportOutput,
    ReferenceStudyReport,
)
from video_create_plugin.reporting.validator import validate_reference_report


@dataclass(frozen=True, slots=True)
class ReferenceStudyContext:
    source: SourceMedia
    job: AnalysisJob
    evidence_bundle: EvidenceBundle


ReportBuilder = Callable[[ReferenceStudyContext], ReferenceStudyReport]


class ReferenceStudyPreparation(PluginModel):
    source: SourceMedia
    job: AnalysisJob
    report_output: ReferenceReportOutput
    publication_preview: PublicationPreview
    publication_request: PublicationRequest


class ReferenceStudyRunner:
    def __init__(self, workspace_root: Path) -> None:
        self._runtime = ReferenceRuntime(workspace_root)

    @property
    def runtime(self) -> ReferenceRuntime:
        return self._runtime

    def prepare(
        self,
        source: str,
        report_builder: ReportBuilder,
        output_dir: Path,
    ) -> ReferenceStudyPreparation:
        source_media = self._runtime.source.resolve(source)
        job = self._runtime.analysis.start(source_media)
        job = self._runtime.analysis.run(job.job_id)
        if job.status != "succeeded":
            message = job.error.message if job.error is not None else "分析 Job 未成功"
            raise PluginError("analysis_failed", message)
        evidence_bundle = build_evidence_bundle(
            job,
            self._runtime.workspace_root,
        )
        report = report_builder(
            ReferenceStudyContext(
                source=source_media,
                job=job,
                evidence_bundle=evidence_bundle,
            )
        )
        validate_reference_report(report, self._runtime.workspace_root)
        report_output = self._runtime.reporting.generate(report, output_dir)
        drafts = tuple(
            KnowledgeUnitDraft(
                applicable_stages=(item.applicable_stage,),
                knowledge_type=item.knowledge_type,
                granularity="global",
                visibility="creation_shared",
                content=item.content,
                evidence_refs=item.evidence_refs,
                fact_status=item.fact_status,
                confidence=item.confidence,
                transferability=item.transferability,
            )
            for item in report.creation_context_projection.all_items()
        )
        preview = self._runtime.knowledge.preview(
            report_output.manifest_file,
            drafts,
        )
        return ReferenceStudyPreparation(
            source=source_media,
            job=job,
            report_output=report_output,
            publication_preview=preview,
            publication_request=PublicationRequest(
                user_confirmed=False,
                manifest_file=report_output.manifest_file,
                units=drafts,
            ),
        )

    def publish(
        self,
        preparation: ReferenceStudyPreparation,
        *,
        user_confirmed: bool,
    ) -> PublicationPreview:
        return self._runtime.knowledge.publish(
            preparation.publication_request.model_copy(update={"user_confirmed": user_confirmed})
        )
