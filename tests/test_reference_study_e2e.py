"""使用真实媒体验证参考证据闭环与最终 MCP 公开合同。"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from video_create_plugin.application.reference_runtime import ReferenceRuntime
from video_create_plugin.knowledge.models import (
    KnowledgeEvidenceRef,
    KnowledgePublishRequest,
    KnowledgeSearchQuery,
    KnowledgeUnitDraft,
)
from video_create_plugin.mcp.server import create_server

ROOT = Path(__file__).parents[1]

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="需要 FFmpeg 工具链",
)


def _make_reference_video(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:r=10:d=0.5",
            "-f",
            "lavfi",
            "-i",
            "color=c=white:s=160x90:r=10:d=0.5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=8000:duration=1",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
    )


def test_real_analysis_exposes_evidence_without_persisting_a_report(tmp_path: Path) -> None:
    source_path = tmp_path / "reference.mp4"
    _make_reference_video(source_path)
    runtime = ReferenceRuntime(tmp_path)
    source = runtime.source.resolve(str(source_path))
    job = runtime.analysis.start(source)
    job = runtime.analysis.run(job.job_id)

    assert job.status == "succeeded"
    server = create_server(ROOT, tmp_path)
    resource = asyncio.run(
        server.read_resource(f"video-create://analysis/{job.analysis_id}/contact_sheet")
    )
    assert list(resource)[0].content
    assert runtime.knowledge_store.list_all() == ()
    assert not (tmp_path / "reports").exists()
    assert not list(tmp_path.rglob("reference_report_manifest.json"))

    publication = runtime.knowledge.publish(
        KnowledgePublishRequest(
            analysis_id=job.analysis_id,
            units=(
                KnowledgeUnitDraft(
                    local_id="K001",
                    stage="stage3",
                    video_types=("测试混剪",),
                    knowledge_type="editing_sentence",
                    content="当画面由明暗对比进入重音时，使用明确切换强化视觉释放。",
                    evidence_refs=(
                        KnowledgeEvidenceRef(
                            resource_uri=(
                                f"video-create://analysis/{job.analysis_id}/contact_sheet"
                            )
                        ),
                    ),
                    confidence="high",
                ),
            ),
        )
    )
    found = runtime.knowledge.search(
        KnowledgeSearchQuery(
            stage="stage3",
            video_types=("测试混剪",),
            knowledge_types=("editing_sentence",),
            text="通过画面切换承接音乐重音",
        )
    )

    assert publication.items[0].action == "created"
    assert [item.knowledge_id for item in found.items] == [
        publication.items[0].knowledge_id
    ]


def test_stdio_handshake_exposes_only_the_final_reference_tools(tmp_path: Path) -> None:
    source = tmp_path / "reference.mp4"
    _make_reference_video(source)

    async def verify() -> None:
        environment = os.environ.copy()
        environment["VIDEO_CREATE_WORKSPACE"] = str(tmp_path)
        environment["VIDEO_CREATE_CONTENT_ROOT"] = str(ROOT)
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "video_create_plugin.mcp.server"],
            cwd=ROOT,
            env=environment,
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "video-create"
                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                assert {
                    "reference_resolve_source",
                    "media_probe",
                    "analysis_start",
                    "analysis_get_job",
                    "analysis_refine_intervals",
                    "knowledge_list_stage_types",
                    "knowledge_publish",
                    "knowledge_search",
                } <= tool_names
                assert {
                    "analysis_validate_artifact",
                    "report_generate",
                    "knowledge_preview_publication",
                }.isdisjoint(tool_names)
                resources = await session.list_resources()
                resource_uris = {str(resource.uri) for resource in resources.resources}
                assert "video-create://rules/reference-study-agent" in resource_uris
                assert "video-create://schemas/reference-study" not in resource_uris
                result = await session.call_tool(
                    "reference_resolve_source",
                    {"source": str(source)},
                )
                assert not result.isError
                assert '"ok":true' in result.content[0].text.replace(" ", "")

    asyncio.run(verify())


def test_reference_skill_defines_the_six_chapter_context_document() -> None:
    content = (ROOT / "skills/reference-study/SKILL.md").read_text(encoding="utf-8")
    main_rule = (ROOT / "rules/main-agent.md").read_text(encoding="utf-8")

    for title in (
        "第一章：先用一分钟看懂这条视频",
        "第二章：音乐和声音是怎么带动视频的",
        "第三章：画面是怎么一段段剪出来的",
        "第四章：声音和画面是怎么配合的",
        "第五章：如果重新做一条，应该学什么",
        "第六章：待沉淀知识",
    ):
        assert title in content
    assert "| 时间 | 主要画面 | 画面里的变化 | 对应声音 | 产生的作用 |" in content
    assert "可以重复使用的剪法" in content
    assert "内部字段不进入用户可见的前五章正文" in content
    assert "K001" in content
    assert "knowledge_publish" in content
    assert "宿主文档能力" in content
    assert "DOCX" in content
    assert "前五章使用普通用户能理解的表达" in main_rule
