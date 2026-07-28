"""确定性音频证据的数据合同。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AudioAnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AudioTimeRange(AudioAnalysisModel):
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)

    @model_validator(mode="after")
    def end_is_after_start(self) -> "AudioTimeRange":
        if self.end_us <= self.start_us:
            raise ValueError("end_us 必须大于 start_us")
        return self


class AudioEvidenceFile(AudioAnalysisModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class TempoCandidate(AudioAnalysisModel):
    status: Literal["algorithm_candidate"] = "algorithm_candidate"
    bpm: float = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    method: Literal["transient_interval"] = "transient_interval"


class BeatCandidate(AudioAnalysisModel):
    status: Literal["algorithm_candidate"] = "algorithm_candidate"
    timestamp_us: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)


class SoundEventCandidate(AudioAnalysisModel):
    status: Literal["algorithm_candidate"] = "algorithm_candidate"
    candidate_type: Literal["transient", "silence"]
    time_range: AudioTimeRange
    confidence: float = Field(ge=0, le=1)


class AudioAnalysisResult(AudioAnalysisModel):
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    algorithm_version: Literal["audio-evidence-1.0"] = "audio-evidence-1.0"
    audio_scope: Literal["mixed_program_audio", "isolated_bgm"]
    sample_rate: int = Field(gt=0)
    source_channels: int = Field(gt=0)
    analysis_channels: Literal[1] = 1
    time_range: AudioTimeRange
    pcm: AudioEvidenceFile
    waveform: AudioEvidenceFile
    waveform_visualization: AudioEvidenceFile
    signals: AudioEvidenceFile
    tempo_candidates: tuple[TempoCandidate, ...]
    beat_candidates: tuple[BeatCandidate, ...]
    sound_event_candidates: tuple[SoundEventCandidate, ...]
