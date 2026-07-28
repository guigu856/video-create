"""把参考分析、报告和确认后知识发布映射为薄 MCP Tools 与 Resources。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from video_create_plugin.analysis.jobs import AnalysisJob
from video_create_plugin.analysis.models import SourceMedia
from video_create_plugin.application.reference_runtime import ReferenceRuntime
from video_create_plugin.contracts import FileRef, TimeRangeUs
from video_create_plugin.errors import PluginError
from video_create_plugin.knowledge.models import (
    KnowledgeSearchQuery,
    KnowledgeUnitDraft,
    PublicationRequest,
)
from video_create_plugin.reporting.evidence import build_evidence_bundle
from video_create_plugin.reporting.models import ReferenceStudyReport
from video_create_plugin.reporting.validator import validate_reference_report


def register_reference_capabilities(
    server: FastMCP,
    runtime: ReferenceRuntime,
) -> None:
    @server.tool(
        name="reference_resolve_source",
        description="解析本地文件、URL 或分享文本并固化参考媒体。",
    )
    def reference_resolve_source(source: str) -> dict[str, Any]:
        return _result(
            lambda: {"source_media": runtime.source.resolve(source).model_dump(mode="json")}
        )

    @server.tool(
        name="media_probe",
        description="读取已解析 SourceMedia 中的时长、媒体流和真实 time base。",
    )
    def media_probe(source_media: dict[str, Any]) -> dict[str, Any]:
        return _result(
            lambda: {
                "probe": SourceMedia.model_validate(source_media).probe.model_dump(mode="json")
            }
        )

    @server.tool(
        name="analysis_start",
        description="创建视频和音频证据 Job；可在同一次调用中执行完成。",
    )
    def analysis_start(
        source_media: dict[str, Any],
        run_immediately: bool = True,
    ) -> dict[str, Any]:
        def execute() -> dict[str, Any]:
            job = runtime.analysis.start(SourceMedia.model_validate(source_media))
            if run_immediately:
                job = runtime.analysis.run(job.job_id)
            return _job_data(runtime, job)

        return _result(execute)

    @server.tool(
        name="analysis_get_job",
        description="读取持久分析 Job 的状态、进度、输出和错误。",
    )
    def analysis_get_job(job_id: str) -> dict[str, Any]:
        return _result(lambda: _job_data(runtime, runtime.jobs.get(job_id)))

    @server.tool(
        name="analysis_refine_intervals",
        description="对已完成分析的指定区间进行最大 0.1 秒间隔密集取证。",
    )
    def analysis_refine_intervals(
        job_id: str,
        intervals: list[dict[str, int]],
    ) -> dict[str, Any]:
        return _result(
            lambda: _job_data(
                runtime,
                runtime.analysis.refine_intervals(
                    job_id,
                    tuple(TimeRangeUs.model_validate(item) for item in intervals),
                ),
            )
        )

    @server.tool(
        name="analysis_validate_artifact",
        description="校验参考报告时间线、证据闭包、置信度与结构。",
    )
    def analysis_validate_artifact(report: dict[str, Any]) -> dict[str, Any]:
        return _result(
            lambda: {
                "report": validate_reference_report(
                    ReferenceStudyReport.model_validate(report),
                    runtime.workspace_root,
                ).model_dump(mode="json")
            }
        )

    @server.tool(
        name="report_generate",
        description="从 Agent 已完成的参考报告合同生成 Markdown、JSON 和文件清单。",
    )
    def report_generate(
        report: dict[str, Any],
        output_dir: str,
    ) -> dict[str, Any]:
        return _result(
            lambda: {
                "output": runtime.reporting.generate(
                    ReferenceStudyReport.model_validate(report),
                    runtime.workspace_root / output_dir,
                ).model_dump(mode="json")
            }
        )

    @server.tool(
        name="knowledge_preview_publication",
        description="校验待发布知识的报告来源、阶段分类和证据引用，不写入知识库。",
    )
    def knowledge_preview_publication(
        manifest_file: dict[str, Any],
        units: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return _result(
            lambda: {
                "preview": runtime.knowledge.preview(
                    FileRef.model_validate(manifest_file),
                    tuple(KnowledgeUnitDraft.model_validate(item) for item in units),
                ).model_dump(mode="json")
            }
        )

    @server.tool(
        name="knowledge_publish",
        description="在用户明确确认后发布已预览的可迁移知识。",
    )
    def knowledge_publish(
        manifest_file: dict[str, Any],
        units: list[dict[str, Any]],
        user_confirmed: bool,
    ) -> dict[str, Any]:
        return _result(
            lambda: {
                "publication": runtime.knowledge.publish(
                    PublicationRequest(
                        user_confirmed=user_confirmed,
                        manifest_file=FileRef.model_validate(manifest_file),
                        units=tuple(KnowledgeUnitDraft.model_validate(item) for item in units),
                    )
                ).model_dump(mode="json")
            }
        )

    @server.tool(
        name="knowledge_search",
        description="按 active、阶段、类型、共享可见性和可迁移性过滤创作知识。",
    )
    def knowledge_search(
        stage: str,
        knowledge_types: list[str],
        text: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        return _result(
            lambda: {
                "result": runtime.knowledge.search(
                    KnowledgeSearchQuery.model_validate(
                        {
                            "stage": stage,
                            "knowledge_types": knowledge_types,
                            "text": text,
                            "limit": limit,
                        }
                    )
                ).model_dump(mode="json")
            }
        )

    @server.resource(
        "video-create://analysis/{analysis_id}/{evidence_id}",
        name="analysis_evidence",
        description="按分析 ID 和 evidence_id 读取结构化证据、帧、联系表或波形。",
    )
    def read_analysis(analysis_id: str, evidence_id: str) -> str | bytes:
        return runtime.read_evidence(analysis_id, evidence_id)

    @server.resource(
        "video-create://knowledge/{knowledge_id}",
        name="published_knowledge",
        mime_type="application/json",
    )
    def read_knowledge(knowledge_id: str) -> str:
        return runtime.knowledge_store.get(knowledge_id).model_dump_json(indent=2)


def _result(call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return {"ok": True, "data": call()}
    except PluginError as error:
        return error.to_response().model_dump(mode="json")
    except ValidationError as error:
        return {
            "ok": False,
            "error": {
                "code": "input_invalid",
                "message": "工具输入结构无效",
                "details": {"validation": str(error)[:2000]},
            },
        }


def _job_data(runtime: ReferenceRuntime, job: AnalysisJob) -> dict[str, Any]:
    data: dict[str, Any] = {"job": job.model_dump(mode="json")}
    if job.status == "succeeded":
        data["evidence_bundle"] = build_evidence_bundle(
            job,
            runtime.workspace_root,
        ).model_dump(mode="json")
    return data
