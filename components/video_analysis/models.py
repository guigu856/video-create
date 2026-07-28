"""确定性视频证据的数据合同。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AnalysisInterval(AnalysisModel):
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)

    @model_validator(mode="after")
    def end_is_after_start(self) -> "AnalysisInterval":
        if self.end_us <= self.start_us:
            raise ValueError("end_us 必须大于 start_us")
        return self


class EvidenceFile(AnalysisModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class TimestampRef(AnalysisModel):
    pts: int
    time_base: str = Field(pattern=r"^\d+/\d+$")
    frame_index: int | None = Field(default=None, ge=0)
    timestamp_us: int = Field(ge=0)


class FrameEvidence(AnalysisModel):
    evidence_id: str = Field(pattern=r"^frame_[0-9]{6}$")
    timestamp: TimestampRef
    file: EvidenceFile


class VisualSignal(AnalysisModel):
    timestamp: TimestampRef
    frame_difference: float = Field(ge=0, le=1)


class BoundaryCandidate(AnalysisModel):
    evidence_id: str = Field(pattern=r"^boundary_[0-9]{6}$")
    status: Literal["algorithm_candidate"] = "algorithm_candidate"
    timestamp: TimestampRef
    confidence: float = Field(ge=0, le=1)


class VideoAnalysisResult(AnalysisModel):
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    algorithm_version: Literal["video-evidence-1.0"] = "video-evidence-1.0"
    max_sample_interval_us: int = Field(gt=0)
    time_range: AnalysisInterval
    frame_index: EvidenceFile
    visual_signals: EvidenceFile
    boundary_candidates_file: EvidenceFile
    frames: tuple[FrameEvidence, ...] = Field(min_length=1)
    boundary_candidates: tuple[BoundaryCandidate, ...]
    contact_sheet: EvidenceFile
