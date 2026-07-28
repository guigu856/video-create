"""验证知识发布发生在确认之后，并保持报告、媒体和证据来源。"""

from pathlib import Path

import pytest
from test_reference_reporting import _materialize_evidence

from video_create_plugin.application.knowledge import KnowledgeService
from video_create_plugin.errors import PluginError
from video_create_plugin.knowledge.models import KnowledgeUnitDraft, PublicationRequest
from video_create_plugin.knowledge.store import KnowledgeStore
from video_create_plugin.reporting.generator import ReferenceReportGenerator


def _generated_report(root: Path):
    report = _materialize_evidence(root)
    output = ReferenceReportGenerator(root).generate(report, root / "reports/example")
    return report, output


def _drafts(report):
    return tuple(
        KnowledgeUnitDraft(
            applicable_stages=(item.applicable_stage,),
            knowledge_type=item.knowledge_type,
            content=item.content,
            evidence_refs=item.evidence_refs,
            fact_status=item.fact_status,
            confidence=item.confidence,
            visibility="creation_shared",
            transferability="reusable_mechanism",
            granularity="global",
        )
        for item in report.creation_context_projection.all_items()
    )


def test_preview_does_not_publish_and_confirmation_persists_sources(
    tmp_path: Path,
) -> None:
    report, output = _generated_report(tmp_path)
    store = KnowledgeStore(tmp_path / "output/plugin/knowledge.sqlite3")
    service = KnowledgeService(tmp_path, store)
    drafts = _drafts(report)

    preview = service.preview(output.manifest_file, drafts)
    assert len(preview.units) == 3
    assert store.list_all() == ()

    with pytest.raises(PluginError) as caught:
        service.publish(
            PublicationRequest(
                user_confirmed=False,
                manifest_file=output.manifest_file,
                units=drafts,
            )
        )
    assert caught.value.code == "knowledge_publication_rejected"
    assert store.list_all() == ()

    published = service.publish(
        PublicationRequest(
            user_confirmed=True,
            manifest_file=output.manifest_file,
            units=drafts,
        )
    )

    assert len(published.units) == 3
    for unit in published.units:
        assert unit.source_report_path == output.manifest.file_for("structured_report").path
        assert unit.source_report_sha256 == output.manifest.file_for("structured_report").sha256
        assert unit.source_media_sha256 == report.source_media_sha256
        assert unit.evidence_refs


def test_missing_or_modified_report_is_rejected(tmp_path: Path) -> None:
    report, output = _generated_report(tmp_path)
    service = KnowledgeService(
        tmp_path,
        KnowledgeStore(tmp_path / "output/plugin/knowledge.sqlite3"),
    )
    request = PublicationRequest(
        user_confirmed=True,
        manifest_file=output.manifest_file,
        units=_drafts(report),
    )

    manifest_path = tmp_path / output.manifest_file.path
    manifest_path.unlink()
    with pytest.raises(PluginError) as missing:
        service.publish(request)
    assert missing.value.code == "file_not_found"

    output = ReferenceReportGenerator(tmp_path).generate(report, tmp_path / "reports/example")
    manifest_path = tmp_path / output.manifest_file.path
    manifest_path.write_text("modified", encoding="utf-8")
    with pytest.raises(PluginError) as modified:
        service.publish(request.model_copy(update={"manifest_file": output.manifest_file}))
    assert modified.value.code == "file_hash_mismatch"


def test_evidence_only_unit_uses_isolated_collection(tmp_path: Path) -> None:
    report, output = _generated_report(tmp_path)
    store = KnowledgeStore(tmp_path / "output/plugin/knowledge.sqlite3")
    service = KnowledgeService(tmp_path, store)
    draft = KnowledgeUnitDraft(
        applicable_stages=("stage3",),
        knowledge_type="effect_scope",
        content="原片人物在 0.5 秒出现专属闪白",
        evidence_refs=("frame_000001",),
        fact_status="agent_inference",
        confidence=0.7,
        visibility="evidence_only",
        transferability="reference_specific",
        granularity="shot",
    )

    result = service.publish(
        PublicationRequest(
            user_confirmed=True,
            manifest_file=output.manifest_file,
            units=(draft,),
        )
    )

    assert result.units[0].collection == "reference_evidence"
    assert store.list_all()[0].collection == "reference_evidence"
