"""验证实时类型汇总、结构化预过滤、ANY 标签语义和相似度输出。"""

from pathlib import Path

import pytest
from reference_analysis_fixtures import materialize_succeeded_analysis
from test_knowledge_publication import draft, make_service, publish

from video_create_plugin.knowledge.models import KnowledgeSearchQuery


def _populated_service(root: Path):
    service, store, _ = make_service(root)
    result = publish(
        service,
        draft(
            local_id="K001",
            video_types=("动漫 MAD", "燃向混剪"),
            knowledge_type="editing_sentence",
            content="先用连续快切积累密度，再以重拍释放。",
        ),
        draft(
            local_id="K002",
            evidence_id="frame_000002",
            video_types=("电影混剪",),
            knowledge_type="motion_pattern",
            content="缓慢横移保持空间方向连续。",
        ),
        draft(
            local_id="K003",
            evidence_id="audio_signals",
            stage="stage1",
            video_types=("动漫 MAD",),
            knowledge_type="core_mechanism",
            content="快切和重拍共同形成总体吸引力。",
        ),
    )
    return service, store, result


def test_stage_types_are_derived_from_active_rows(tmp_path: Path) -> None:
    service, store, result = _populated_service(tmp_path)

    listed = service.list_stage_types("stage3")

    assert listed.model_dump(mode="json") == {
        "stage": "stage3",
        "video_types": [
            {
                "name": "动漫 MAD",
                "knowledge_types": [{"name": "editing_sentence", "count": 1}],
            },
            {
                "name": "燃向混剪",
                "knowledge_types": [{"name": "editing_sentence", "count": 1}],
            },
            {
                "name": "电影混剪",
                "knowledge_types": [{"name": "motion_pattern", "count": 1}],
            },
        ],
    }

    store.archive(result.items[0].knowledge_id)
    after_archive = service.list_stage_types("stage3")
    assert [item.name for item in after_archive.video_types] == ["电影混剪"]


def test_search_uses_any_video_type_and_returns_each_row_once(tmp_path: Path) -> None:
    service, _, _ = _populated_service(tmp_path)

    result = service.search(
        KnowledgeSearchQuery(
            stage="stage3",
            video_types=("燃向混剪", "不存在的类型"),
            knowledge_types=("editing_sentence",),
            text="重音爆发前通过密集切换逐步蓄力",
        )
    )

    assert len(result.items) == 1
    assert result.items[0].knowledge_type == "editing_sentence"
    assert isinstance(result.items[0].similarity, float)


def test_structured_filter_runs_before_vector_limit(tmp_path: Path) -> None:
    service, store, result = _populated_service(tmp_path)

    found = service.search(
        KnowledgeSearchQuery(
            stage="stage3",
            video_types=("电影混剪",),
            knowledge_types=("motion_pattern",),
            text="快切重拍密度",
            limit=1,
        )
    )

    assert [item.knowledge_type for item in found.items] == ["motion_pattern"]
    store.archive(result.items[1].knowledge_id)
    assert service.search(
        KnowledgeSearchQuery(
            stage="stage3",
            video_types=("电影混剪",),
            knowledge_types=("motion_pattern",),
            text="横向移动",
        )
    ).items == ()


def test_filter_literals_with_quotes_are_escaped(tmp_path: Path) -> None:
    service, _, _ = make_service(tmp_path)
    publish(service, draft(video_types=("导演's Cut",)))

    result = service.search(
        KnowledgeSearchQuery(
            stage="stage3",
            video_types=("导演's Cut",),
            knowledge_types=("editing_sentence",),
            text="快切",
        )
    )

    assert len(result.items) == 1


def test_merge_new_video_type_is_immediately_searchable(tmp_path: Path) -> None:
    service, _, _ = make_service(tmp_path)
    knowledge_id = publish(service, draft()).items[0].knowledge_id
    materialize_succeeded_analysis(tmp_path, analysis_id="analysis_second")

    publish(
        service,
        draft(
            local_id="K002",
            analysis_id="analysis_second",
            evidence_id="frame_000002",
            existing_knowledge_id=knowledge_id,
            video_types=("新类型",),
        ),
        analysis_id="analysis_second",
    )

    found = service.search(
        KnowledgeSearchQuery(
            stage="stage3",
            video_types=("新类型",),
            knowledge_types=("editing_sentence",),
            text="密集切换后在重拍释放",
        )
    )
    assert [item.knowledge_id for item in found.items] == [knowledge_id]


def test_stage_type_reader_refreshes_after_another_store_publishes(tmp_path: Path) -> None:
    writer, _, _ = make_service(tmp_path)
    publish(writer, draft())
    reader, _, _ = make_service(tmp_path)
    assert [item.name for item in reader.list_stage_types("stage3").video_types] == [
        "动漫 MAD"
    ]

    publish(
        writer,
        draft(
            local_id="K002",
            evidence_id="frame_000002",
            video_types=("电影混剪",),
            knowledge_type="motion_pattern",
        ),
    )

    assert [item.name for item in reader.list_stage_types("stage3").video_types] == [
        "动漫 MAD",
        "电影混剪",
    ]


def test_search_does_not_rebuild_healthy_indices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, store, _ = make_service(tmp_path)
    publish(service, draft())
    table = store._table()

    def unexpected_maintenance(*_: object, **__: object) -> None:
        raise AssertionError("健康索引不应重建")

    monkeypatch.setattr(table, "create_index", unexpected_maintenance)
    monkeypatch.setattr(table, "optimize", unexpected_maintenance)

    found = service.search(
        KnowledgeSearchQuery(
            stage="stage3",
            video_types=("动漫 MAD",),
            knowledge_types=("editing_sentence",),
            text="快切重拍",
        )
    )
    assert len(found.items) == 1


def test_healthy_search_skips_full_row_embedding_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, store, _ = make_service(tmp_path)
    publish(service, draft())

    def unexpected_full_scan(*_: object, **__: object) -> None:
        raise AssertionError("健康向量空间不应加载全部知识正文和向量")

    monkeypatch.setattr(store, "list_stored", unexpected_full_scan)

    found = service.search(
        KnowledgeSearchQuery(
            stage="stage3",
            video_types=("动漫 MAD",),
            knowledge_types=("editing_sentence",),
            text="快切重拍",
        )
    )

    assert len(found.items) == 1
