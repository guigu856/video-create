"""定义 Plugin 各层共享的稳定 ID、时间、Artifact 引用、响应与哈希合同。"""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

StableId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class PluginModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ArtifactRef(PluginModel):
    artifact_id: StableId
    revision: int = Field(ge=1)
    sha256: Sha256


class TimeRangeUs(PluginModel):
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)

    @model_validator(mode="after")
    def end_is_after_start(self) -> "TimeRangeUs":
        if self.end_us <= self.start_us:
            raise ValueError("end_us 必须大于 start_us")
        return self


class ErrorBody(PluginModel):
    code: StableId
    message: str = Field(min_length=1)
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ErrorResponse(PluginModel):
    ok: Literal[False] = False
    error: ErrorBody


class SuccessResponse(PluginModel):
    ok: Literal[True] = True
    data: dict[str, JsonValue]


CommonContract = ArtifactRef | TimeRangeUs | SuccessResponse | ErrorResponse


def canonical_json_sha256(value: JsonValue) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
