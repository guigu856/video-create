"""验证视频分析组件只生成基于真实 PTS 的确定性证据。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from components.video_analysis import AnalysisInterval, VideoAnalysisService

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="需要 FFmpeg 工具链",
)


def _make_cut_video(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:r=10:d=0.5",
            "-f",
            "lavfi",
            "-i",
            "color=c=white:s=160x90:r=10:d=0.5",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )


def test_video_analysis_emits_pts_frames_candidates_and_contact_sheet(
    tmp_path: Path,
) -> None:
    source = tmp_path / "cut.mp4"
    _make_cut_video(source)

    result = VideoAnalysisService().analyze(
        source,
        tmp_path / "evidence",
        max_sample_interval_us=200_000,
    )

    assert result.frames
    assert result.frames[0].timestamp.pts == 0
    assert result.frames[0].timestamp.time_base == "1/10240"
    assert all(frame.file.sha256 for frame in result.frames)
    assert all((tmp_path / "evidence" / frame.file.path).is_file() for frame in result.frames)
    assert (tmp_path / "evidence" / result.contact_sheet.path).is_file()
    assert any(
        candidate.status == "algorithm_candidate"
        and 400_000 <= candidate.timestamp.timestamp_us <= 600_000
        for candidate in result.boundary_candidates
    )


def test_refinement_honors_dense_sampling_interval(tmp_path: Path) -> None:
    source = tmp_path / "cut.mp4"
    _make_cut_video(source)

    result = VideoAnalysisService().refine_intervals(
        source,
        tmp_path / "refined",
        intervals=(AnalysisInterval(start_us=300_000, end_us=700_000),),
        max_sample_interval_us=100_000,
    )

    timestamps = [frame.timestamp.timestamp_us for frame in result.frames]
    assert timestamps
    assert min(timestamps) >= 300_000
    assert max(timestamps) <= 700_000
    assert all(right - left <= 100_000 for left, right in zip(timestamps, timestamps[1:]))


def test_dense_contact_sheet_uses_frame_count_based_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run_ffmpeg(
        args: list[str],
        *,
        capture_output: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        del capture_output, check
        if timeout <= 60:
            raise subprocess.TimeoutExpired(args, timeout)
        Path(args[-1]).write_bytes(b"contact-sheet")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", run_ffmpeg)

    path = VideoAnalysisService()._create_contact_sheet(tmp_path, frame_count=112)

    assert path.is_file()


def test_refinement_rejects_interval_over_one_tenth_second() -> None:
    with pytest.raises(ValueError, match="100000"):
        VideoAnalysisService().refine_intervals(
            "source.mp4",
            "evidence",
            intervals=(AnalysisInterval(start_us=0, end_us=1_000_000),),
            max_sample_interval_us=100_001,
        )


def test_analysis_interval_rejects_empty_range() -> None:
    with pytest.raises(ValidationError):
        AnalysisInterval(start_us=10, end_us=10)
