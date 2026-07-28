"""参考学习总体报告、逐镜分析、剪辑规律、阶段投影与证据闭包合同。"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from video_create_plugin.contracts import FileRef, PluginModel, StableId, TimeRangeUs

FactStatus = Literal[
    "measured",
    "algorithm_candidate",
    "agent_inference",
    "reconstruction_suggestion",
]
ApplicableStage = Literal["stage1", "stage2", "stage3"]

STAGE_KNOWLEDGE_TYPES: dict[str, frozenset[str]] = {
    "stage1": frozenset(
        {
            "video_type",
            "core_mechanism",
            "production_method",
            "visual_language",
            "rhythm_method",
            "transition_principle",
            "asset_music_traits",
            "viewing_experience",
        }
    ),
    "stage2": frozenset(
        {
            "asset_selection_traits",
            "shot_composition_traits",
            "action_direction_traits",
            "preprocess_need",
            "bgm_mood",
            "music_sections",
            "energy_curve",
            "rhythm_events",
        }
    ),
    "stage3": frozenset(
        {
            "editing_sentence",
            "shot_switch_logic",
            "pip_layer_pattern",
            "motion_pattern",
            "effect_scope",
            "audio_visual_binding",
            "cross_shot_continuity",
            "density_pattern",
            "transition_pattern",
        }
    ),
}


class EvidenceEntry(PluginModel):
    evidence_id: StableId
    evidence_type: Literal[
        "frame",
        "contact_sheet",
        "frame_index",
        "visual_signals",
        "boundary_candidates",
        "audio_pcm",
        "waveform",
        "waveform_visualization",
        "audio_signals",
        "refinement",
    ]
    file: FileRef
    time_range: TimeRangeUs | None = None
    fact_status: Literal["measured", "algorithm_candidate"]
    algorithm_version: str | None = Field(default=None, min_length=1)


class EvidenceBundle(PluginModel):
    analysis_id: StableId
    source_media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_version: str = Field(min_length=1)
    entries: tuple[EvidenceEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def entries_are_unique(self) -> EvidenceBundle:
        evidence_ids = [entry.evidence_id for entry in self.entries]
        paths = [entry.file.path for entry in self.entries]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("EvidenceBundle evidence_id 必须唯一")
        if len(paths) != len(set(paths)):
            raise ValueError("EvidenceBundle 文件路径必须唯一")
        return self


class EvidenceBackedClaim(PluginModel):
    claim_id: StableId
    content: str = Field(min_length=1)
    fact_status: FactStatus
    importance: Literal["important", "supporting"]
    confidence: float = Field(ge=0, le=1)
    evidence_refs: tuple[StableId, ...]

    @model_validator(mode="after")
    def important_claim_has_evidence(self) -> EvidenceBackedClaim:
        if self.importance == "important" and not self.evidence_refs:
            raise ValueError("重要结论必须包含 evidence_refs")
        return self


OverviewSectionName = Literal[
    "video_type_and_core_mechanism",
    "production_method",
    "visual_language",
    "rhythm_and_sound",
    "transition_principles",
    "asset_and_music_traits",
    "viewing_experience",
]
_OVERVIEW_SECTIONS = (
    "video_type_and_core_mechanism",
    "production_method",
    "visual_language",
    "rhythm_and_sound",
    "transition_principles",
    "asset_and_music_traits",
    "viewing_experience",
)


class OverviewSection(PluginModel):
    section: OverviewSectionName
    claims: tuple[EvidenceBackedClaim, ...] = Field(min_length=1)


class VideoOverview(PluginModel):
    sections: tuple[OverviewSection, ...]

    @model_validator(mode="after")
    def contains_seven_sections(self) -> VideoOverview:
        if tuple(section.section for section in self.sections) != _OVERVIEW_SECTIONS:
            raise ValueError("video_overview 必须按固定顺序包含七个板块")
        return self


class MusicSection(PluginModel):
    section_id: StableId
    section_type: Literal["intro", "build", "drive", "climax", "buffer", "outro"]
    time_range: TimeRangeUs
    claims: tuple[EvidenceBackedClaim, ...] = Field(min_length=1)


class TempoEvidence(PluginModel):
    bpm: float = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    evidence_refs: tuple[StableId, ...] = Field(min_length=1)


class AudioVisualRelation(PluginModel):
    relation_id: StableId
    relation_type: Literal[
        "sync",
        "anticipation",
        "post_beat_release",
        "sustain",
        "non_beat_binding",
    ]
    time_range: TimeRangeUs
    claim: EvidenceBackedClaim


class BgmAnalysis(PluginModel):
    audio_scope: Literal["mixed_program_audio", "isolated_bgm"]
    sections: tuple[MusicSection, ...] = Field(min_length=1)
    tempo_candidates: tuple[TempoEvidence, ...]
    audiovisual_relations: tuple[AudioVisualRelation, ...]


class ReferenceShot(PluginModel):
    shot_id: StableId
    rhythm_unit_id: StableId
    time_range: TimeRangeUs
    main_picture: str = Field(min_length=1)
    visible_layers: tuple[str, ...] = Field(min_length=1)
    visual_change: str = Field(min_length=1)
    effect_scope: str = Field(min_length=1)
    sound_relation: str = Field(min_length=1)
    connection: str = Field(min_length=1)
    sentence_function: str = Field(min_length=1)
    claims: tuple[EvidenceBackedClaim, ...] = Field(min_length=1)


class ReferenceShotAnalysis(PluginModel):
    duration_us: int = Field(gt=0)
    shots: tuple[ReferenceShot, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def timeline_continuously_covers_source(self) -> ReferenceShotAnalysis:
        if self.shots[0].time_range.start_us != 0:
            raise ValueError("主镜头时间线必须从 0 连续覆盖")
        for previous, current in zip(self.shots, self.shots[1:]):
            if previous.time_range.end_us != current.time_range.start_us:
                raise ValueError("主镜头时间线必须连续覆盖且不得重叠")
        if self.shots[-1].time_range.end_us != self.duration_us:
            raise ValueError("主镜头时间线必须覆盖完整片长")
        return self


class EditingSentence(PluginModel):
    sentence_id: StableId
    content: str = Field(min_length=1)
    evidence_refs: tuple[StableId, ...] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class EditingGrammar(PluginModel):
    viewing_experience: tuple[EvidenceBackedClaim, ...] = Field(min_length=1)
    reusable_sentences: tuple[EditingSentence, ...] = Field(min_length=1)
    reference_specific_notes: tuple[EvidenceBackedClaim, ...]


class ProjectedKnowledge(PluginModel):
    projection_id: StableId
    applicable_stage: ApplicableStage
    knowledge_type: str = Field(min_length=1)
    content: str = Field(min_length=1)
    evidence_refs: tuple[StableId, ...] = Field(min_length=1)
    fact_status: Literal["agent_inference", "reconstruction_suggestion"] = "agent_inference"
    confidence: float = Field(ge=0, le=1)
    transferability: Literal["reusable_mechanism"] = "reusable_mechanism"

    @model_validator(mode="after")
    def knowledge_type_matches_stage(self) -> ProjectedKnowledge:
        if self.knowledge_type not in STAGE_KNOWLEDGE_TYPES[self.applicable_stage]:
            raise ValueError("knowledge_type 与 applicable_stage 不匹配")
        return self


class CreationContextProjection(PluginModel):
    stage1_knowledge: tuple[ProjectedKnowledge, ...]
    stage2_knowledge: tuple[ProjectedKnowledge, ...]
    stage3_knowledge: tuple[ProjectedKnowledge, ...]

    @model_validator(mode="after")
    def fields_match_stages(self) -> CreationContextProjection:
        for stage, items in (
            ("stage1", self.stage1_knowledge),
            ("stage2", self.stage2_knowledge),
            ("stage3", self.stage3_knowledge),
        ):
            if any(item.applicable_stage != stage for item in items):
                raise ValueError(f"{stage}_knowledge 包含其他阶段条目")
        return self

    def all_items(self) -> tuple[ProjectedKnowledge, ...]:
        return (
            *self.stage1_knowledge,
            *self.stage2_knowledge,
            *self.stage3_knowledge,
        )


class ReferenceStudyReport(PluginModel):
    schema_version: Literal["1.0"] = "1.0"
    report_id: StableId
    analysis_id: StableId
    source_media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_version: str = Field(min_length=1)
    duration_us: int = Field(gt=0)
    evidence_bundle: EvidenceBundle
    video_overview: VideoOverview
    bgm_analysis: BgmAnalysis
    shot_analysis: ReferenceShotAnalysis
    editing_grammar: EditingGrammar
    creation_context_projection: CreationContextProjection

    @model_validator(mode="after")
    def report_identity_is_consistent(self) -> ReferenceStudyReport:
        if self.analysis_id != self.evidence_bundle.analysis_id:
            raise ValueError("报告与 EvidenceBundle analysis_id 不一致")
        if self.source_media_sha256 != self.evidence_bundle.source_media_sha256:
            raise ValueError("报告与 EvidenceBundle 媒体哈希不一致")
        if self.analysis_version != self.evidence_bundle.analysis_version:
            raise ValueError("报告与 EvidenceBundle 分析版本不一致")
        if self.duration_us != self.shot_analysis.duration_us:
            raise ValueError("报告片长与逐镜时间线片长不一致")
        return self


ReportFileRole = Literal[
    "structured_report",
    "video_overview",
    "bgm_analysis_json",
    "bgm_analysis_markdown",
    "shot_analysis_json",
    "shot_analysis_markdown",
    "editing_grammar",
    "creation_context_projection",
    "evidence_bundle",
]


class ReferenceReportFile(PluginModel):
    role: ReportFileRole
    file: FileRef


class ReferenceReportManifest(PluginModel):
    schema_version: Literal["1.0"] = "1.0"
    report_id: StableId
    analysis_id: StableId
    source_media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_version: str = Field(min_length=1)
    files: tuple[ReferenceReportFile, ...]

    def file_for(self, role: ReportFileRole) -> FileRef:
        for item in self.files:
            if item.role == role:
                return item.file
        raise KeyError(role)


class ReferenceReportOutput(PluginModel):
    manifest: ReferenceReportManifest
    manifest_file: FileRef
