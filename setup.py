from pathlib import Path


def _data_files(root: Path) -> list[tuple[str, list[str]]]:
    entries = [
        ("share/video-create", [".mcp.json"]),
        ("share/video-create/.codex-plugin", [".codex-plugin/plugin.json"]),
        ("share/video-create/.claude-plugin", [".claude-plugin/plugin.json"]),
        ("share/video-create/rules", ["rules/main-agent.md"]),
        (
            "share/video-create/schemas",
            [
                "schemas/catalog.schema.json",
                "schemas/common.schema.json",
            ],
        ),
        ("share/video-create/skills", ["skills/README.md"]),
    ]
    role_rules = [
        path.relative_to(root).as_posix()
        for path in sorted((root / "rules/roles").glob("*.md"))
    ]
    if role_rules:
        entries.append(("share/video-create/rules/roles", role_rules))
    for path in sorted((root / "skills").glob("*/SKILL.md")):
        relative_path = path.relative_to(root)
        entries.append(
            (
                f"share/video-create/{relative_path.parent.as_posix()}",
                [relative_path.as_posix()],
            )
        )
    return entries


if __name__ == "__main__":
    from setuptools import setup

    setup(data_files=_data_files(Path(__file__).parent))
