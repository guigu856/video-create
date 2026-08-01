"""构造不依赖 FFmpeg 的最小参考分析 Job 与真实证据文件。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from components.audio_analysis.models import (
    AudioAnalysisResult,
    AudioEvidenceFile,
    AudioTimeRange,
)
from components.video_analysis.models import (
    AnalysisInterval,
    EvidenceFile,
    FrameEvidence,
    TimestampRef,
    VideoAnalysisResult,
)
from video_create_plugin.analysis.jobs import AnalysisJob, AnalysisStep
from video_create_plugin.analysis.models import MediaProbe, MediaStream, SourceMedia
from video_create_plugin.contracts import FileRef
from video_create_plugin.repository.jobs import AnalysisJobRepository


def materialize_succeeded_analysis(
    root: Path,
    *,
    analysis_id: str = "analysis_example",
) -> tuple[AnalysisJobRepository, AnalysisJob]:
    source_path = root / "output/plugin/sources/reference.mp4"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"reference-media")
    source_sha256 = _sha256(source_path)
    source = SourceMedia(
        source_id=f"source_{source_sha256[:16]}",
        source_kind="local",
        original_input=str(source_path),
        file=_workspace_ref(root, source_path),
        probe=MediaProbe(
            duration_us=1_000_000,
            streams=(
                MediaStream(
                    index=0,
                    codec_type="video",
                    codec_name="h264",
                    time_base="1/1000000",
                ),
                MediaStream(
                    index=1,
                    codec_type="audio",
                    codec_name="aac",
                    time_base="1/1000000",
                ),
            ),
        ),
    )

    analysis_root = root / f"output/plugin/analysis/{analysis_id}"
    video_root = analysis_root / "video"
    audio_root = analysis_root / "audio"
    video_root.mkdir(parents=True, exist_ok=True)
    audio_root.mkdir(parents=True, exist_ok=True)

    frame_one = _component_file(video_root, "frames/frame_000001.jpg", b"frame-one")
    frame_two = _component_file(video_root, "frames/frame_000002.jpg", b"frame-two")
    frame_index = _component_file(video_root, "frame_index.json", b"[]\n")
    visual_signals = _component_file(video_root, "visual_signals.json", b"[]\n")
    boundaries = _component_file(video_root, "boundary_candidates.json", b"[]\n")
    contact_sheet = _component_file(video_root, "contact_sheet.jpg", b"contact-sheet")
    video = VideoAnalysisResult(
        source_sha256=source_sha256,
        max_sample_interval_us=500_000,
        time_range=AnalysisInterval(start_us=0, end_us=1_000_000),
        frame_index=frame_index,
        visual_signals=visual_signals,
        boundary_candidates_file=boundaries,
        frames=(
            FrameEvidence(
                evidence_id="frame_000001",
                timestamp=TimestampRef(
                    pts=100_000,
                    time_base="1/1000000",
                    frame_index=1,
                    timestamp_us=100_000,
                ),
                file=frame_one,
            ),
            FrameEvidence(
                evidence_id="frame_000002",
                timestamp=TimestampRef(
                    pts=500_000,
                    time_base="1/1000000",
                    frame_index=2,
                    timestamp_us=500_000,
                ),
                file=frame_two,
            ),
        ),
        boundary_candidates=(),
        contact_sheet=contact_sheet,
    )
    video_result_path = video_root / "video_analysis.json"
    video_result_path.write_text(video.model_dump_json(indent=2) + "\n", encoding="utf-8")

    pcm = _audio_component_file(audio_root, "audio.pcm", b"pcm")
    waveform = _audio_component_file(audio_root, "waveform.json", b"[]\n")
    waveform_visualization = _audio_component_file(audio_root, "waveform.png", b"waveform")
    signals = _audio_component_file(audio_root, "audio_signals.json", b"{}\n")
    audio = AudioAnalysisResult(
        source_sha256=source_sha256,
        audio_scope="mixed_program_audio",
        sample_rate=8_000,
        source_channels=1,
        analysis_channels=1,
        time_range=AudioTimeRange(start_us=0, end_us=1_000_000),
        pcm=pcm,
        waveform=waveform,
        waveform_visualization=waveform_visualization,
        signals=signals,
        tempo_candidates=(),
        beat_candidates=(),
        sound_event_candidates=(),
    )
    audio_result_path = audio_root / "audio_analysis.json"
    audio_result_path.write_text(audio.model_dump_json(indent=2) + "\n", encoding="utf-8")

    now = 1_000_000
    video_output = _workspace_ref(root, video_result_path)
    audio_output = _workspace_ref(root, audio_result_path)
    job = AnalysisJob(
        job_id=f"job_{analysis_id.removeprefix('analysis_')}",
        analysis_id=analysis_id,
        status="succeeded",
        progress=100,
        source=source,
        analysis_dir=f"output/plugin/analysis/{analysis_id}",
        steps=(
            AnalysisStep(name="video", status="succeeded", output=video_output),
            AnalysisStep(name="audio", status="succeeded", output=audio_output),
        ),
        video_output=video_output,
        audio_output=audio_output,
        created_at_us=now,
        updated_at_us=now,
    )
    repository = AnalysisJobRepository(root)
    repository.save(job)
    return repository, job


def materialize_refinement(
    root: Path,
    repository: AnalysisJobRepository,
    job: AnalysisJob,
) -> AnalysisJob:
    refinement_root = root / job.analysis_dir / "refinements/refinement_test"
    refinement_root.mkdir(parents=True, exist_ok=True)
    frame_one = _component_file(refinement_root, "frames/frame_000001.jpg", b"refined-one")
    frame_two = _component_file(refinement_root, "frames/frame_000002.jpg", b"refined-two")
    result = VideoAnalysisResult(
        source_sha256=job.source.file.sha256,
        max_sample_interval_us=100_000,
        time_range=AnalysisInterval(start_us=200_000, end_us=400_000),
        frame_index=_component_file(refinement_root, "frame_index.json", b"[]\n"),
        visual_signals=_component_file(refinement_root, "visual_signals.json", b"[]\n"),
        boundary_candidates_file=_component_file(
            refinement_root,
            "boundary_candidates.json",
            b"[]\n",
        ),
        frames=(
            FrameEvidence(
                evidence_id="frame_000001",
                timestamp=TimestampRef(
                    pts=200_000,
                    time_base="1/1000000",
                    frame_index=2,
                    timestamp_us=200_000,
                ),
                file=frame_one,
            ),
            FrameEvidence(
                evidence_id="frame_000002",
                timestamp=TimestampRef(
                    pts=300_000,
                    time_base="1/1000000",
                    frame_index=3,
                    timestamp_us=300_000,
                ),
                file=frame_two,
            ),
        ),
        boundary_candidates=(),
        contact_sheet=_component_file(
            refinement_root,
            "contact_sheet.jpg",
            b"refined-contact-sheet",
        ),
    )
    result_path = refinement_root / "video_analysis.json"
    result_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    reference = _workspace_ref(root, result_path)
    refined = job.model_copy(
        update={
            "refinements": (*job.refinements, reference),
            "updated_at_us": job.updated_at_us + 1,
        }
    )
    return repository.save(refined)


def _component_file(root: Path, relative_path: str, content: bytes) -> EvidenceFile:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return EvidenceFile(path=relative_path, sha256=_sha256(path))


def _audio_component_file(
    root: Path,
    relative_path: str,
    content: bytes,
) -> AudioEvidenceFile:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return AudioEvidenceFile(path=relative_path, sha256=_sha256(path))


def _workspace_ref(root: Path, path: Path) -> FileRef:
    return FileRef(
        path=path.relative_to(root).as_posix(),
        sha256=_sha256(path),
        schema_version="1.0",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
