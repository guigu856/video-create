"""从已校验参考报告合同确定性生成 DOCX、JSON 与文件清单。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from video_create_plugin.contracts import FileRef

from .models import (
    ReferenceReportFile,
    ReferenceReportManifest,
    ReferenceReportOutput,
    ReferenceStudyReport,
    ReportFileRole,
)
from .validator import validate_reference_report
from .word_report import write_human_report

REPORT_FILE_ROLES: tuple[ReportFileRole, ...] = (
    "structured_report",
    "human_report_docx",
    "bgm_analysis_json",
    "shot_analysis_json",
    "creation_context_projection",
    "evidence_bundle",
)

_FILE_NAMES: dict[ReportFileRole, str] = {
    "structured_report": "reference_study.json",
    "human_report_docx": "reference_study_report.docx",
    "bgm_analysis_json": "bgm_analysis.json",
    "shot_analysis_json": "reference_shot_analysis.json",
    "creation_context_projection": "creation_context_projection.json",
    "evidence_bundle": "evidence_bundle.json",
}


class ReferenceReportGenerator:
    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root.resolve()

    def generate(
        self,
        report: ReferenceStudyReport,
        output_dir: Path,
    ) -> ReferenceReportOutput:
        validate_reference_report(report, self._workspace_root)
        target = output_dir.resolve()
        if not target.is_relative_to(self._workspace_root):
            raise ValueError("报告输出目录必须位于工作区内")
        target.mkdir(parents=True, exist_ok=True)

        content: dict[ReportFileRole, str] = {
            "structured_report": report.model_dump_json(indent=2) + "\n",
            "bgm_analysis_json": report.bgm_analysis.model_dump_json(indent=2) + "\n",
            "shot_analysis_json": report.shot_analysis.model_dump_json(indent=2) + "\n",
            "creation_context_projection": (
                report.creation_context_projection.model_dump_json(indent=2) + "\n"
            ),
            "evidence_bundle": report.evidence_bundle.model_dump_json(indent=2) + "\n",
        }
        files: list[ReferenceReportFile] = []
        for role in REPORT_FILE_ROLES:
            path = target / _FILE_NAMES[role]
            if role == "human_report_docx":
                write_human_report(report, path)
            else:
                _atomic_write(path, content[role])
            files.append(ReferenceReportFile(role=role, file=self._file_ref(path)))
        manifest = ReferenceReportManifest(
            report_id=report.report_id,
            analysis_id=report.analysis_id,
            source_media_sha256=report.source_media_sha256,
            analysis_version=report.analysis_version,
            files=tuple(files),
        )
        manifest_path = target / "reference_report_manifest.json"
        _atomic_write(manifest_path, manifest.model_dump_json(indent=2) + "\n")
        return ReferenceReportOutput(
            manifest=manifest,
            manifest_file=self._file_ref(manifest_path),
        )

    def _file_ref(self, path: Path) -> FileRef:
        return FileRef(
            path=path.relative_to(self._workspace_root).as_posix(),
            sha256=_sha256(path),
            schema_version="1.0",
        )

def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
