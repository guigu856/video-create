"""从已校验参考报告合同确定性生成 Markdown、JSON 与文件清单。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from video_create_plugin.contracts import FileRef

from .models import (
    EvidenceBackedClaim,
    ReferenceReportFile,
    ReferenceReportManifest,
    ReferenceReportOutput,
    ReferenceStudyReport,
    ReportFileRole,
)
from .validator import validate_reference_report

REPORT_FILE_ROLES: tuple[ReportFileRole, ...] = (
    "structured_report",
    "video_overview",
    "bgm_analysis_json",
    "bgm_analysis_markdown",
    "shot_analysis_json",
    "shot_analysis_markdown",
    "editing_grammar",
    "creation_context_projection",
    "evidence_bundle",
)

_FILE_NAMES: dict[ReportFileRole, str] = {
    "structured_report": "reference_study.json",
    "video_overview": "video_overview.md",
    "bgm_analysis_json": "bgm_analysis.json",
    "bgm_analysis_markdown": "bgm_analysis.md",
    "shot_analysis_json": "reference_shot_analysis.json",
    "shot_analysis_markdown": "reference_shot_analysis.md",
    "editing_grammar": "reusable_editing_grammar.md",
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
            "video_overview": _overview_markdown(report),
            "bgm_analysis_json": report.bgm_analysis.model_dump_json(indent=2) + "\n",
            "bgm_analysis_markdown": _bgm_markdown(report),
            "shot_analysis_json": report.shot_analysis.model_dump_json(indent=2) + "\n",
            "shot_analysis_markdown": _shots_markdown(report),
            "editing_grammar": _grammar_markdown(report),
            "creation_context_projection": (
                report.creation_context_projection.model_dump_json(indent=2) + "\n"
            ),
            "evidence_bundle": report.evidence_bundle.model_dump_json(indent=2) + "\n",
        }
        files: list[ReferenceReportFile] = []
        for role in REPORT_FILE_ROLES:
            path = target / _FILE_NAMES[role]
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


def _overview_markdown(report: ReferenceStudyReport) -> str:
    labels = {
        "video_type_and_core_mechanism": "视频类型与核心机制",
        "production_method": "整体制作方法",
        "visual_language": "视觉语言与画面组织",
        "rhythm_and_sound": "节奏与声音使用方法",
        "transition_principles": "转场与镜头连接原则",
        "asset_and_music_traits": "素材与音乐的性质",
        "viewing_experience": "预期观看体验",
    }
    lines = ["# 参考视频总体理解", ""]
    for section in report.video_overview.sections:
        lines.extend((f"## {labels[section.section]}", ""))
        lines.extend(_claim_lines(section.claims))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _bgm_markdown(report: ReferenceStudyReport) -> str:
    bgm = report.bgm_analysis
    lines = [
        "# 参考视频 BGM 与音画关系分析",
        "",
        f"- 音频范围：`{bgm.audio_scope}`",
        "",
        "## 音乐段落",
        "",
        "| 段落 | 类型 | 时间范围 | 结论 |",
        "| :-- | :-- | :-- | :-- |",
    ]
    for section in bgm.sections:
        claims = "<br>".join(_claim_summary(claim) for claim in section.claims)
        lines.append(
            f"| {section.section_id} | {section.section_type} | "
            f"{_time_range(section.time_range.start_us, section.time_range.end_us)} | "
            f"{_table(claims)} |"
        )
    lines.extend(("", "## Tempo 候选", ""))
    lines.extend(
        f"- {item.bpm:g} BPM；置信度 {item.confidence:.2f}；证据：{', '.join(item.evidence_refs)}"
        for item in bgm.tempo_candidates
    )
    lines.extend(("", "## 音画关系", ""))
    lines.extend(
        f"- `{item.relation_type}` "
        f"{_time_range(item.time_range.start_us, item.time_range.end_us)}："
        f"{_claim_summary(item.claim)}"
        for item in bgm.audiovisual_relations
    )
    return "\n".join(lines).rstrip() + "\n"


def _shots_markdown(report: ReferenceStudyReport) -> str:
    lines = [
        "# 参考片逐镜分析表",
        "",
        "| 镜头 | 原片时间 | 节奏单元 | 主画面与图层 | 画面变化 | 效果作用域 | "
        "声音关系 | 连接 | 剪辑句子功能 | 证据结论 |",
        "| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |",
    ]
    for shot in report.shot_analysis.shots:
        claims = "<br>".join(_claim_summary(claim) for claim in shot.claims)
        lines.append(
            f"| {shot.shot_id} | "
            f"{_time_range(shot.time_range.start_us, shot.time_range.end_us)} | "
            f"{shot.rhythm_unit_id} | "
            f"{_table(shot.main_picture)}；{_table(', '.join(shot.visible_layers))} | "
            f"{_table(shot.visual_change)} | {_table(shot.effect_scope)} | "
            f"{_table(shot.sound_relation)} | {_table(shot.connection)} | "
            f"{_table(shot.sentence_function)} | {_table(claims)} |"
        )
    return "\n".join(lines) + "\n"


def _grammar_markdown(report: ReferenceStudyReport) -> str:
    grammar = report.editing_grammar
    lines = ["# 可复用剪辑语法", "", "## 核心观看体验", ""]
    lines.extend(_claim_lines(grammar.viewing_experience))
    lines.extend(("", "## 可迁移剪辑句子", ""))
    lines.extend(
        f"- `{item.sentence_id}` {item.content}；置信度 {item.confidence:.2f}；"
        f"证据：{', '.join(item.evidence_refs)}"
        for item in grammar.reusable_sentences
    )
    lines.extend(("", "## 原片专属证据", ""))
    lines.extend(_claim_lines(grammar.reference_specific_notes))
    return "\n".join(lines).rstrip() + "\n"


def _claim_lines(claims: tuple[EvidenceBackedClaim, ...]) -> list[str]:
    return [f"- {_claim_summary(claim)}" for claim in claims]


def _claim_summary(claim: EvidenceBackedClaim) -> str:
    evidence = ", ".join(claim.evidence_refs) or "无"
    return (
        f"{claim.content}（{claim.fact_status}，置信度 {claim.confidence:.2f}，证据：{evidence}）"
    )


def _time_range(start_us: int, end_us: int) -> str:
    return f"{start_us / 1_000_000:.3f}s–{end_us / 1_000_000:.3f}s"


def _table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


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
