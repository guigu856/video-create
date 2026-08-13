"""验证 Context Catalog 的固定内容、稳定错误以及 MCP Resource 列出与读取闭环。"""

import asyncio
import json
import shutil
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from video_create_plugin.context.catalog import CatalogDocument, ContextCatalog
from video_create_plugin.errors import PluginError
from video_create_plugin.mcp.server import create_server

ROOT = Path(__file__).parents[1]


def _copy_fixed_content(target: Path) -> None:
    (target / "rules").mkdir()
    shutil.copy2(ROOT / "rules/main-agent.md", target / "rules/main-agent.md")
    shutil.copytree(ROOT / "schemas", target / "schemas")


def test_catalog_lists_fixed_versioned_content() -> None:
    catalog = ContextCatalog(ROOT)

    entries = catalog.document().entries

    assert [(entry.content_id, entry.version, entry.kind, entry.uri) for entry in entries] == [
        ("rule_main_agent", "1.0.0", "rule", "video-create://rules/main-agent"),
        (
            "rule_reference_study_agent",
            "1.2.0",
            "rule",
            "video-create://rules/reference-study-agent",
        ),
        (
            "skill_audiovisual_relation_analysis",
            "1.2.0",
            "skill",
            "video-create://skills/audiovisual-relation-analysis",
        ),
        (
            "skill_editing_grammar_synthesis",
            "1.2.0",
            "skill",
            "video-create://skills/editing-grammar-synthesis",
        ),
        (
            "skill_reference_bgm_analysis",
            "1.2.0",
            "skill",
            "video-create://skills/reference-bgm-analysis",
        ),
        (
            "skill_reference_study",
            "1.2.0",
            "skill",
            "video-create://skills/reference-study",
        ),
        (
            "skill_reference_visual_analysis",
            "1.2.0",
            "skill",
            "video-create://skills/reference-visual-analysis",
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


def test_rule_content_does_not_require_a_markdown_heading(tmp_path: Path) -> None:
    _copy_fixed_content(tmp_path)
    content = "识别任务类型，并进入对应阶段。\n"
    rule_path = tmp_path / "rules/main-agent.md"
    rule_path.write_text(content, encoding="utf-8")

    catalog = ContextCatalog(tmp_path)

    assert catalog.read("video-create://rules/main-agent") == rule_path.read_bytes().decode("utf-8")


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
    _copy_fixed_content(tmp_path)
    (tmp_path / relative_path).write_text(invalid_content, encoding="utf-8")

    with pytest.raises(PluginError) as caught:
        ContextCatalog(tmp_path)

    assert caught.value.code == "context_content_invalid"
    assert caught.value.details["path"] == relative_path


def test_catalog_schema_matches_model() -> None:
    checked_in = json.loads((ROOT / "schemas/catalog.schema.json").read_text(encoding="utf-8"))

    assert checked_in == CatalogDocument.model_json_schema()


def _write_example_skill(
    tmp_path: Path,
    content: str,
) -> None:
    _copy_fixed_content(tmp_path)
    skill_path = tmp_path / "skills/example-skill/SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(content, encoding="utf-8")


def test_catalog_discovers_role_rules_and_skills(tmp_path: Path) -> None:
    _copy_fixed_content(tmp_path)
    role_path = tmp_path / "rules/roles/editing-specification-agent.md"
    role_path.parent.mkdir(parents=True)
    role_path.write_text(
        "---\n"
        "role_id: editing-specification-agent\n"
        "version: 1.2.0\n"
        "description: 生成逐镜编辑规格\n"
        "---\n"
        "只读取当前阶段允许的冻结输入。\n",
        encoding="utf-8",
    )
    skill_path = tmp_path / "skills/editing-specification/SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\n"
        "name: editing-specification\n"
        "description: 生成逐镜表和编辑规格\n"
        "metadata:\n"
        "  resource_version: 2.0.0\n"
        "---\n"
        "执行规格生成步骤。\n",
        encoding="utf-8",
    )

    catalog = ContextCatalog(tmp_path)

    entries = catalog.document().entries
    assert [(entry.content_id, entry.version, entry.kind, entry.uri) for entry in entries] == [
        ("rule_main_agent", "1.0.0", "rule", "video-create://rules/main-agent"),
        (
            "rule_editing_specification_agent",
            "1.2.0",
            "rule",
            "video-create://rules/editing-specification-agent",
        ),
        (
            "skill_editing_specification",
            "2.0.0",
            "skill",
            "video-create://skills/editing-specification",
        ),
        ("schema_common", "1.0.0", "schema", "video-create://schemas/common"),
        ("schema_catalog", "1.0.0", "schema", "video-create://schemas/catalog"),
    ]
    assert catalog.read(entries[1].uri) == role_path.read_bytes().decode("utf-8")
    assert catalog.read(entries[2].uri) == skill_path.read_bytes().decode("utf-8")

    async def verify_registered_resources() -> None:
        server = create_server(tmp_path)
        resources = await server.list_resources()
        uris = {str(resource.uri) for resource in resources}
        assert "video-create://rules/editing-specification-agent" in uris
        assert "video-create://skills/editing-specification" in uris
        role = await server.read_resource("video-create://rules/editing-specification-agent")
        skill = await server.read_resource("video-create://skills/editing-specification")
        assert role[0].content == role_path.read_bytes().decode("utf-8")
        assert skill[0].content == skill_path.read_bytes().decode("utf-8")

    asyncio.run(verify_registered_resources())


def test_registered_skill_accepts_yaml_quoted_name(
    tmp_path: Path,
) -> None:
    _write_example_skill(
        tmp_path,
        '---\nname: "example-skill"\ndescription: 示例\n'
        "metadata:\n  resource_version: 1.0.0\n---\n执行步骤。\n",
    )

    catalog = ContextCatalog(tmp_path)

    assert catalog.read("video-create://skills/example-skill")


@pytest.mark.parametrize(
    "content",
    [
        "---\nname: wrong\ndescription: 示例\n"
        "metadata:\n  resource_version: 1.0.0\n---\n执行步骤。\n",
        "---\nname: example-skill\ndescription: >\n"
        "metadata:\n  resource_version: 1.0.0\n---\n执行步骤。\n",
        "---\nname: example-skill\ndescription: 示例\n---\n执行步骤。\n",
    ],
)
def test_invalid_registered_skill_has_stable_error(
    tmp_path: Path,
    content: str,
) -> None:
    _write_example_skill(tmp_path, content)

    with pytest.raises(PluginError) as caught:
        ContextCatalog(tmp_path)

    assert caught.value.code == "context_content_invalid"
    assert caught.value.details["path"] == "skills/example-skill/SKILL.md"


@pytest.mark.parametrize(
    "content",
    [
        "---\nrole_id: wrong\nversion: 1.0.0\ndescription: 示例\n---\n角色规则。\n",
        "---\nrole_id: example-agent\ndescription: 示例\n---\n角色规则。\n",
    ],
)
def test_invalid_registered_role_rule_has_stable_error(
    tmp_path: Path,
    content: str,
) -> None:
    _copy_fixed_content(tmp_path)
    role_path = tmp_path / "rules/roles/example-agent.md"
    role_path.parent.mkdir(parents=True)
    role_path.write_text(content, encoding="utf-8")

    with pytest.raises(PluginError) as caught:
        ContextCatalog(tmp_path)

    assert caught.value.code == "context_content_invalid"
    assert caught.value.details["path"] == "rules/roles/example-agent.md"


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
                    "video-create://rules/reference-study-agent",
                    "video-create://skills/audiovisual-relation-analysis",
                    "video-create://skills/editing-grammar-synthesis",
                    "video-create://skills/reference-bgm-analysis",
                    "video-create://skills/reference-study",
                    "video-create://skills/reference-visual-analysis",
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
