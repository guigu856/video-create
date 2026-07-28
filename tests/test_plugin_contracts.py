"""验证公共值对象、稳定响应、规范化哈希与检入 JSON Schema 的合同边界。"""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from video_create_plugin.contracts import (
    CommonContract,
    FileRef,
    SuccessResponse,
    TimeRangeUs,
    canonical_json_sha256,
)
from video_create_plugin.errors import PluginError

ROOT = Path(__file__).parents[1]
SHA256 = "a" * 64


def test_file_ref_round_trips_without_workflow_state() -> None:
    value = FileRef(path="analysis/source.mp4", sha256=SHA256, schema_version="1.0")

    assert FileRef.model_validate_json(value.model_dump_json()) == value
    assert value.model_dump() == {
        "path": "analysis/source.mp4",
        "sha256": SHA256,
        "schema_version": "1.0",
    }


@pytest.mark.parametrize(
    "path",
    ["/absolute/source.mp4", "../source.mp4", "analysis/../source.mp4", r"analysis\source.mp4"],
)
def test_file_ref_rejects_paths_outside_the_controlled_root(path: str) -> None:
    with pytest.raises(ValidationError):
        FileRef(path=path, sha256=SHA256)


def test_file_ref_rejects_invalid_hash() -> None:
    with pytest.raises(ValidationError):
        FileRef(path="analysis/source.mp4", sha256="A" * 64)


def test_time_range_uses_non_empty_integer_microseconds() -> None:
    assert TimeRangeUs(start_us=0, end_us=1).model_dump() == {
        "start_us": 0,
        "end_us": 1,
    }
    with pytest.raises(ValidationError):
        TimeRangeUs(start_us=10, end_us=10)


def test_canonical_json_hash_is_key_order_independent() -> None:
    assert canonical_json_sha256({"标题": "测试", "revision": 1}) == canonical_json_sha256(
        {"revision": 1, "标题": "测试"}
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_hash_rejects_non_json_numbers(value: float) -> None:
    with pytest.raises(ValueError):
        canonical_json_sha256(value)


def test_plugin_error_maps_to_stable_response() -> None:
    response = PluginError(
        "artifact_not_found",
        "Artifact 不存在",
        details={"artifact_id": "artifact_1"},
    ).to_response()

    assert response.model_dump(mode="json") == {
        "ok": False,
        "error": {
            "code": "artifact_not_found",
            "message": "Artifact 不存在",
            "details": {"artifact_id": "artifact_1"},
        },
    }


def test_success_response_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SuccessResponse(data={"revision": 1}, extra_value=True)


def test_common_schema_matches_checked_in_contract() -> None:
    checked_in = json.loads((ROOT / "schemas/common.schema.json").read_text(encoding="utf-8"))
    assert checked_in == TypeAdapter(CommonContract).json_schema()
