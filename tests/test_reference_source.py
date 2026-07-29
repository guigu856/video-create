"""验证本地文件与下载结果统一进入可复现的参考源合同。"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from components.video_download import download_video
from components.video_download import downloader as downloader_module
from video_create_plugin.analysis.source import SourceMediaResolver
from video_create_plugin.errors import PluginError


def _probe_payload() -> str:
    return json.dumps(
        {
            "format": {"duration": "1.250000"},
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                    "time_base": "1/12800",
                    "start_pts": 0,
                    "duration_ts": 16000,
                    "width": 320,
                    "height": 180,
                },
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "time_base": "1/48000",
                    "start_pts": 0,
                    "duration_ts": 60000,
                    "sample_rate": "48000",
                    "channels": 2,
                },
            ],
        }
    )


def _probe_runner(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
    assert argv[0] == "ffprobe"
    return subprocess.CompletedProcess(argv, 0, _probe_payload(), "")


def test_local_and_downloaded_media_share_one_contract(tmp_path: Path) -> None:
    local = tmp_path / "incoming" / "local.mp4"
    local.parent.mkdir()
    local.write_bytes(b"same media")
    downloaded = tmp_path / "downloaded.mp4"
    downloaded.write_bytes(b"download media")

    def fake_download(source: str, config: Any) -> SimpleNamespace:
        assert source == "分享文本 https://example.test/video"
        assert config.output_dir == tmp_path / "output/plugin/sources"
        return SimpleNamespace(file_path=downloaded, source_url="https://example.test/video")

    resolver = SourceMediaResolver(
        tmp_path,
        downloader=fake_download,
        probe_runner=_probe_runner,
    )

    local_result = resolver.resolve(str(local))
    download_result = resolver.resolve("分享文本 https://example.test/video")

    for result in (local_result, download_result):
        assert result.file.path.startswith("output/plugin/sources/")
        assert (tmp_path / result.file.path).is_file()
        assert result.probe.duration_us == 1_250_000
        assert [stream.time_base for stream in result.probe.streams] == [
            "1/12800",
            "1/48000",
        ]
        assert result.source_id == f"source_{result.file.sha256[:16]}"

    assert local_result.source_kind == "local"
    assert local_result.source_url is None
    assert download_result.source_kind == "download"
    assert download_result.source_url == "https://example.test/video"


def test_missing_local_source_has_stable_error(tmp_path: Path) -> None:
    resolver = SourceMediaResolver(tmp_path, probe_runner=_probe_runner)

    with pytest.raises(PluginError) as error:
        resolver.resolve("missing.mp4")

    assert error.value.code == "file_not_found"


def test_async_resolve_isolates_sync_downloader_from_host_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_download(
        url: str,
        output_dir: Path,
        temporary_key: str,
        config: object,
        report: object,
    ) -> downloader_module._DownloadedVideo:
        temporary_path = output_dir / f"{temporary_key}.mp4"
        temporary_path.write_bytes(b"video" * 1000)
        return downloader_module._DownloadedVideo(
            temporary_path=temporary_path,
            platform="Douyin",
            canonical_url="https://www.douyin.com/video/1",
            video_id="1",
            title="事件循环测试",
            author=None,
            duration_seconds=1.25,
            published_at=None,
        )

    monkeypatch.setattr(downloader_module, "_download_douyin", fake_download)
    resolver = SourceMediaResolver(
        tmp_path,
        downloader=download_video,
        probe_runner=_probe_runner,
    )

    result = asyncio.run(
        resolver.resolve_async("分享文本 https://v.douyin.com/event-loop-test/")
    )

    assert result.source_kind == "download"
    assert result.source_url == "https://v.douyin.com/event-loop-test/"
    assert result.probe.duration_us == 1_250_000


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="需要 FFmpeg 工具链",
)
def test_real_ffprobe_smoke_preserves_stream_time_base(tmp_path: Path) -> None:
    media = tmp_path / "real.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:r=25:d=0.4",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            "0.4",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(media),
        ],
        check=True,
    )

    result = SourceMediaResolver(tmp_path).resolve(str(media))

    assert result.probe.duration_us > 0
    assert {stream.codec_type for stream in result.probe.streams} == {"video", "audio"}
    assert all("/" in stream.time_base for stream in result.probe.streams)
