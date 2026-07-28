"""知识发布、持久记录和阶段过滤检索合同。"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from video_create_plugin.contracts import FileRef, PluginModel, StableId, TimeRangeUs
from video_create_plugin.reporting.models import (
    STAGE_KNOWLEDGE_TYPES,
    ApplicableStage,
    FactStatus,
)

KnowledgeCollection = Literal["creation_knowledge", "reference_evidence"]


class KnowledgeUnitDraft(PluginModel):
    applicable_stages: tuple[ApplicableStage, ...] = Field(min_length=1)
    knowledge_type: str = Field(min_length=1)
    video_type_tags: tuple[str, ...] = ()
    technique_tags: tuple[str, ...] = ()
    music_layer_tags: tuple[str, ...] = ()
    energy_phase: str | None = None
    granularity: Literal["global", "section", "rhythm_unit", "shot"]
    visibility: Literal["creation_shared", "task_private", "evidence_only"]
    source_time_range: TimeRangeUs | None = None
    content: str = Field(min_length=1)
    evidence_refs: tuple[StableId, ...] = Field(min_length=1)
    fact_status: FactStatus
    confidence: float = Field(ge=0, le=1)
    transferability: Literal["reusable_mechanism", "reference_specific", "uncertain"]

    @model_validator(mode="after")
    def type_matches_all_stages(self) -> KnowledgeUnitDraft:
        if len(set(self.applicable_stages)) != len(self.applicable_stages):
            raise ValueError("applicable_stages 不得重复")
        if any(
            self.knowledge_type not in STAGE_KNOWLEDGE_TYPES[stage]
            for stage in self.applicable_stages
        ):
            raise ValueError("knowledge_type 与 applicable_stages 不匹配")
        return self


class KnowledgeUnit(KnowledgeUnitDraft):
    knowledge_id: StableId
    source_report_path: str = Field(min_length=1)
    source_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_version: str = Field(min_length=1)
    collection: KnowledgeCollection
    status: Literal["active", "archived"] = "active"


class PublicationRequest(PluginModel):
    user_confirmed: bool
    manifest_file: FileRef
    units: tuple[KnowledgeUnitDraft, ...] = Field(min_length=1)


class PublicationPreview(PluginModel):
    units: tuple[KnowledgeUnit, ...]


class KnowledgeSearchQuery(PluginModel):
    stage: ApplicableStage
    knowledge_types: tuple[str, ...] = Field(min_length=1)
    text: str = ""
    video_type_tags: tuple[str, ...] = ()
    technique_tags: tuple[str, ...] = ()
    music_layer_tags: tuple[str, ...] = ()
    energy_phase: str | None = None
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def types_match_stage(self) -> KnowledgeSearchQuery:
        if any(
            knowledge_type not in STAGE_KNOWLEDGE_TYPES[self.stage]
            for knowledge_type in self.knowledge_types
        ):
            raise ValueError("knowledge_types 包含不适用于目标阶段的类型")
        return self


class KnowledgeSearchResult(PluginModel):
    items: tuple[KnowledgeUnit, ...]
