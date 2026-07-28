"""验证分析 Job 的持久状态、重启恢复、步骤复用与区间细化。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from video_create_plugin.analysis.jobs import AnalysisJob, AnalysisStep
from video_create_plugin.analysis.models import MediaProbe, MediaStream, SourceMedia
from video_create_plugin.analysis.service import AnalysisJobService
from video_create_plugin.contracts import FileRef, TimeRangeUs
from video_create_plugin.repository.jobs import AnalysisJobRepository


class FakeVideoService:
    def __init__(self) -> None:
        self.analyze_calls = 0
        self.refine_calls: list[tuple[tuple[Any, ...], int]] = []

    def analyze(self, source: Path, output_dir: Path) -> None:
        self.analyze_calls += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "video_analysis.json").write_text(
            '{"kind":"video"}\n',
            encoding="utf-8",
        )

    def refine_intervals(
        self,
        source: Path,
        output_dir: Path,
        *,
        intervals: tuple[Any, ...],
        max_sample_interval_us: int,
    ) -> None:
        self.refine_calls.append((intervals, max_sample_interval_us))
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "video_analysis.json").write_text(
            '{"kind":"refinement"}\n',
            encoding="utf-8",
        )


class FlakyAudioService:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, source: Path, output_dir: Path) -> None:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("synthetic audio failure")
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "audio_analysis.json").write_text(
            '{"kind":"audio"}\n',
            encoding="utf-8",
        )


def _source_media(root: Path) -> SourceMedia:
    source_path = root / "output/plugin/sources/source.mp4"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"source")
    sha256 = hashlib.sha256(b"source").hexdigest()
    return SourceMedia(
        source_id="source_1234567890abcdef",
        source_kind="local",
        original_input=str(source_path),
        file=FileRef(path="output/plugin/sources/source.mp4", sha256=sha256),
        probe=MediaProbe(
            duration_us=1_000_000,
            streams=(
                MediaStream(
                    index=0,
                    codec_type="video",
                    codec_name="h264",
                    time_base="1/1000",
                ),
            ),
        ),
    )


def test_failed_job_reuses_completed_content_hash_step_on_retry(tmp_path: Path) -> None:
    repository = AnalysisJobRepository(tmp_path)
    video = FakeVideoService()
    audio = FlakyAudioService()
    service = AnalysisJobService(
        tmp_path,
        repository,
        video_service=video,
        audio_service=audio,
    )
    job = service.start(_source_media(tmp_path))

    failed = service.run(job.job_id)
    recovered = service.retry(job.job_id)

    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.code == "analysis_failed"
    assert recovered.status == "succeeded"
    assert recovered.progress == 100
    assert video.analyze_calls == 1
    assert audio.calls == 2
    assert recovered.video_output is not None
    assert recovered.audio_output is not None
    assert recovered.video_output.path.startswith(f"output/plugin/analysis/{job.analysis_id}/")
    assert repository.get(job.job_id) == recovered


def test_restart_interrupts_running_and_resumes_queued_jobs(tmp_path: Path) -> None:
    source = _source_media(tmp_path)
    repository = AnalysisJobRepository(tmp_path)
    service = AnalysisJobService(
        tmp_path,
        repository,
        video_service=FakeVideoService(),
        audio_service=FlakyAudioService(),
    )
    queued = service.start(source)
    running = service.start(source)
    repository.save(
        running.model_copy(update={"status": "running", "steps": (AnalysisStep(name="video"),)})
    )

    restarted_repository = AnalysisJobRepository(tmp_path)
    interrupted = restarted_repository.get(running.job_id)
    assert interrupted.status == "interrupted"
    assert interrupted.error is not None
    assert interrupted.error.code == "job_interrupted"
    assert restarted_repository.get(queued.job_id).status == "queued"

    resumed_service = AnalysisJobService(
        tmp_path,
        restarted_repository,
        video_service=FakeVideoService(),
        audio_service=FakeAudioService(),
    )
    resumed = resumed_service.resume_queued()
    assert [job.job_id for job in resumed] == [queued.job_id]
    assert resumed[0].status == "succeeded"


class FakeAudioService:
    def analyze(self, source: Path, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "audio_analysis.json").write_text("{}\n", encoding="utf-8")


def test_refinement_persists_only_analysis_evidence_reference(tmp_path: Path) -> None:
    repository = AnalysisJobRepository(tmp_path)
    video = FakeVideoService()
    service = AnalysisJobService(
        tmp_path,
        repository,
        video_service=video,
        audio_service=FakeAudioService(),
    )
    job = service.start(_source_media(tmp_path))
    succeeded = service.run(job.job_id)

    refined = service.refine_intervals(
        succeeded.job_id,
        (TimeRangeUs(start_us=100_000, end_us=300_000),),
    )

    assert len(refined.refinements) == 1
    assert refined.refinements[0].path.startswith(
        f"output/plugin/analysis/{job.analysis_id}/refinements/"
    )
    assert video.refine_calls[0][1] == 100_000
    assert video.refine_calls[0][0][0].start_us == 100_000
    assert (tmp_path / refined.refinements[0].path).is_file()


def test_repository_round_trips_all_persisted_states(tmp_path: Path) -> None:
    repository = AnalysisJobRepository(tmp_path)
    source = _source_media(tmp_path)
    for index, status in enumerate(("queued", "running", "succeeded", "failed"), start=1):
        job = AnalysisJob(
            job_id=f"job_state_{index}",
            analysis_id=f"analysis_state_{index}",
            status=status,
            progress=0,
            source=source,
            analysis_dir=f"output/plugin/analysis/analysis_state_{index}",
            steps=(),
            created_at_us=index,
            updated_at_us=index,
        )
        repository.save(job)
        assert repository.get(job.job_id) == job
