"""把参考分析证据和确认后的知识操作映射为薄 MCP Tools 与 Resources。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import TypeAdapter, ValidationError

from video_create_plugin.analysis.evidence import build_evidence_bundle
from video_create_plugin.analysis.jobs import AnalysisJob
from video_create_plugin.analysis.models import SourceMedia
from video_create_plugin.application.reference_runtime import ReferenceRuntime
from video_create_plugin.contracts import TimeRangeUs
from video_create_plugin.errors import PluginError
from video_create_plugin.knowledge.models import (
    ApplicableStage,
    KnowledgePublishRequest,
    KnowledgeSearchQuery,
    KnowledgeUnitDraft,
)


def register_reference_capabilities(server: FastMCP, runtime: ReferenceRuntime) -> None:
    @server.tool(
        name="reference_resolve_source",
        description="解析本地文件、URL 或分享文本并固化参考媒体。",
    )
    async def reference_resolve_source(source: str) -> dict[str, Any]:
        async def execute() -> dict[str, Any]:
            source_media = await runtime.source.resolve_async(source)
            return {"source_media": source_media.model_dump(mode="json")}

        return await _result_async(execute)

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
        name="knowledge_list_stage_types",
        description="实时汇总指定阶段 active 知识中的视频类型和知识类型。",
    )
    def knowledge_list_stage_types(stage: str) -> dict[str, Any]:
        return _result(
            lambda: {
                "result": runtime.knowledge.list_stage_types(
                    TypeAdapter(ApplicableStage).validate_python(stage)
                ).model_dump(mode="json")
            }
        )

    @server.tool(
        name="knowledge_publish",
        description="把用户最终选中的知识作为一个原子批次创建或显式合并。",
    )
    def knowledge_publish(
        analysis_id: str,
        units: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return _result(
            lambda: {
                "publication": runtime.knowledge.publish(
                    KnowledgePublishRequest(
                        analysis_id=analysis_id,
                        units=tuple(KnowledgeUnitDraft.model_validate(item) for item in units),
                    )
                ).model_dump(mode="json")
            }
        )

    @server.tool(
        name="knowledge_search",
        description="先按 active、阶段、动态类型过滤，再执行中文正文语义排序。",
    )
    def knowledge_search(
        stage: str,
        video_types: list[str],
        knowledge_types: list[str],
        text: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        return _result(
            lambda: {
                "result": runtime.knowledge.search(
                    KnowledgeSearchQuery.model_validate(
                        {
                            "stage": stage,
                            "video_types": video_types,
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


async def _result_async(
    call: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    try:
        return {"ok": True, "data": await call()}
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
