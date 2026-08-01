"""从真实 PTS 生成帧、视觉信号、联系表和候选切点。"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path

from .models import (
    AnalysisInterval,
    BoundaryCandidate,
    EvidenceFile,
    FrameEvidence,
    TimestampRef,
    VideoAnalysisResult,
    VisualSignal,
)


class VideoAnalysisService:
    def __init__(
        self,
        *,
        ffmpeg_binary: str = "ffmpeg",
        ffprobe_binary: str = "ffprobe",
    ) -> None:
        self._ffmpeg_binary = ffmpeg_binary
        self._ffprobe_binary = ffprobe_binary

    def analyze(
        self,
        source: Path | str,
        output_dir: Path | str,
        *,
        max_sample_interval_us: int = 1_000_000,
        intervals: tuple[AnalysisInterval, ...] | None = None,
    ) -> VideoAnalysisResult:
        if max_sample_interval_us <= 0:
            raise ValueError("max_sample_interval_us 必须大于 0")
        source_path = Path(source).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        evidence_dir = Path(output_dir).resolve()
        evidence_dir.mkdir(parents=True, exist_ok=True)

        time_base, frame_index = self._probe_frames(source_path)
        if not frame_index:
            raise ValueError("视频不包含可分析帧")
        active_intervals = intervals or (
            AnalysisInterval(
                start_us=frame_index[0].timestamp_us,
                end_us=max(frame_index[-1].timestamp_us + 1, frame_index[0].timestamp_us + 1),
            ),
        )
        selected = _select_frames(frame_index, active_intervals, max_sample_interval_us)
        if not selected:
            raise ValueError("指定区间内没有视频帧")

        frame_index_path = evidence_dir / "frame_index.jsonl"
        frame_index_path.write_text(
            "".join(f"{item.model_dump_json()}\n" for item in frame_index),
            encoding="utf-8",
        )
        frames, gray_frames = self._extract_frames(source_path, evidence_dir, selected)
        signals = _visual_signals(selected, gray_frames)
        candidates = tuple(
            BoundaryCandidate(
                evidence_id=f"boundary_{index:06d}",
                timestamp=signal.timestamp,
                confidence=signal.frame_difference,
            )
            for index, signal in enumerate(signals, start=1)
            if signal.frame_difference >= 0.2
        )
        visual_path = evidence_dir / "visual_signals.json"
        visual_path.write_text(
            json.dumps(
                [item.model_dump(mode="json") for item in signals],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        boundaries_path = evidence_dir / "boundary_candidates.json"
        boundaries_path.write_text(
            json.dumps(
                [item.model_dump(mode="json") for item in candidates],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        contact_sheet_path = self._create_contact_sheet(evidence_dir, len(frames))
        result = VideoAnalysisResult(
            source_sha256=_sha256(source_path),
            max_sample_interval_us=max_sample_interval_us,
            time_range=AnalysisInterval(
                start_us=min(interval.start_us for interval in active_intervals),
                end_us=max(interval.end_us for interval in active_intervals),
            ),
            frame_index=_file_ref(evidence_dir, frame_index_path),
            visual_signals=_file_ref(evidence_dir, visual_path),
            boundary_candidates_file=_file_ref(evidence_dir, boundaries_path),
            frames=frames,
            boundary_candidates=candidates,
            contact_sheet=_file_ref(evidence_dir, contact_sheet_path),
        )
        (evidence_dir / "video_analysis.json").write_text(
            result.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        return result

    def refine_intervals(
        self,
        source: Path | str,
        output_dir: Path | str,
        *,
        intervals: tuple[AnalysisInterval, ...],
        max_sample_interval_us: int = 100_000,
    ) -> VideoAnalysisResult:
        if max_sample_interval_us > 100_000:
            raise ValueError("细化取证 max_sample_interval_us 不得大于 100000")
        return self.analyze(
            source,
            output_dir,
            max_sample_interval_us=max_sample_interval_us,
            intervals=intervals,
        )

    def _probe_frames(self, source: Path) -> tuple[str, tuple[TimestampRef, ...]]:
        completed = subprocess.run(
            [
                self._ffprobe_binary,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=time_base:frame=pts,best_effort_timestamp,best_effort_timestamp_time",
                "-show_frames",
                "-of",
                "json",
                str(source),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"ffprobe 视频分析失败：{completed.stderr[-2000:]}")
        payload = json.loads(completed.stdout)
        time_base = str(payload["streams"][0]["time_base"])
        fraction = Fraction(time_base)
        frames: list[TimestampRef] = []
        for index, frame in enumerate(payload.get("frames", [])):
            pts_value = frame.get("best_effort_timestamp", frame.get("pts"))
            if pts_value is None:
                continue
            pts = int(pts_value)
            frames.append(
                TimestampRef(
                    pts=pts,
                    time_base=time_base,
                    frame_index=index,
                    timestamp_us=max(0, round(pts * fraction * 1_000_000)),
                )
            )
        return time_base, tuple(frames)

    def _extract_frames(
        self,
        source: Path,
        output_dir: Path,
        selected: tuple[TimestampRef, ...],
    ) -> tuple[tuple[FrameEvidence, ...], tuple[bytes, ...]]:
        frames_dir = output_dir / "frames"
        frames_dir.mkdir(exist_ok=True)
        evidence: list[FrameEvidence] = []
        gray_frames: list[bytes] = []
        for index, timestamp in enumerate(selected, start=1):
            path = frames_dir / f"frame_{index:06d}.jpg"
            seconds = f"{timestamp.timestamp_us / 1_000_000:.6f}"
            self._run_ffmpeg(
                [
                    "-ss",
                    seconds,
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    str(path),
                ]
            )
            gray = self._run_ffmpeg(
                [
                    "-ss",
                    seconds,
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=64:36",
                    "-pix_fmt",
                    "gray",
                    "-f",
                    "rawvideo",
                    "pipe:1",
                ],
                binary=True,
            )
            evidence.append(
                FrameEvidence(
                    evidence_id=f"frame_{index:06d}",
                    timestamp=timestamp,
                    file=_file_ref(output_dir, path),
                )
            )
            gray_frames.append(gray)
        return tuple(evidence), tuple(gray_frames)

    def _create_contact_sheet(self, output_dir: Path, frame_count: int) -> Path:
        columns = min(4, frame_count)
        rows = math.ceil(frame_count / columns)
        path = output_dir / "contact_sheet.jpg"
        self._run_ffmpeg(
            [
                "-framerate",
                "1",
                "-i",
                str(output_dir / "frames/frame_%06d.jpg"),
                "-vf",
                f"scale=320:-1,tile={columns}x{rows}:padding=4:margin=4",
                "-frames:v",
                "1",
                str(path),
            ],
            timeout_seconds=max(60, frame_count * 2),
        )
        return path

    def _run_ffmpeg(
        self,
        args: list[str],
        *,
        binary: bool = False,
        timeout_seconds: int = 60,
    ) -> bytes:
        completed = subprocess.run(
            [self._ffmpeg_binary, "-v", "error", "-y", *args],
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            message = completed.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"ffmpeg 视频取证失败：{message[-2000:]}")
        return completed.stdout if binary else b""


def _select_frames(
    frames: tuple[TimestampRef, ...],
    intervals: tuple[AnalysisInterval, ...],
    max_interval_us: int,
) -> tuple[TimestampRef, ...]:
    selected: list[TimestampRef] = []
    for interval in intervals:
        candidates = [
            frame for frame in frames if interval.start_us <= frame.timestamp_us <= interval.end_us
        ]
        previous: TimestampRef | None = None
        for frame in candidates:
            if previous is None or frame.timestamp_us - previous.timestamp_us >= max_interval_us:
                selected.append(frame)
                previous = frame
        if candidates and selected[-1] != candidates[-1]:
            selected.append(candidates[-1])
    return tuple(dict.fromkeys(selected))


def _visual_signals(
    timestamps: tuple[TimestampRef, ...],
    gray_frames: tuple[bytes, ...],
) -> tuple[VisualSignal, ...]:
    signals: list[VisualSignal] = []
    for timestamp, previous, current in zip(timestamps[1:], gray_frames, gray_frames[1:]):
        length = min(len(previous), len(current))
        difference = (
            sum(abs(previous[index] - current[index]) for index in range(length)) / (length * 255)
            if length
            else 0
        )
        signals.append(VisualSignal(timestamp=timestamp, frame_difference=difference))
    return tuple(signals)


def _file_ref(root: Path, path: Path) -> EvidenceFile:
    return EvidenceFile(path=path.relative_to(root).as_posix(), sha256=_sha256(path))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
