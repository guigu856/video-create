"""单阶段原子知识、发布、实时类型汇总与语义检索合同。"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import Field, model_validator

from video_create_plugin.contracts import PluginModel, Sha256, StableId

ApplicableStage = Literal["stage1", "stage2", "stage3"]
Confidence = Literal["medium", "high"]
KnowledgeStatus = Literal["active", "archived"]
DynamicName = Annotated[str, Field(min_length=1, max_length=100)]
EvidenceResourceUri = Annotated[
    str,
    Field(
        pattern=(
            r"^video-create://analysis/[a-z][a-z0-9_]{2,63}/"
            r"[a-z][a-z0-9_]{2,63}$"
        )
    ),
]


class KnowledgeEvidenceRef(PluginModel):
    resource_uri: EvidenceResourceUri
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def interval_is_complete_and_ordered(self) -> KnowledgeEvidenceRef:
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("start_ms 与 end_ms 必须同时存在或同时省略")
        if self.start_ms is not None and self.end_ms is not None:
            if self.end_ms <= self.start_ms:
                raise ValueError("end_ms 必须大于 start_ms")
        return self


class KnowledgeUnitDraft(PluginModel):
    local_id: str = Field(pattern=r"^K[0-9]{3,}$")
    existing_knowledge_id: StableId | None = None
    stage: ApplicableStage
    video_types: tuple[DynamicName, ...] = Field(min_length=1)
    knowledge_type: DynamicName
    content: str = Field(min_length=1)
    evidence_refs: tuple[KnowledgeEvidenceRef, ...] = Field(min_length=1)
    confidence: Confidence

    @model_validator(mode="after")
    def multi_value_fields_are_unique(self) -> KnowledgeUnitDraft:
        if len(self.video_types) != len(set(self.video_types)):
            raise ValueError("video_types 不得重复")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evidence_refs 不得重复")
        return self


class KnowledgePublishRequest(PluginModel):
    analysis_id: StableId
    units: tuple[KnowledgeUnitDraft, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def local_ids_are_unique(self) -> KnowledgePublishRequest:
        local_ids = [unit.local_id for unit in self.units]
        if len(local_ids) != len(set(local_ids)):
            raise ValueError("units 中的 local_id 必须唯一")
        return self


class KnowledgeProvenance(PluginModel):
    analysis_id: StableId
    source_media_sha256: Sha256
    analysis_version: str = Field(min_length=1)


class KnowledgeUnit(PluginModel):
    knowledge_id: StableId
    stage: ApplicableStage
    video_types: tuple[DynamicName, ...] = Field(min_length=1)
    knowledge_type: DynamicName
    content: str = Field(min_length=1)
    evidence_refs: tuple[KnowledgeEvidenceRef, ...] = Field(min_length=1)
    provenances: tuple[KnowledgeProvenance, ...] = Field(min_length=1)
    confidence: Confidence
    status: KnowledgeStatus = "active"
    embedding_model: str = Field(min_length=1)
    embedding_version: str = Field(min_length=1)
    embedding_sha256: Sha256
    embedding_dimension: int = Field(gt=0)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def stored_lists_are_unique(self) -> KnowledgeUnit:
        for field_name, values in (
            ("video_types", self.video_types),
            ("evidence_refs", self.evidence_refs),
            ("provenances", self.provenances),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} 不得重复")
        if self.updated_at_us < self.created_at_us:
            raise ValueError("updated_at_us 不得早于 created_at_us")
        return self


class StoredKnowledgeUnit(KnowledgeUnit):
    vector: tuple[float, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def vector_matches_declared_space(self) -> StoredKnowledgeUnit:
        if len(self.vector) != self.embedding_dimension:
            raise ValueError("vector 维度与 embedding_dimension 不一致")
        if not all(math.isfinite(value) for value in self.vector):
            raise ValueError("vector 必须只包含有限浮点数")
        return self


class KnowledgePublishItem(PluginModel):
    local_id: str = Field(pattern=r"^K[0-9]{3,}$")
    knowledge_id: StableId
    action: Literal["created", "merged"]


class KnowledgePublishResult(PluginModel):
    items: tuple[KnowledgePublishItem, ...] = Field(min_length=1)


class KnowledgeSearchQuery(PluginModel):
    stage: ApplicableStage
    video_types: tuple[DynamicName, ...] = Field(min_length=1)
    knowledge_types: tuple[DynamicName, ...] = Field(min_length=1)
    text: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def filters_are_unique(self) -> KnowledgeSearchQuery:
        if len(self.video_types) != len(set(self.video_types)):
            raise ValueError("video_types 不得重复")
        if len(self.knowledge_types) != len(set(self.knowledge_types)):
            raise ValueError("knowledge_types 不得重复")
        return self


class KnowledgeSearchHit(KnowledgeUnit):
    similarity: float = Field(ge=-1, le=1)


class KnowledgeSearchResult(PluginModel):
    items: tuple[KnowledgeSearchHit, ...]


class KnowledgeTypeCount(PluginModel):
    name: DynamicName
    count: int = Field(ge=1)


class VideoTypeSummary(PluginModel):
    name: DynamicName
    knowledge_types: tuple[KnowledgeTypeCount, ...] = Field(min_length=1)


class StageTypesResult(PluginModel):
    stage: ApplicableStage
    video_types: tuple[VideoTypeSummary, ...]
