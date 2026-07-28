"""持久编排视频与音频证据步骤，并按内容哈希复用已完成输出。"""

from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path
from typing import Protocol

from components.audio_analysis import AudioAnalysisService
from components.video_analysis import AnalysisInterval, VideoAnalysisService
from video_create_plugin.contracts import FileRef, TimeRangeUs
from video_create_plugin.errors import PluginError
from video_create_plugin.repository.jobs import AnalysisJobRepository

from .jobs import AnalysisFailure, AnalysisJob, AnalysisStep
from .models import SourceMedia


class VideoAnalyzer(Protocol):
    def analyze(self, source: Path, output_dir: Path) -> object: ...

    def refine_intervals(
        self,
        source: Path,
        output_dir: Path,
        *,
        intervals: tuple[AnalysisInterval, ...],
        max_sample_interval_us: int,
    ) -> object: ...


class AudioAnalyzer(Protocol):
    def analyze(self, source: Path, output_dir: Path) -> object: ...


class AnalysisJobService:
    def __init__(
        self,
        workspace_root: Path,
        repository: AnalysisJobRepository,
        *,
        video_service: VideoAnalyzer | None = None,
        audio_service: AudioAnalyzer | None = None,
    ) -> None:
        self._workspace_root = workspace_root.resolve()
        self._repository = repository
        self._video = video_service or VideoAnalysisService()
        self._audio = audio_service or AudioAnalysisService()

    def start(self, source: SourceMedia, *, analysis_id: str | None = None) -> AnalysisJob:
        now = _now_us()
        active_analysis_id = analysis_id or f"analysis_{uuid.uuid4().hex[:16]}"
        job = AnalysisJob(
            job_id=f"job_{uuid.uuid4().hex[:16]}",
            analysis_id=active_analysis_id,
            status="queued",
            progress=0,
            source=source,
            analysis_dir=f"output/plugin/analysis/{active_analysis_id}",
            steps=(AnalysisStep(name="video"), AnalysisStep(name="audio")),
            created_at_us=now,
            updated_at_us=now,
        )
        return self._repository.save(job)

    def run(self, job_id: str) -> AnalysisJob:
        job = self._repository.get(job_id)
        if job.status == "succeeded":
            return job
        if job.status != "queued":
            raise PluginError(
                "analysis_incomplete",
                "只有 queued Job 可以运行",
                details={"job_id": job_id, "status": job.status},
            )
        source_path = self._source_path(job.source)
        job = self._repository.save(
            job.model_copy(update={"status": "running", "error": None, "updated_at_us": _now_us()})
        )
        for step_index, step in enumerate(job.steps):
            input_sha256 = _step_input_sha256(job.source.file.sha256, step.name)
            if (
                step.status == "succeeded"
                and step.input_sha256 == input_sha256
                and step.output is not None
                and self._file_ref_is_valid(step.output)
            ):
                continue
            running_step = step.model_copy(
                update={
                    "status": "running",
                    "input_sha256": input_sha256,
                    "output": None,
                }
            )
            job = self._replace_step(job, step_index, running_step)
            self._repository.save(job)
            try:
                output = self._run_step(job, running_step.name, source_path)
            except Exception as error:
                failed_step = running_step.model_copy(update={"status": "failed"})
                job = self._replace_step(job, step_index, failed_step).model_copy(
                    update={
                        "status": "failed",
                        "error": AnalysisFailure(
                            code="analysis_failed",
                            message=str(error)[:2000] or type(error).__name__,
                        ),
                        "updated_at_us": _now_us(),
                    }
                )
                return self._repository.save(job)
            succeeded_step = running_step.model_copy(
                update={"status": "succeeded", "output": output}
            )
            job = self._replace_step(job, step_index, succeeded_step)
            progress = round(
                sum(item.status == "succeeded" for item in job.steps) / len(job.steps) * 100
            )
            job = job.model_copy(
                update={
                    "progress": progress,
                    f"{running_step.name}_output": output,
                    "updated_at_us": _now_us(),
                }
            )
            self._repository.save(job)
        job = job.model_copy(
            update={
                "status": "succeeded",
                "progress": 100,
                "error": None,
                "updated_at_us": _now_us(),
            }
        )
        return self._repository.save(job)

    def retry(self, job_id: str) -> AnalysisJob:
        job = self._repository.get(job_id)
        if job.status not in {"failed", "interrupted"}:
            raise PluginError("analysis_incomplete", "只有失败或中断 Job 可以重试")
        steps = tuple(
            step.model_copy(update={"status": "pending", "output": None})
            if step.status != "succeeded"
            else step
            for step in job.steps
        )
        self._repository.save(
            job.model_copy(
                update={
                    "status": "queued",
                    "steps": steps,
                    "error": None,
                    "updated_at_us": _now_us(),
                }
            )
        )
        return self.run(job_id)

    def resume_queued(self) -> tuple[AnalysisJob, ...]:
        return tuple(
            self.run(job.job_id) for job in self._repository.list() if job.status == "queued"
        )

    def refine_intervals(
        self,
        job_id: str,
        intervals: tuple[TimeRangeUs, ...],
    ) -> AnalysisJob:
        job = self._repository.get(job_id)
        if job.status != "succeeded":
            raise PluginError("analysis_incomplete", "分析完成后才能细化区间")
        if not intervals:
            raise ValueError("intervals 不得为空")
        source_path = self._source_path(job.source)
        refinement_key = hashlib.sha256(
            (
                job.source.file.sha256
                + "|"
                + "|".join(f"{item.start_us}:{item.end_us}" for item in intervals)
            ).encode("utf-8")
        ).hexdigest()[:16]
        output_dir = self._workspace_root / job.analysis_dir / "refinements" / refinement_key
        self._video.refine_intervals(
            source_path,
            output_dir,
            intervals=tuple(
                AnalysisInterval(start_us=item.start_us, end_us=item.end_us) for item in intervals
            ),
            max_sample_interval_us=100_000,
        )
        output = self._make_file_ref(output_dir / "video_analysis.json")
        refinements = tuple(dict.fromkeys((*job.refinements, output)))
        job = job.model_copy(update={"refinements": refinements, "updated_at_us": _now_us()})
        return self._repository.save(job)

    def _run_step(
        self,
        job: AnalysisJob,
        step_name: str,
        source_path: Path,
    ) -> FileRef:
        output_dir = self._workspace_root / job.analysis_dir / step_name
        if step_name == "video":
            self._video.analyze(source_path, output_dir)
            return self._make_file_ref(output_dir / "video_analysis.json")
        self._audio.analyze(source_path, output_dir)
        return self._make_file_ref(output_dir / "audio_analysis.json")

    def _source_path(self, source: SourceMedia) -> Path:
        path = (self._workspace_root / source.file.path).resolve()
        if not path.is_relative_to(self._workspace_root) or not path.is_file():
            raise PluginError("file_not_found", "分析源文件不存在")
        if _sha256(path) != source.file.sha256:
            raise PluginError("file_hash_mismatch", "分析源文件哈希不匹配")
        return path

    def _make_file_ref(self, path: Path) -> FileRef:
        if not path.is_file():
            raise FileNotFoundError(path)
        return FileRef(
            path=path.relative_to(self._workspace_root).as_posix(),
            sha256=_sha256(path),
            schema_version="1.0",
        )

    def _file_ref_is_valid(self, reference: FileRef) -> bool:
        path = self._workspace_root / reference.path
        return path.is_file() and _sha256(path) == reference.sha256

    @staticmethod
    def _replace_step(
        job: AnalysisJob,
        index: int,
        replacement: AnalysisStep,
    ) -> AnalysisJob:
        steps = list(job.steps)
        steps[index] = replacement
        return job.model_copy(update={"steps": tuple(steps), "updated_at_us": _now_us()})


def _step_input_sha256(source_sha256: str, step_name: str) -> str:
    return hashlib.sha256(f"{source_sha256}|{step_name}|evidence-1.0".encode()).hexdigest()


def _now_us() -> int:
    return time.time_ns() // 1000


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
