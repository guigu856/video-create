"""从已完成分析 Job 确定性构造并核验 EvidenceBundle。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from components.audio_analysis.models import AudioAnalysisResult
from components.video_analysis.models import VideoAnalysisResult
from video_create_plugin.analysis.jobs import AnalysisJob
from video_create_plugin.contracts import FileRef, TimeRangeUs
from video_create_plugin.errors import PluginError

from .models import EvidenceBundle, EvidenceEntry


def build_evidence_bundle(job: AnalysisJob, workspace_root: Path) -> EvidenceBundle:
    if job.status != "succeeded" or job.video_output is None or job.audio_output is None:
        raise PluginError("analysis_incomplete", "分析 Job 完成后才能建立 EvidenceBundle")
    root = workspace_root.resolve()
    video_path = _verified_workspace_path(root, job.video_output)
    audio_path = _verified_workspace_path(root, job.audio_output)
    video = VideoAnalysisResult.model_validate_json(video_path.read_text(encoding="utf-8"))
    audio = AudioAnalysisResult.model_validate_json(audio_path.read_text(encoding="utf-8"))
    if (
        video.source_sha256 != job.source.file.sha256
        or audio.source_sha256 != job.source.file.sha256
    ):
        raise PluginError("file_hash_mismatch", "分析结果与来源媒体哈希不一致")

    video_root = video_path.parent
    audio_root = audio_path.parent
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
    for index, reference in enumerate(job.refinements, start=1):
        path = _verified_workspace_path(root, reference)
        refinement = VideoAnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
        if refinement.source_sha256 != job.source.file.sha256:
            raise PluginError("file_hash_mismatch", "细化分析结果与来源媒体哈希不一致")
        prefix = f"refinement_{index:03d}"
        refinement_root = path.parent
        entries.append(
            EvidenceEntry(
                evidence_id=prefix,
                evidence_type="refinement",
                file=FileRef(
                    path=path.relative_to(root).as_posix(),
                    sha256=_sha256(path),
                    schema_version=reference.schema_version,
                ),
                time_range=TimeRangeUs(
                    start_us=refinement.time_range.start_us,
                    end_us=refinement.time_range.end_us,
                ),
                fact_status="algorithm_candidate",
                algorithm_version=refinement.algorithm_version,
            )
        )
        for frame in refinement.frames:
            entries.append(
                EvidenceEntry(
                    evidence_id=f"{prefix}_{frame.evidence_id}",
                    evidence_type="frame",
                    file=_workspace_ref(
                        root,
                        refinement_root,
                        frame.file.path,
                        frame.file.sha256,
                    ),
                    time_range=TimeRangeUs(
                        start_us=frame.timestamp.timestamp_us,
                        end_us=frame.timestamp.timestamp_us + 1,
                    ),
                    fact_status="measured",
                    algorithm_version=refinement.algorithm_version,
                )
            )
        entries.extend(
            (
                _entry(
                    root,
                    refinement_root,
                    f"{prefix}_frame_index",
                    "frame_index",
                    refinement.frame_index.path,
                    refinement.frame_index.sha256,
                    "measured",
                    refinement.algorithm_version,
                    refinement.time_range,
                ),
                _entry(
                    root,
                    refinement_root,
                    f"{prefix}_visual_signals",
                    "visual_signals",
                    refinement.visual_signals.path,
                    refinement.visual_signals.sha256,
                    "measured",
                    refinement.algorithm_version,
                    refinement.time_range,
                ),
                _entry(
                    root,
                    refinement_root,
                    f"{prefix}_boundary_candidates",
                    "boundary_candidates",
                    refinement.boundary_candidates_file.path,
                    refinement.boundary_candidates_file.sha256,
                    "algorithm_candidate",
                    refinement.algorithm_version,
                    refinement.time_range,
                ),
                _entry(
                    root,
                    refinement_root,
                    f"{prefix}_contact_sheet",
                    "contact_sheet",
                    refinement.contact_sheet.path,
                    refinement.contact_sheet.sha256,
                    "measured",
                    refinement.algorithm_version,
                    refinement.time_range,
                ),
            )
        )
    return EvidenceBundle(
        analysis_id=job.analysis_id,
        source_media_sha256=job.source.file.sha256,
        analysis_version="1.0",
        entries=tuple(entries),
    )


def verified_evidence_path(
    workspace_root: Path,
    entry: EvidenceEntry,
) -> Path:
    return _verified_workspace_path(workspace_root.resolve(), entry.file)


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
    declared_sha256: str,
) -> FileRef:
    resolved_evidence_root = evidence_root.resolve()
    path = (resolved_evidence_root / relative_path).resolve()
    if (
        not path.is_relative_to(workspace_root)
        or not path.is_relative_to(resolved_evidence_root)
        or not path.is_file()
    ):
        raise PluginError(
            "file_not_found",
            "分析证据文件不存在",
            details={"path": str(path)},
        )
    actual_sha256 = _sha256(path)
    if actual_sha256 != declared_sha256:
        raise PluginError(
            "file_hash_mismatch",
            "分析证据文件哈希不匹配",
            details={"path": path.relative_to(workspace_root).as_posix()},
        )
    return FileRef(
        path=path.relative_to(workspace_root).as_posix(),
        sha256=actual_sha256,
        schema_version="1.0",
    )


def _verified_workspace_path(workspace_root: Path, reference: FileRef) -> Path:
    path = (workspace_root / reference.path).resolve()
    if not path.is_relative_to(workspace_root) or not path.is_file():
        raise PluginError(
            "file_not_found",
            "分析证据文件不存在",
            details={"path": reference.path},
        )
    if _sha256(path) != reference.sha256:
        raise PluginError(
            "file_hash_mismatch",
            "分析证据文件哈希不匹配",
            details={"path": reference.path},
        )
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
