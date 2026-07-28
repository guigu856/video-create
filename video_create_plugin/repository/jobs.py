"""使用原子 JSON 文件持久化分析 Job。"""

from __future__ import annotations

import time
from pathlib import Path

from video_create_plugin.analysis.jobs import AnalysisFailure, AnalysisJob
from video_create_plugin.errors import PluginError


class AnalysisJobRepository:
    def __init__(self, workspace_root: Path, jobs_dir: Path | None = None) -> None:
        self._workspace_root = workspace_root.resolve()
        self._jobs_dir = (
            jobs_dir.resolve()
            if jobs_dir is not None
            else self._workspace_root / "output/plugin/jobs"
        )
        if not self._jobs_dir.is_relative_to(self._workspace_root):
            raise ValueError("jobs_dir 必须位于 workspace_root 内")
        self._interrupt_running_jobs()

    def save(self, job: AnalysisJob) -> AnalysisJob:
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        target = self._path(job.job_id)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(job.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
        return job

    def get(self, job_id: str) -> AnalysisJob:
        path = self._path(job_id)
        if not path.is_file():
            raise PluginError(
                "analysis_job_not_found",
                "分析 Job 不存在",
                details={"job_id": job_id},
            )
        return AnalysisJob.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> tuple[AnalysisJob, ...]:
        if not self._jobs_dir.is_dir():
            return ()
        return tuple(
            sorted(
                (
                    AnalysisJob.model_validate_json(path.read_text(encoding="utf-8"))
                    for path in self._jobs_dir.glob("*.json")
                ),
                key=lambda job: (job.created_at_us, job.job_id),
            )
        )

    def _interrupt_running_jobs(self) -> None:
        for job in self.list():
            if job.status != "running":
                continue
            self.save(
                job.model_copy(
                    update={
                        "status": "interrupted",
                        "error": AnalysisFailure(
                            code="job_interrupted",
                            message="MCP Server 重启时分析仍在运行",
                        ),
                        "updated_at_us": time.time_ns() // 1000,
                    }
                )
            )

    def _path(self, job_id: str) -> Path:
        return self._jobs_dir / f"{job_id}.json"
