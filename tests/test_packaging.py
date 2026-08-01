"""验证插件上下文内容按运行时目录结构进入分发包。"""

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

ROOT = Path(__file__).parents[1]
DataFilesBuilder = Callable[[Path], list[tuple[str, list[str]]]]


def test_role_rules_and_skills_are_discovered_for_packaging(tmp_path: Path) -> None:
    role_path = tmp_path / "rules/roles/example-agent.md"
    role_path.parent.mkdir(parents=True)
    role_path.write_text("角色规则", encoding="utf-8")
    skill_path = tmp_path / "skills/example-skill/SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("Skill", encoding="utf-8")

    namespace = runpy.run_path(str(ROOT / "setup.py"), run_name="video_create_setup")
    data_files = cast(DataFilesBuilder, namespace["_data_files"])(tmp_path)

    assert ("share/video-create/rules/roles", ["rules/roles/example-agent.md"]) in data_files
    assert (
        "share/video-create/skills/example-skill",
        ["skills/example-skill/SKILL.md"],
    ) in data_files


def test_obsolete_reference_report_schema_is_not_packaged() -> None:
    namespace = runpy.run_path(str(ROOT / "setup.py"), run_name="video_create_setup")
    data_files = cast(DataFilesBuilder, namespace["_data_files"])(ROOT)

    packaged = {path for _, paths in data_files for path in paths}
    assert "schemas/reference-study.schema.json" not in packaged
