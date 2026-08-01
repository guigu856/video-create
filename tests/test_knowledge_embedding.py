"""验证固定中文模型资产、离线加载和发布检索共用的 512 维空间。"""

from __future__ import annotations

import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

import video_create_plugin.knowledge.embedding as embedding_module
from video_create_plugin.errors import PluginError
from video_create_plugin.knowledge.embedding import (
    MODEL_DIMENSION,
    MODEL_NAME,
    MODEL_SHA256,
    MODEL_VERSION,
    LocalEmbeddingService,
)

ROOT = Path(__file__).parents[1]
ASSET_DIR = ROOT / "video_create_plugin/assets/models/bge-small-zh-v1.5"


def test_checked_in_metadata_matches_runtime_embedding_contract() -> None:
    metadata = json.loads((ASSET_DIR / "MODEL_METADATA.json").read_text(encoding="utf-8"))
    service = LocalEmbeddingService(ASSET_DIR)

    service.validate_assets()
    assert metadata["model_name"] == MODEL_NAME == service.metadata.model
    assert metadata["runtime_revision"] == MODEL_VERSION == service.metadata.version
    assert metadata["bundle_sha256"] == MODEL_SHA256 == service.metadata.sha256
    assert metadata["embedding_dimension"] == MODEL_DIMENSION == 512
    assert sum(item["size"] for item in metadata["files"]) == 95_221_432


def test_missing_model_asset_has_stable_error(tmp_path: Path) -> None:
    service = LocalEmbeddingService(tmp_path)

    with pytest.raises(PluginError) as caught:
        service.validate_assets()

    assert caught.value.code == "embedding_assets_invalid"


def test_model_loads_from_plugin_assets_with_offline_caches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HF_HOME", str(tmp_path / "empty-hf"))
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path / "empty-fastembed"))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    service = LocalEmbeddingService(ASSET_DIR)

    documents = service.embed_documents(
        (
            "在重拍释放前使用连续快切逐步积累视觉密度。",
            "量子力学讨论微观粒子的波函数。",
        )
    )
    query = service.embed_query("高潮爆发之前先用密集镜头完成蓄力")

    assert all(len(vector) == 512 for vector in (*documents, query))
    assert all(math.isfinite(value) for vector in (*documents, query) for value in vector)
    assert _cosine(query, documents[0]) > _cosine(query, documents[1])


def test_concurrent_first_load_initializes_one_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor_calls = 0
    constructor_guard = threading.Lock()
    first_constructor_entered = threading.Event()
    second_constructor_entered = threading.Event()
    release_constructor = threading.Event()
    second_call_started = threading.Event()

    class BlockingTextEmbedding:
        def __init__(self, **_: object) -> None:
            nonlocal constructor_calls
            with constructor_guard:
                constructor_calls += 1
                if constructor_calls == 1:
                    first_constructor_entered.set()
                else:
                    second_constructor_entered.set()
            if not release_constructor.wait(timeout=5):
                raise TimeoutError("测试未释放模型构造")

    service = LocalEmbeddingService(tmp_path)
    monkeypatch.setattr(service, "validate_assets", lambda: None)
    monkeypatch.setattr(
        embedding_module,
        "import_module",
        lambda _: SimpleNamespace(TextEmbedding=BlockingTextEmbedding),
    )

    def load_second() -> object:
        second_call_started.set()
        return service._load_model()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service._load_model)
        assert first_constructor_entered.wait(timeout=2)
        second = executor.submit(load_second)
        assert second_call_started.wait(timeout=2)
        second_constructor_entered.wait(timeout=0.5)
        release_constructor.set()
        first_model = first.result(timeout=2)
        second_model = second.result(timeout=2)

    assert constructor_calls == 1
    assert first_model is second_model


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(first * second for first, second in zip(left, right, strict=True))
