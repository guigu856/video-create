"""验证音频分析组件输出候选证据而不写入声音语义判断。"""

from __future__ import annotations

import math
import shutil
import struct
import wave
from pathlib import Path

import pytest

from components.audio_analysis import AudioAnalysisService

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="需要 FFmpeg 工具链",
)


def _write_click_track(path: Path, *, silent: bool = False) -> None:
    sample_rate = 8_000
    samples: list[int] = []
    for index in range(sample_rate * 2):
        position = index % (sample_rate // 2)
        active = not silent and position < sample_rate // 25
        value = int(0.8 * 32767 * math.sin(2 * math.pi * 440 * index / sample_rate))
        samples.append(value if active else 0)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"".join(struct.pack("<h", value) for value in samples))


def test_click_track_produces_candidate_tempo_beats_and_waveform(tmp_path: Path) -> None:
    source = tmp_path / "clicks.wav"
    _write_click_track(source)

    result = AudioAnalysisService().analyze(
        source,
        tmp_path / "evidence",
        audio_scope="isolated_bgm",
    )

    assert result.sample_rate == 8_000
    assert result.source_channels == 1
    assert result.analysis_channels == 1
    assert result.time_range.start_us == 0
    assert 1_900_000 <= result.time_range.end_us <= 2_000_000
    assert result.pcm.sha256
    assert (tmp_path / "evidence" / result.waveform.path).is_file()
    assert (tmp_path / "evidence" / result.waveform_visualization.path).is_file()
    assert result.tempo_candidates
    assert result.tempo_candidates[0].status == "algorithm_candidate"
    assert result.tempo_candidates[0].bpm == pytest.approx(120, abs=2)
    assert result.tempo_candidates[0].confidence > 0.8
    assert len(result.beat_candidates) >= 3
    assert {event.candidate_type for event in result.sound_event_candidates} <= {
        "transient",
        "silence",
    }


def test_silence_has_no_tempo_or_beat_claim(tmp_path: Path) -> None:
    source = tmp_path / "silence.wav"
    _write_click_track(source, silent=True)

    result = AudioAnalysisService().analyze(source, tmp_path / "silence-evidence")

    assert result.audio_scope == "mixed_program_audio"
    assert result.tempo_candidates == ()
    assert result.beat_candidates == ()
    assert any(
        event.candidate_type == "silence"
        and event.time_range.start_us == 0
        and event.time_range.end_us == result.time_range.end_us
        for event in result.sound_event_candidates
    )
