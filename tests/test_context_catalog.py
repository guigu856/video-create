"""验证 Context Catalog 的固定内容、稳定错误以及 MCP Resource 列出与读取闭环。"""

import asyncio
import json
import shutil
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from video_create_plugin.context import catalog as catalog_module
from video_create_plugin.context.catalog import CatalogDocument, ContextCatalog
from video_create_plugin.errors import PluginError

ROOT = Path(__file__).parents[1]


def test_catalog_lists_fixed_versioned_content() -> None:
    catalog = ContextCatalog(ROOT)

    entries = catalog.document().entries

    assert [(entry.content_id, entry.version, entry.kind, entry.uri) for entry in entries] == [
        ("rule_main_agent", "1.0.0", "rule", "video-create://rules/main-agent"),
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
        ("schemas/common.schema.json", "{"),
    ],
)
def test_invalid_context_content_has_stable_error(
    tmp_path: Path,
    relative_path: str,
    invalid_content: str,
) -> None:
    for directory in ("rules", "schemas"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    (tmp_path / relative_path).write_text(invalid_content, encoding="utf-8")

    with pytest.raises(PluginError) as caught:
        ContextCatalog(tmp_path)

    assert caught.value.code == "context_content_invalid"
    assert caught.value.details["path"] == relative_path


def test_catalog_schema_matches_model() -> None:
    checked_in = json.loads((ROOT / "schemas/catalog.schema.json").read_text(encoding="utf-8"))

    assert checked_in == CatalogDocument.model_json_schema()


def test_invalid_registered_skill_has_stable_error(tmp_path: Path, monkeypatch) -> None:
    for directory in ("rules", "schemas"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    skill_path = tmp_path / "skills/example-skill/SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("---\nname: wrong\n---\n", encoding="utf-8")
    skill = catalog_module._ContentSpec(
        "skill_example",
        "1.0.0",
        "skill",
        "video-create://skills/example-skill",
        "skills/example-skill/SKILL.md",
        "text/markdown",
    )
    monkeypatch.setattr(catalog_module, "_CONTENT", (*catalog_module._CONTENT, skill))

    with pytest.raises(PluginError) as caught:
        ContextCatalog(tmp_path)

    assert caught.value.code == "context_content_invalid"
    assert caught.value.details["path"] == "skills/example-skill/SKILL.md"


def test_stdio_resources_list_and_read_context() -> None:
    async def verify_resources() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "video_create_plugin.mcp.server"],
            cwd=ROOT,
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_resources()
                uris = {str(resource.uri) for resource in listed.resources}
                assert uris == {
                    "video-create://catalog",
                    "video-create://rules/main-agent",
                    "video-create://schemas/common",
                    "video-create://schemas/catalog",
                }

                catalog = await session.read_resource("video-create://catalog")
                catalog_text = catalog.contents[0].text
                assert json.loads(catalog_text)["schema_version"] == "1.0"

                rule = await session.read_resource("video-create://rules/main-agent")
                assert rule.contents[0].text == (ROOT / "rules/main-agent.md").read_text(
                    encoding="utf-8"
                )

    asyncio.run(verify_resources())
