"""参考来源、媒体探测与确定性分析证据的稳定数据合同。"""

from typing import Literal

from pydantic import Field, model_validator

from video_create_plugin.contracts import FileRef, PluginModel, StableId, TimeRangeUs


class MediaStream(PluginModel):
    index: int = Field(ge=0)
    codec_type: Literal["video", "audio"]
    codec_name: str = Field(min_length=1)
    time_base: str = Field(pattern=r"^\d+/\d+$")
    start_pts: int | None = None
    duration_ts: int | None = Field(default=None, ge=0)
    duration_us: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    sample_rate: int | None = Field(default=None, gt=0)
    channels: int | None = Field(default=None, gt=0)


class MediaProbe(PluginModel):
    duration_us: int = Field(gt=0)
    streams: tuple[MediaStream, ...] = Field(min_length=1)


class SourceMedia(PluginModel):
    source_id: StableId
    source_kind: Literal["local", "download"]
    original_input: str = Field(min_length=1)
    source_url: str | None = None
    file: FileRef
    probe: MediaProbe


class EvidenceEntry(PluginModel):
    evidence_id: StableId
    evidence_type: Literal[
        "frame",
        "contact_sheet",
        "frame_index",
        "visual_signals",
        "boundary_candidates",
        "audio_pcm",
        "waveform",
        "waveform_visualization",
        "audio_signals",
        "refinement",
    ]
    file: FileRef
    time_range: TimeRangeUs | None = None
    fact_status: Literal["measured", "algorithm_candidate"]
    algorithm_version: str | None = Field(default=None, min_length=1)


class EvidenceBundle(PluginModel):
    analysis_id: StableId
    source_media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_version: str = Field(min_length=1)
    entries: tuple[EvidenceEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def entries_are_unique(self) -> "EvidenceBundle":
        evidence_ids = [entry.evidence_id for entry in self.entries]
        paths = [entry.file.path for entry in self.entries]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("EvidenceBundle evidence_id 必须唯一")
        if len(paths) != len(set(paths)):
            raise ValueError("EvidenceBundle 文件路径必须唯一")
        return self
