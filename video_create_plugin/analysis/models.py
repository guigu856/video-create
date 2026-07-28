"""参考来源、媒体探测与分析任务的稳定数据合同。"""

from typing import Literal

from pydantic import Field

from video_create_plugin.contracts import FileRef, PluginModel, StableId


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
