"""验证参考报告、证据闭包、逐镜时间线和阶段投影合同。"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from video_create_plugin.contracts import FileRef, TimeRangeUs
from video_create_plugin.errors import PluginError
from video_create_plugin.reporting.models import (
    AudioVisualRelation,
    BgmAnalysis,
    CreationContextProjection,
    EditingGrammar,
    EditingSentence,
    EvidenceBackedClaim,
    EvidenceBundle,
    EvidenceEntry,
    MusicSection,
    OverviewSection,
    ProjectedKnowledge,
    ReferenceShot,
    ReferenceShotAnalysis,
    ReferenceStudyReport,
    TempoEvidence,
    VideoOverview,
)
from video_create_plugin.reporting.validator import validate_reference_report

ROOT = Path(__file__).parents[1]
SHA = "a" * 64


def _claim(claim_id: str, evidence_id: str = "frame_000001") -> EvidenceBackedClaim:
    return EvidenceBackedClaim(
        claim_id=claim_id,
        content="基于证据的结论",
        fact_status="agent_inference",
        importance="important",
        confidence=0.9,
        evidence_refs=(evidence_id,),
    )


def make_reference_report() -> ReferenceStudyReport:
    evidence = EvidenceBundle(
        analysis_id="analysis_example",
        source_media_sha256=SHA,
        analysis_version="1.0",
        entries=(
            EvidenceEntry(
                evidence_id="frame_000001",
                evidence_type="frame",
                file=FileRef(path="evidence/frame.jpg", sha256=SHA),
                time_range=TimeRangeUs(start_us=0, end_us=1),
                fact_status="measured",
            ),
            EvidenceEntry(
                evidence_id="audio_signals",
                evidence_type="audio_signals",
                file=FileRef(path="evidence/audio.json", sha256=SHA),
                time_range=TimeRangeUs(start_us=0, end_us=1_000_000),
                fact_status="algorithm_candidate",
            ),
        ),
    )
    overview = VideoOverview(
        sections=tuple(
            OverviewSection(
                section=section,
                claims=(_claim(f"claim_{index}"),),
            )
            for index, section in enumerate(
                (
                    "video_type_and_core_mechanism",
                    "production_method",
                    "visual_language",
                    "rhythm_and_sound",
                    "transition_principles",
                    "asset_and_music_traits",
                    "viewing_experience",
                ),
                start=1,
            )
        )
    )
    bgm = BgmAnalysis(
        audio_scope="mixed_program_audio",
        sections=(
            MusicSection(
                section_id="music_intro",
                section_type="intro",
                time_range=TimeRangeUs(start_us=0, end_us=1_000_000),
                claims=(_claim("claim_music", "audio_signals"),),
            ),
        ),
        tempo_candidates=(
            TempoEvidence(bpm=120, confidence=0.8, evidence_refs=("audio_signals",)),
        ),
        audiovisual_relations=(
            AudioVisualRelation(
                relation_id="relation_sync",
                relation_type="sync",
                time_range=TimeRangeUs(start_us=0, end_us=1_000_000),
                claim=_claim("claim_relation", "audio_signals"),
            ),
        ),
    )
    shots = ReferenceShotAnalysis(
        duration_us=1_000_000,
        shots=(
            ReferenceShot(
                shot_id="shot_001",
                rhythm_unit_id="rhythm_001",
                time_range=TimeRangeUs(start_us=0, end_us=500_000),
                main_picture="主画面 A",
                visible_layers=("main",),
                visual_change="静态建立",
                effect_scope="shot",
                sound_relation="intro",
                connection="hard_cut",
                sentence_function="setup",
                claims=(_claim("claim_shot_1"),),
            ),
            ReferenceShot(
                shot_id="shot_002",
                rhythm_unit_id="rhythm_001",
                time_range=TimeRangeUs(start_us=500_000, end_us=1_000_000),
                main_picture="主画面 B",
                visible_layers=("main",),
                visual_change="画面切换",
                effect_scope="shot",
                sound_relation="sync",
                connection="end",
                sentence_function="release",
                claims=(_claim("claim_shot_2"),),
            ),
        ),
    )
    grammar = EditingGrammar(
        viewing_experience=(_claim("claim_experience"),),
        reusable_sentences=(
            EditingSentence(
                sentence_id="sentence_001",
                content="建立后在能量点释放",
                evidence_refs=("frame_000001", "audio_signals"),
                confidence=0.85,
            ),
        ),
        reference_specific_notes=(_claim("claim_specific"),),
    )
    projection = CreationContextProjection(
        stage1_knowledge=(
            ProjectedKnowledge(
                projection_id="projection_stage1",
                applicable_stage="stage1",
                knowledge_type="video_type",
                content="短促建立后释放的类型机制",
                evidence_refs=("frame_000001",),
                confidence=0.9,
            ),
        ),
        stage2_knowledge=(
            ProjectedKnowledge(
                projection_id="projection_stage2",
                applicable_stage="stage2",
                knowledge_type="bgm_mood",
                content="选择具有清晰能量释放点的音乐",
                evidence_refs=("audio_signals",),
                confidence=0.8,
            ),
        ),
        stage3_knowledge=(
            ProjectedKnowledge(
                projection_id="projection_stage3",
                applicable_stage="stage3",
                knowledge_type="editing_sentence",
                content="建立镜头后接能量释放镜头",
                evidence_refs=("frame_000001", "audio_signals"),
                confidence=0.85,
            ),
        ),
    )
    return ReferenceStudyReport(
        report_id="report_example",
        analysis_id="analysis_example",
        source_media_sha256=SHA,
        analysis_version="1.0",
        duration_us=1_000_000,
        evidence_bundle=evidence,
        video_overview=overview,
        bgm_analysis=bgm,
        shot_analysis=shots,
        editing_grammar=grammar,
        creation_context_projection=projection,
    )


def test_complete_report_round_trips_and_matches_schema() -> None:
    report = make_reference_report()

    assert ReferenceStudyReport.model_validate_json(report.model_dump_json()) == report
    checked_in = json.loads(
        (ROOT / "schemas/reference-study.schema.json").read_text(encoding="utf-8")
    )
    assert checked_in == ReferenceStudyReport.model_json_schema()
    assert validate_reference_report(report) == report


def test_missing_evidence_reference_is_rejected() -> None:
    report = make_reference_report()
    invalid_claim = _claim("claim_missing", "missing_evidence")
    invalid = report.model_copy(
        update={
            "editing_grammar": report.editing_grammar.model_copy(
                update={"viewing_experience": (invalid_claim,)}
            )
        }
    )

    with pytest.raises(PluginError) as caught:
        validate_reference_report(invalid)

    assert caught.value.code == "evidence_not_found"


def test_main_shot_timeline_gap_is_rejected() -> None:
    report = make_reference_report()
    second = report.shot_analysis.shots[1].model_copy(
        update={"time_range": TimeRangeUs(start_us=600_000, end_us=1_000_000)}
    )

    with pytest.raises(ValidationError, match="连续覆盖"):
        ReferenceShotAnalysis(
            duration_us=1_000_000,
            shots=(report.shot_analysis.shots[0], second),
        )


def test_important_claim_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="重要结论"):
        EvidenceBackedClaim(
            claim_id="claim_without_evidence",
            content="缺少证据",
            fact_status="agent_inference",
            importance="important",
            confidence=0.8,
            evidence_refs=(),
        )


def test_projection_rejects_source_specific_fields_and_wrong_stage_type() -> None:
    with pytest.raises(ValidationError):
        ProjectedKnowledge.model_validate(
            {
                "projection_id": "projection_invalid",
                "applicable_stage": "stage1",
                "knowledge_type": "video_type",
                "content": "投影内容",
                "evidence_refs": ["frame_000001"],
                "confidence": 0.8,
                "source_time_range": {"start_us": 0, "end_us": 1},
            }
        )
    with pytest.raises(ValidationError, match="knowledge_type"):
        ProjectedKnowledge(
            projection_id="projection_wrong_type",
            applicable_stage="stage1",
            knowledge_type="editing_sentence",
            content="阶段错配",
            evidence_refs=("frame_000001",),
            confidence=0.8,
        )
