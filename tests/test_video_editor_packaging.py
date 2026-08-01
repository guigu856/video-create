from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def test_wheel_contains_web_assets_and_serves_homepage_after_extraction(
    tmp_path: Path,
) -> None:
    project_root = Path(__file__).parents[1]
    source_root = tmp_path / "source"
    source_root.mkdir()
    shutil.copy2(project_root / "pyproject.toml", source_root / "pyproject.toml")
    shutil.copy2(project_root / "setup.py", source_root / "setup.py")
    shutil.copy2(project_root / ".mcp.json", source_root / ".mcp.json")
    shutil.copytree(project_root / ".codex-plugin", source_root / ".codex-plugin")
    shutil.copytree(project_root / ".claude-plugin", source_root / ".claude-plugin")
    shutil.copytree(project_root / "rules", source_root / "rules")
    shutil.copytree(project_root / "schemas", source_root / "schemas")
    shutil.copytree(project_root / "skills", source_root / "skills")
    role_path = source_root / "rules/roles/packaging-agent.md"
    role_path.parent.mkdir(parents=True, exist_ok=True)
    role_path.write_text(
        "---\nrole_id: packaging-agent\nversion: 1.0.0\n"
        "description: 验证角色 Rule 打包\n---\n角色规则。\n",
        encoding="utf-8",
    )
    skill_path = source_root / "skills/packaging-skill/SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\nname: packaging-skill\ndescription: 验证 Skill 打包\n"
        "metadata:\n  resource_version: 1.0.0\n---\n执行步骤。\n",
        encoding="utf-8",
    )
    shutil.copytree(
        project_root / "components",
        source_root / "components",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        project_root / "video_create_plugin",
        source_root / "video_create_plugin",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()

    built = subprocess.run(
        [
            "uv",
            "build",
            "--wheel",
            "--out-dir",
            str(wheel_dir),
        ],
        cwd=source_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert built.returncode == 0, built.stderr
    wheel = next(wheel_dir.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        assert "components/video_editor/web/index.html" in names
        assert "components/video_editor/web/app.js" in names
        assert any(name.endswith("share/video-create/rules/main-agent.md") for name in names)
        assert any(
            name.endswith("share/video-create/rules/roles/packaging-agent.md")
            for name in names
        )
        assert any(name.endswith("share/video-create/skills/README.md") for name in names)
        assert any(
            name.endswith("share/video-create/skills/packaging-skill/SKILL.md")
            for name in names
        )
        assert any(
            name.endswith("share/video-create/schemas/catalog.schema.json") for name in names
        )
        for model_file in (
            "config.json",
            "model_optimized.onnx",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "MODEL_METADATA.json",
            "LICENSE",
        ):
            assert (
                f"video_create_plugin/assets/models/bge-small-zh-v1.5/{model_file}" in names
            )
        site_packages = tmp_path / "site-packages"
        archive.extractall(site_packages)

    served = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from pathlib import Path; "
                f"sys.path.insert(0, {str(site_packages)!r}); "
                "import os; "
                f"os.environ['HF_HOME']={str(tmp_path / 'empty-hf')!r}; "
                f"os.environ['FASTEMBED_CACHE_PATH']={str(tmp_path / 'empty-fastembed')!r}; "
                "os.environ['HF_HUB_OFFLINE']='1'; "
                "from fastapi.testclient import TestClient; "
                "from components.video_editor.api import create_app; "
                "from video_create_plugin.knowledge.embedding import LocalEmbeddingService; "
                f"response=TestClient(create_app(Path({str(tmp_path / 'data')!r}))).get('/'); "
                "assert response.status_code == 200; "
                "assert '本地视频剪辑器' in response.text; "
                "assert len(LocalEmbeddingService().embed_query('离线模型验证')) == 512"
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert served.returncode == 0, served.stderr
