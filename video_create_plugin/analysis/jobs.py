"""持久分析 Job 的最小状态合同。"""

from typing import Literal

from pydantic import Field

from video_create_plugin.contracts import FileRef, PluginModel, StableId

from .models import SourceMedia

JobStatus = Literal["queued", "running", "succeeded", "failed", "interrupted"]
StepStatus = Literal["pending", "running", "succeeded", "failed"]


class AnalysisFailure(PluginModel):
    code: StableId
    message: str = Field(min_length=1, max_length=2000)


class AnalysisStep(PluginModel):
    name: Literal["video", "audio"]
    status: StepStatus = "pending"
    input_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    output: FileRef | None = None


class AnalysisJob(PluginModel):
    job_id: StableId
    analysis_id: StableId
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    source: SourceMedia
    analysis_dir: str = Field(min_length=1)
    steps: tuple[AnalysisStep, ...]
    video_output: FileRef | None = None
    audio_output: FileRef | None = None
    refinements: tuple[FileRef, ...] = ()
    error: AnalysisFailure | None = None
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)
