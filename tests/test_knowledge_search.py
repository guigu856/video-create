"""验证创作知识检索强制阶段、类型、可见性、可迁移性与 active 状态。"""

from pathlib import Path

from test_knowledge_publication import _drafts, _generated_report

from video_create_plugin.application.knowledge import KnowledgeService
from video_create_plugin.knowledge.models import KnowledgeSearchQuery, PublicationRequest
from video_create_plugin.knowledge.store import KnowledgeStore


def _published_service(root: Path):
    report, output = _generated_report(root)
    store = KnowledgeStore(root / "output/plugin/knowledge.sqlite3")
    service = KnowledgeService(root, store)
    result = service.publish(
        PublicationRequest(
            user_confirmed=True,
            manifest_file=output.manifest_file,
            units=_drafts(report),
        )
    )
    return service, store, output, result


def test_search_filters_stage_type_and_archived_status(tmp_path: Path) -> None:
    service, store, _, published = _published_service(tmp_path)

    stage1 = service.search(
        KnowledgeSearchQuery(
            stage="stage1",
            knowledge_types=("video_type",),
            text="类型机制",
        )
    )
    stage3 = service.search(
        KnowledgeSearchQuery(
            stage="stage3",
            knowledge_types=("editing_sentence",),
            text="建立 能量 释放",
        )
    )

    assert [item.knowledge_type for item in stage1.items] == ["video_type"]
    assert [item.knowledge_type for item in stage3.items] == ["editing_sentence"]
    archived_id = published.units[0].knowledge_id
    store.archive(archived_id)
    after_archive = service.search(
        KnowledgeSearchQuery(
            stage="stage1",
            knowledge_types=("video_type",),
        )
    )
    assert all(item.knowledge_id != archived_id for item in after_archive.items)


def test_exact_report_read_bypasses_search_index(tmp_path: Path) -> None:
    service, store, output, _ = _published_service(tmp_path)

    def fail_search(query):
        raise AssertionError("精确报告读取不应调用知识检索")

    store.search_creation = fail_search  # type: ignore[method-assign]
    content = service.read_report(output.manifest.file_for("structured_report"))

    assert '"report_id": "report_example"' in content
