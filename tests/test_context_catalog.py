import json
import shutil
from pathlib import Path

import pytest

from video_create_plugin.context.catalog import CatalogDocument, ContextCatalog
from video_create_plugin.errors import PluginError

ROOT = Path(__file__).parents[1]


def test_catalog_lists_fixed_versioned_content() -> None:
    catalog = ContextCatalog(ROOT)

    entries = catalog.document().entries

    assert [(entry.content_id, entry.version, entry.kind, entry.uri) for entry in entries] == [
        ("rule_main_agent", "1.0.0", "rule", "video-create://rules/main-agent"),
        (
            "skill_video_task_router",
            "1.0.0",
            "skill",
            "video-create://skills/video-task-router",
        ),
        ("schema_common", "1.0.0", "schema", "video-create://schemas/common"),
        ("schema_catalog", "1.0.0", "schema", "video-create://schemas/catalog"),
    ]
    assert all(len(entry.content_sha256) == 64 for entry in entries)


def test_catalog_reads_only_the_requested_content() -> None:
    catalog = ContextCatalog(ROOT)

    content = catalog.read("video-create://rules/main-agent")

    assert content == (ROOT / "rules/main-agent.md").read_text(encoding="utf-8")
    assert "video-task-router" not in content


@pytest.mark.parametrize(
    ("relative_path", "invalid_content"),
    [
        ("rules/main-agent.md", ""),
        ("skills/video-task-router/SKILL.md", "---\nname: wrong\n---\n"),
        ("schemas/common.schema.json", "{"),
    ],
)
def test_invalid_context_content_has_stable_error(
    tmp_path: Path,
    relative_path: str,
    invalid_content: str,
) -> None:
    for directory in ("rules", "skills", "schemas"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    (tmp_path / relative_path).write_text(invalid_content, encoding="utf-8")

    with pytest.raises(PluginError) as caught:
        ContextCatalog(tmp_path)

    assert caught.value.code == "context_content_invalid"
    assert caught.value.details["path"] == relative_path


def test_catalog_schema_matches_model() -> None:
    checked_in = json.loads((ROOT / "schemas/catalog.schema.json").read_text(encoding="utf-8"))

    assert checked_in == CatalogDocument.model_json_schema()
