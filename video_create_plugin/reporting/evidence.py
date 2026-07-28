"""从已完成分析 Job 的组件结果建立 EvidenceBundle 文件闭包。"""

from __future__ import annotations

from pathlib import Path

from components.audio_analysis.models import AudioAnalysisResult
from components.video_analysis.models import VideoAnalysisResult
from video_create_plugin.analysis.jobs import AnalysisJob
from video_create_plugin.contracts import FileRef, TimeRangeUs
from video_create_plugin.errors import PluginError

from .models import EvidenceBundle, EvidenceEntry


def build_evidence_bundle(
    job: AnalysisJob,
    workspace_root: Path,
) -> EvidenceBundle:
    if job.status != "succeeded" or job.video_output is None or job.audio_output is None:
        raise PluginError("analysis_incomplete", "分析 Job 完成后才能建立 EvidenceBundle")
    root = workspace_root.resolve()
    video = VideoAnalysisResult.model_validate_json(
        (root / job.video_output.path).read_text(encoding="utf-8")
    )
    audio = AudioAnalysisResult.model_validate_json(
        (root / job.audio_output.path).read_text(encoding="utf-8")
    )
    video_root = (root / job.video_output.path).parent
    audio_root = (root / job.audio_output.path).parent
    entries: list[EvidenceEntry] = []
    for frame in video.frames:
        entries.append(
            EvidenceEntry(
                evidence_id=frame.evidence_id,
                evidence_type="frame",
                file=_workspace_ref(root, video_root, frame.file.path, frame.file.sha256),
                time_range=TimeRangeUs(
                    start_us=frame.timestamp.timestamp_us,
                    end_us=frame.timestamp.timestamp_us + 1,
                ),
                fact_status="measured",
                algorithm_version=video.algorithm_version,
            )
        )
    entries.extend(
        (
            _entry(
                root,
                video_root,
                "frame_index",
                "frame_index",
                video.frame_index.path,
                video.frame_index.sha256,
                "measured",
                video.algorithm_version,
                video.time_range,
            ),
            _entry(
                root,
                video_root,
                "visual_signals",
                "visual_signals",
                video.visual_signals.path,
                video.visual_signals.sha256,
                "measured",
                video.algorithm_version,
                video.time_range,
            ),
            _entry(
                root,
                video_root,
                "boundary_candidates",
                "boundary_candidates",
                video.boundary_candidates_file.path,
                video.boundary_candidates_file.sha256,
                "algorithm_candidate",
                video.algorithm_version,
                video.time_range,
            ),
            _entry(
                root,
                video_root,
                "contact_sheet",
                "contact_sheet",
                video.contact_sheet.path,
                video.contact_sheet.sha256,
                "measured",
                video.algorithm_version,
                video.time_range,
            ),
            _entry(
                root,
                audio_root,
                "audio_pcm",
                "audio_pcm",
                audio.pcm.path,
                audio.pcm.sha256,
                "measured",
                audio.algorithm_version,
                audio.time_range,
            ),
            _entry(
                root,
                audio_root,
                "waveform",
                "waveform",
                audio.waveform.path,
                audio.waveform.sha256,
                "measured",
                audio.algorithm_version,
                audio.time_range,
            ),
            _entry(
                root,
                audio_root,
                "waveform_visualization",
                "waveform_visualization",
                audio.waveform_visualization.path,
                audio.waveform_visualization.sha256,
                "measured",
                audio.algorithm_version,
                audio.time_range,
            ),
            _entry(
                root,
                audio_root,
                "audio_signals",
                "audio_signals",
                audio.signals.path,
                audio.signals.sha256,
                "algorithm_candidate",
                audio.algorithm_version,
                audio.time_range,
            ),
        )
    )
    entries.extend(
        EvidenceEntry(
            evidence_id=f"refinement_{index:03d}",
            evidence_type="refinement",
            file=reference,
            fact_status="algorithm_candidate",
            algorithm_version=video.algorithm_version,
        )
        for index, reference in enumerate(job.refinements, start=1)
    )
    return EvidenceBundle(
        analysis_id=job.analysis_id,
        source_media_sha256=job.source.file.sha256,
        analysis_version="1.0",
        entries=tuple(entries),
    )


def _entry(
    workspace_root: Path,
    evidence_root: Path,
    evidence_id: str,
    evidence_type: str,
    relative_path: str,
    sha256: str,
    fact_status: str,
    algorithm_version: str,
    time_range: object,
) -> EvidenceEntry:
    return EvidenceEntry.model_validate(
        {
            "evidence_id": evidence_id,
            "evidence_type": evidence_type,
            "file": _workspace_ref(workspace_root, evidence_root, relative_path, sha256),
            "time_range": {
                "start_us": getattr(time_range, "start_us"),
                "end_us": getattr(time_range, "end_us"),
            },
            "fact_status": fact_status,
            "algorithm_version": algorithm_version,
        }
    )


def _workspace_ref(
    workspace_root: Path,
    evidence_root: Path,
    relative_path: str,
    sha256: str,
) -> FileRef:
    path = (evidence_root / relative_path).resolve()
    if not path.is_relative_to(workspace_root) or not path.is_file():
        raise PluginError(
            "file_not_found",
            "分析证据文件不存在",
            details={"path": str(path)},
        )
    return FileRef(
        path=path.relative_to(workspace_root).as_posix(),
        sha256=sha256,
        schema_version="1.0",
    )
