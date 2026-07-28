"""提取 PCM、波形、能量、瞬态、节拍和声音事件候选。"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import subprocess
import sys
from array import array
from pathlib import Path
from typing import Any, Literal

from .models import (
    AudioAnalysisResult,
    AudioEvidenceFile,
    AudioTimeRange,
    BeatCandidate,
    SoundEventCandidate,
    TempoCandidate,
)


class AudioAnalysisService:
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
        audio_scope: Literal["mixed_program_audio", "isolated_bgm"] = ("mixed_program_audio"),
    ) -> AudioAnalysisResult:
        source_path = Path(source).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        evidence_dir = Path(output_dir).resolve()
        evidence_dir.mkdir(parents=True, exist_ok=True)

        sample_rate, source_channels = self._probe_audio(source_path)
        pcm_path = evidence_dir / "audio_mono_s16le.pcm"
        pcm_path.write_bytes(self._extract_pcm(source_path, sample_rate))
        samples = _read_samples(pcm_path)
        if not samples:
            raise ValueError("音轨不包含可分析采样")
        duration_us = round(len(samples) / sample_rate * 1_000_000)
        windows = _waveform_windows(samples, sample_rate)
        transient_times = _transient_times(windows)
        tempo_candidates, beat_candidates = _rhythm_candidates(transient_times)
        event_candidates = _event_candidates(windows, transient_times, duration_us)

        waveform_path = evidence_dir / "waveform.json"
        waveform_path.write_text(
            json.dumps(windows, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        visualization_path = evidence_dir / "waveform.svg"
        visualization_path.write_text(_waveform_svg(windows), encoding="utf-8")
        signals_path = evidence_dir / "audio_signals.json"
        signals_path.write_text(
            json.dumps(
                {
                    "tempo_candidates": [item.model_dump(mode="json") for item in tempo_candidates],
                    "beat_candidates": [item.model_dump(mode="json") for item in beat_candidates],
                    "sound_event_candidates": [
                        item.model_dump(mode="json") for item in event_candidates
                    ],
                    "energy_curve": [
                        {
                            "start_us": window["start_us"],
                            "end_us": window["end_us"],
                            "rms": window["rms"],
                        }
                        for window in windows
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        result = AudioAnalysisResult(
            source_sha256=_sha256(source_path),
            audio_scope=audio_scope,
            sample_rate=sample_rate,
            source_channels=source_channels,
            time_range=AudioTimeRange(start_us=0, end_us=duration_us),
            pcm=_file_ref(evidence_dir, pcm_path),
            waveform=_file_ref(evidence_dir, waveform_path),
            waveform_visualization=_file_ref(evidence_dir, visualization_path),
            signals=_file_ref(evidence_dir, signals_path),
            tempo_candidates=tempo_candidates,
            beat_candidates=beat_candidates,
            sound_event_candidates=event_candidates,
        )
        (evidence_dir / "audio_analysis.json").write_text(
            result.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        return result

    def _probe_audio(self, source: Path) -> tuple[int, int]:
        completed = subprocess.run(
            [
                self._ffprobe_binary,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=sample_rate,channels",
                "-of",
                "json",
                str(source),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"ffprobe 音频分析失败：{completed.stderr[-2000:]}")
        try:
            stream = json.loads(completed.stdout)["streams"][0]
            return int(stream["sample_rate"]), int(stream["channels"])
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise ValueError("媒体不包含可分析音轨") from error

    def _extract_pcm(self, source: Path, sample_rate: int) -> bytes:
        completed = subprocess.run(
            [
                self._ffmpeg_binary,
                "-v",
                "error",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-f",
                "s16le",
                "-acodec",
                "pcm_s16le",
                "pipe:1",
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            message = completed.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"ffmpeg 音频提取失败：{message[-2000:]}")
        return completed.stdout


def _read_samples(path: Path) -> array[int]:
    samples = array("h")
    samples.frombytes(path.read_bytes())
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def _waveform_windows(samples: array[int], sample_rate: int) -> list[dict[str, Any]]:
    window_size = max(1, round(sample_rate * 0.02))
    windows: list[dict[str, Any]] = []
    for start in range(0, len(samples), window_size):
        chunk = samples[start : start + window_size]
        normalized = [sample / 32768 for sample in chunk]
        rms = math.sqrt(sum(sample * sample for sample in normalized) / len(normalized))
        windows.append(
            {
                "start_us": round(start / sample_rate * 1_000_000),
                "end_us": round(min(start + window_size, len(samples)) / sample_rate * 1_000_000),
                "rms": round(rms, 8),
                "peak": round(max((abs(sample) for sample in normalized), default=0), 8),
            }
        )
    return windows


def _transient_times(windows: list[dict[str, Any]]) -> tuple[int, ...]:
    candidates: list[int] = []
    previous = 0.0
    for window in windows:
        rms = float(window["rms"])
        timestamp = int(window["start_us"])
        if rms >= 0.05 and rms - previous >= max(0.04, previous):
            if not candidates or timestamp - candidates[-1] >= 100_000:
                candidates.append(timestamp)
        previous = rms
    return tuple(candidates)


def _rhythm_candidates(
    transient_times: tuple[int, ...],
) -> tuple[tuple[TempoCandidate, ...], tuple[BeatCandidate, ...]]:
    if len(transient_times) < 3:
        return (), ()
    intervals = [right - left for left, right in zip(transient_times, transient_times[1:])]
    median_interval = statistics.median(intervals)
    if median_interval <= 0:
        return (), ()
    bpm = 60_000_000 / median_interval
    while bpm < 60:
        bpm *= 2
    while bpm > 200:
        bpm /= 2
    mean_deviation = statistics.fmean(
        abs(interval - median_interval) / median_interval for interval in intervals
    )
    confidence = max(0.0, min(1.0, 1 - mean_deviation))
    tempo = (TempoCandidate(bpm=round(bpm, 4), confidence=confidence),)
    beats = tuple(
        BeatCandidate(timestamp_us=timestamp, confidence=confidence)
        for timestamp in transient_times
    )
    return tempo, beats


def _event_candidates(
    windows: list[dict[str, Any]],
    transient_times: tuple[int, ...],
    duration_us: int,
) -> tuple[SoundEventCandidate, ...]:
    events = [
        SoundEventCandidate(
            candidate_type="transient",
            time_range=AudioTimeRange(
                start_us=timestamp,
                end_us=min(duration_us, timestamp + 20_000),
            ),
            confidence=0.8,
        )
        for timestamp in transient_times
        if timestamp < duration_us
    ]
    silence_start: int | None = None
    for window in windows:
        is_silent = float(window["rms"]) <= 0.002
        if is_silent and silence_start is None:
            silence_start = int(window["start_us"])
        if not is_silent and silence_start is not None:
            end_us = int(window["start_us"])
            if end_us - silence_start >= 100_000:
                events.append(_silence_event(silence_start, end_us))
            silence_start = None
    if silence_start is not None and duration_us - silence_start >= 100_000:
        events.append(_silence_event(silence_start, duration_us))
    return tuple(sorted(events, key=lambda item: item.time_range.start_us))


def _silence_event(start_us: int, end_us: int) -> SoundEventCandidate:
    return SoundEventCandidate(
        candidate_type="silence",
        time_range=AudioTimeRange(start_us=start_us, end_us=end_us),
        confidence=1,
    )


def _waveform_svg(windows: list[dict[str, Any]]) -> str:
    width = 1000
    height = 240
    points = []
    denominator = max(1, len(windows) - 1)
    for index, window in enumerate(windows):
        x = round(index / denominator * width, 2)
        y = round(height / 2 - float(window["peak"]) * (height / 2 - 4), 2)
        points.append(f"{x},{y}")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}">'
        f'<polyline fill="none" stroke="#2563eb" points="{" ".join(points)}"/>'
        "</svg>\n"
    )


def _file_ref(root: Path, path: Path) -> AudioEvidenceFile:
    return AudioEvidenceFile(path=path.relative_to(root).as_posix(), sha256=_sha256(path))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
