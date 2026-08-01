"""加载随 Plugin 分发的固定中文模型并生成同一语义空间中的向量。"""

from __future__ import annotations

import hashlib
import math
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from video_create_plugin.errors import PluginError

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
MODEL_VERSION = "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59"
MODEL_SHA256 = "3397f52172b0179f2ad08967b2f0b1bcfa61e4e6737c93eca528683d739086e3"
MODEL_DIMENSION = 512
_MODEL_FILES = {
    "config.json": (739, "9088751d39abbf86ec3d19ffca92ad62ad19075f7e59712e6c71217fa125d1d3"),
    "model_optimized.onnx": (
        94_781_076,
        "1294ea4b6331115a353d81f96b85e8c8d7fdcc284453d5b2fab5b016230aad38",
    ),
    "special_tokens_map.json": (
        125,
        "b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3",
    ),
    "tokenizer.json": (
        439_125,
        "48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26",
    ),
    "tokenizer_config.json": (
        367,
        "e6f3b96db926a37d4039995fbf5ad17de158dfb8f6343d607e4dbaad18d75f5a",
    ),
}


@dataclass(frozen=True)
class EmbeddingMetadata:
    model: str
    version: str
    sha256: str
    dimension: int


class LocalEmbeddingService:
    def __init__(self, asset_dir: Path | None = None) -> None:
        self._asset_dir = (
            asset_dir
            if asset_dir is not None
            else Path(__file__).resolve().parents[1] / "assets/models/bge-small-zh-v1.5"
        ).resolve()
        self._model: Any | None = None
        self._model_lock = threading.Lock()
        self._assets_validated = False

    @property
    def metadata(self) -> EmbeddingMetadata:
        return EmbeddingMetadata(
            model=MODEL_NAME,
            version=MODEL_VERSION,
            sha256=MODEL_SHA256,
            dimension=MODEL_DIMENSION,
        )

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        return self._validated_vectors(self._load_model().passage_embed(texts))

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._validated_vectors(self._load_model().query_embed(text))[0]

    def validate_assets(self) -> None:
        if self._assets_validated:
            return
        for relative_path, (expected_size, expected_sha256) in _MODEL_FILES.items():
            path = self._asset_dir / relative_path
            if not path.is_file() or path.stat().st_size != expected_size:
                raise PluginError(
                    "embedding_assets_invalid",
                    "本地语义模型资产缺失或大小不符",
                    details={"path": relative_path},
                )
            if _sha256(path) != expected_sha256:
                raise PluginError(
                    "embedding_assets_invalid",
                    "本地语义模型资产哈希不匹配",
                    details={"path": relative_path},
                )
        self._assets_validated = True

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is not None:
                return self._model
            self.validate_assets()
            try:
                text_embedding = import_module("fastembed").TextEmbedding
                model = text_embedding(
                    model_name=MODEL_NAME,
                    specific_model_path=str(self._asset_dir),
                    local_files_only=True,
                )
            except Exception as error:
                raise PluginError(
                    "embedding_load_failed",
                    "本地语义模型加载失败",
                    details={"error": type(error).__name__},
                ) from error
            self._model = model
        return self._model

    def _validated_vectors(
        self,
        values: Iterable[Iterable[float]],
    ) -> tuple[tuple[float, ...], ...]:
        try:
            vectors = tuple(tuple(float(item) for item in vector) for vector in values)
        except Exception as error:
            raise PluginError("embedding_vector_invalid", "语义模型输出结构无效") from error
        if not vectors or any(
            len(vector) != MODEL_DIMENSION
            or not all(math.isfinite(item) for item in vector)
            for vector in vectors
        ):
            raise PluginError("embedding_vector_invalid", "语义模型输出向量无效")
        return vectors


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
