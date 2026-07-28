"""使用真实媒体验证 Codex/MCP 参考学习、报告和确认后知识发布闭环。"""

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
from test_reference_report_contract import make_reference_report

from validation.reference_study.runner import (
    ReferenceStudyContext,
    ReferenceStudyRunner,
)
from video_create_plugin.contracts import TimeRangeUs
from video_create_plugin.errors import PluginError
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


def _agent_report(context: ReferenceStudyContext):
    report = make_reference_report()
    duration_us = context.source.probe.duration_us
    split_us = duration_us // 2
    first, second = report.shot_analysis.shots
    shots = report.shot_analysis.model_copy(
        update={
            "duration_us": duration_us,
            "shots": (
                first.model_copy(update={"time_range": TimeRangeUs(start_us=0, end_us=split_us)}),
                second.model_copy(
                    update={
                        "time_range": TimeRangeUs(
                            start_us=split_us,
                            end_us=duration_us,
                        )
                    }
                ),
            ),
        }
    )
    music_section = report.bgm_analysis.sections[0].model_copy(
        update={"time_range": TimeRangeUs(start_us=0, end_us=duration_us)}
    )
    relation = report.bgm_analysis.audiovisual_relations[0].model_copy(
        update={"time_range": TimeRangeUs(start_us=0, end_us=duration_us)}
    )
    return report.model_copy(
        update={
            "report_id": "report_reference_e2e",
            "analysis_id": context.job.analysis_id,
            "source_media_sha256": context.source.file.sha256,
            "analysis_version": context.evidence_bundle.analysis_version,
            "duration_us": duration_us,
            "evidence_bundle": context.evidence_bundle,
            "shot_analysis": shots,
            "bgm_analysis": report.bgm_analysis.model_copy(
                update={
                    "sections": (music_section,),
                    "audiovisual_relations": (relation,),
                }
            ),
        }
    )


def test_real_reference_study_waits_for_confirmation_before_publication(
    tmp_path: Path,
) -> None:
    source = tmp_path / "reference.mp4"
    _make_reference_video(source)
    runner = ReferenceStudyRunner(tmp_path)

    preparation = runner.prepare(
        str(source),
        _agent_report,
        tmp_path / "reports/reference-e2e",
    )

    assert preparation.job.status == "succeeded"
    assert preparation.report_output.manifest_file.path.endswith("reference_report_manifest.json")
    server = create_server(ROOT, tmp_path)
    frame_resource = asyncio.run(
        server.read_resource(f"video-create://analysis/{preparation.job.analysis_id}/frame_000001")
    )
    assert list(frame_resource)[0].content
    assert runner.runtime.knowledge_store.list_all() == ()
    with pytest.raises(PluginError) as caught:
        runner.publish(preparation, user_confirmed=False)
    assert caught.value.code == "knowledge_publication_rejected"
    assert runner.runtime.knowledge_store.list_all() == ()

    publication = runner.publish(preparation, user_confirmed=True)

    assert publication.units
    assert len(runner.runtime.knowledge_store.list_all()) == len(publication.units)
    for unit in publication.units:
        assert unit.source_media_sha256 == preparation.source.file.sha256
        assert (tmp_path / unit.source_report_path).is_file()


def test_stdio_handshake_exposes_reference_tools_and_context(tmp_path: Path) -> None:
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
                    "analysis_start",
                    "analysis_get_job",
                    "analysis_refine_intervals",
                    "analysis_validate_artifact",
                    "report_generate",
                    "knowledge_preview_publication",
                    "knowledge_publish",
                    "knowledge_search",
                } <= tool_names
                resources = await session.list_resources()
                assert "video-create://rules/reference-study-agent" in {
                    str(resource.uri) for resource in resources.resources
                }
                result = await session.call_tool(
                    "reference_resolve_source",
                    {"source": str(source)},
                )
                assert not result.isError
                assert '"ok":true' in result.content[0].text.replace(" ", "")

    asyncio.run(verify())
