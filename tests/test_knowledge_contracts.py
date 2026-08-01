"""锁定单阶段、动态类型和一次发布的公开知识合同。"""

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from video_create_plugin.knowledge.models import (
    KnowledgeEvidenceRef,
    KnowledgePublishRequest,
    KnowledgeSearchQuery,
    KnowledgeUnitDraft,
)
from video_create_plugin.mcp.server import create_server


def _draft(**updates: object) -> KnowledgeUnitDraft:
    payload: dict[str, object] = {
        "local_id": "K001",
        "stage": "stage3",
        "video_types": ("动漫 MAD", "燃向混剪"),
        "knowledge_type": "new_dynamic_type",
        "content": "适用条件、剪辑机制和观看作用形成一个原子规律。",
        "evidence_refs": (
            KnowledgeEvidenceRef(
                resource_uri="video-create://analysis/analysis_example/frame_000001",
                start_ms=100,
                end_ms=101,
            ),
        ),
        "confidence": "high",
    }
    payload.update(updates)
    return KnowledgeUnitDraft.model_validate(payload)


def test_publish_contract_has_no_report_or_confirmation_fields() -> None:
    request = KnowledgePublishRequest(
        analysis_id="analysis_example",
        units=(_draft(),),
    )

    assert set(request.model_dump()) == {"analysis_id", "units"}
    assert request.units[0].stage == "stage3"
    assert request.units[0].video_types == ("动漫 MAD", "燃向混剪")


@pytest.mark.parametrize(
    "updates",
    [
        {"local_id": "K01"},
        {"video_types": ("动漫 MAD", "动漫 MAD")},
        {"evidence_refs": ()},
        {"confidence": "low"},
    ],
)
def test_draft_rejects_invalid_mechanical_shape(updates: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _draft(**updates)


@pytest.mark.parametrize(
    "start_ms,end_ms",
    [(100, None), (None, 101), (101, 100), (-1, 10)],
)
def test_evidence_interval_requires_a_valid_pair(
    start_ms: int | None,
    end_ms: int | None,
) -> None:
    with pytest.raises(ValidationError):
        KnowledgeEvidenceRef(
            resource_uri="video-create://analysis/analysis_example/frame_000001",
            start_ms=start_ms,
            end_ms=end_ms,
        )


def test_search_contract_uses_dynamic_any_match_filters() -> None:
    query = KnowledgeSearchQuery(
        stage="stage3",
        video_types=("动漫 MAD", "电影混剪"),
        knowledge_types=("new_dynamic_type",),
        text="重拍释放前先积累视觉密度",
    )

    assert query.video_types == ("动漫 MAD", "电影混剪")
    assert query.knowledge_types == ("new_dynamic_type",)


@pytest.mark.parametrize(
    "updates",
    [
        {"video_types": ()},
        {"knowledge_types": ()},
        {"video_types": ("动漫 MAD", "动漫 MAD")},
        {"knowledge_types": ("editing_sentence", "editing_sentence")},
    ],
)
def test_search_contract_requires_non_empty_unique_filters(
    updates: dict[str, object],
) -> None:
    payload: dict[str, object] = {
        "stage": "stage3",
        "video_types": ("动漫 MAD",),
        "knowledge_types": ("editing_sentence",),
        "text": "重拍释放前先积累视觉密度",
    }
    payload.update(updates)

    with pytest.raises(ValidationError):
        KnowledgeSearchQuery.model_validate(payload)


def test_search_json_schema_marks_both_filter_dimensions_as_required_lists() -> None:
    schema = KnowledgeSearchQuery.model_json_schema()

    assert {"video_types", "knowledge_types"} <= set(schema["required"])
    assert schema["properties"]["video_types"]["minItems"] == 1
    assert schema["properties"]["knowledge_types"]["minItems"] == 1


def test_mcp_search_rejects_an_empty_filter_dimension(tmp_path: Path) -> None:
    server = create_server(workspace_root=tmp_path)

    async def verify() -> None:
        for field_name in ("video_types", "knowledge_types"):
            arguments = {
                "stage": "stage3",
                "video_types": ["动漫 MAD"],
                "knowledge_types": ["editing_sentence"],
                "text": "重拍释放前先积累视觉密度",
            }
            arguments[field_name] = []

            _, structured = await server.call_tool("knowledge_search", arguments)

            assert structured is not None
            assert structured["ok"] is False
            assert structured["error"]["code"] == "input_invalid"
            assert field_name in structured["error"]["details"]["validation"]

    asyncio.run(verify())
