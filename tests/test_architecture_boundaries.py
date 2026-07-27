"""验证源码树遵守组件、MCP、应用服务与持久化适配层之间的依赖方向。"""

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _imports(relative_path: Path, source: str) -> set[str]:
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    imported.add(node.module)
                continue

            package_parts = relative_path.parent.parts
            base_parts = package_parts[: len(package_parts) - node.level + 1]
            if node.module:
                imported.add(".".join((*base_parts, node.module)))
            else:
                imported.update(".".join((*base_parts, alias.name)) for alias in node.names)
    return imported


def _forbidden_imports(relative_path: Path, source: str) -> set[str]:
    imported = _imports(relative_path, source)
    if relative_path.parts[0] == "components":
        return {
            name
            for name in imported
            if name == "video_create_plugin" or name.startswith("video_create_plugin.")
        }

    if relative_path.parts[:2] == ("video_create_plugin", "mcp"):
        return set()

    forbidden_prefixes = ("video_create_plugin.mcp",)
    if relative_path.parts[:2] == ("video_create_plugin", "repository"):
        forbidden_prefixes += ("video_create_plugin.application",)
    return {
        name
        for name in imported
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    }


def test_source_tree_respects_dependency_direction() -> None:
    violations: list[str] = []
    for source_root in (ROOT / "components", ROOT / "video_create_plugin"):
        for path in source_root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            relative_path = path.relative_to(ROOT)
            forbidden = _forbidden_imports(
                relative_path,
                path.read_text(encoding="utf-8"),
            )
            if forbidden:
                violations.append(f"{relative_path}: {', '.join(sorted(forbidden))}")

    assert not violations, "\n".join(violations)


def test_boundary_rules_detect_reverse_imports() -> None:
    assert _forbidden_imports(
        Path("components/video_editor/service.py"),
        "from video_create_plugin.mcp import server",
    ) == {"video_create_plugin.mcp"}
    assert _forbidden_imports(
        Path("video_create_plugin/repository/workflow.py"),
        "from video_create_plugin.application import workflow",
    ) == {"video_create_plugin.application"}
    assert _forbidden_imports(
        Path("video_create_plugin/application/workflow.py"),
        "from video_create_plugin.mcp import workflow",
    ) == {"video_create_plugin.mcp"}
    assert _forbidden_imports(
        Path("video_create_plugin/application/workflow.py"),
        "from ..mcp import workflow",
    ) == {"video_create_plugin.mcp"}
    assert _forbidden_imports(
        Path("video_create_plugin/repository/workflow.py"),
        "from ..application import workflow",
    ) == {"video_create_plugin.application"}
