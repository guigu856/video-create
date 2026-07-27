"""维护固定 rules、skills 与 schema 的版本化目录。

本模块从源码或安装数据目录加载受控内容，校验最低结构，计算文件哈希，并通过稳定 URI
提供目录发现与精确读取；调用方不直接传入任意文件路径。
"""

import hashlib
import json
import sysconfig
from pathlib import Path
from typing import Annotated, Literal, NamedTuple

import yaml
from pydantic import Field, JsonValue

from video_create_plugin.contracts import PluginModel, Sha256, StableId
from video_create_plugin.errors import PluginError

ContentKind = Literal["rule", "skill", "schema"]
ContentVersion = Annotated[str, Field(pattern=r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")]
ContentUri = Annotated[str, Field(pattern=r"^video-create://[a-z0-9_/-]+$")]


class CatalogEntry(PluginModel):
    content_id: StableId
    version: ContentVersion
    kind: ContentKind
    uri: ContentUri
    content_sha256: Sha256
    mime_type: str = Field(min_length=1)


class CatalogDocument(PluginModel):
    schema_version: Literal["1.0"] = "1.0"
    entries: tuple[CatalogEntry, ...]


class _ContentSpec(NamedTuple):
    content_id: str
    version: str
    kind: ContentKind
    uri: str
    relative_path: str
    mime_type: str


_CONTENT = (
    _ContentSpec(
        "rule_main_agent",
        "1.0.0",
        "rule",
        "video-create://rules/main-agent",
        "rules/main-agent.md",
        "text/markdown",
    ),
    _ContentSpec(
        "schema_common",
        "1.0.0",
        "schema",
        "video-create://schemas/common",
        "schemas/common.schema.json",
        "application/schema+json",
    ),
    _ContentSpec(
        "schema_catalog",
        "1.0.0",
        "schema",
        "video-create://schemas/catalog",
        "schemas/catalog.schema.json",
        "application/schema+json",
    ),
)


class ContextCatalog:
    def __init__(self, content_root: Path | None = None) -> None:
        self._content_root = content_root or self._default_content_root()
        self._content: dict[str, str] = {}
        entries: list[CatalogEntry] = []
        for spec in _CONTENT:
            content, digest = self._load(spec)
            self._content[spec.uri] = content
            entries.append(
                CatalogEntry(
                    content_id=spec.content_id,
                    version=spec.version,
                    kind=spec.kind,
                    uri=spec.uri,
                    content_sha256=digest,
                    mime_type=spec.mime_type,
                )
            )
        self._document = CatalogDocument(entries=tuple(entries))

    def document(self) -> CatalogDocument:
        return self._document

    def read(self, uri: str) -> str:
        try:
            return self._content[uri]
        except KeyError as error:
            raise PluginError(
                "context_content_not_found",
                "上下文资源不存在",
                details={"uri": uri},
            ) from error

    def _load(self, spec: _ContentSpec) -> tuple[str, str]:
        path = self._content_root / spec.relative_path
        try:
            raw = path.read_bytes()
            content = raw.decode("utf-8")
            self._validate(spec, content)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
            details: dict[str, JsonValue] = {"path": spec.relative_path}
            raise PluginError(
                "context_content_invalid",
                "上下文资源校验失败",
                details=details,
            ) from error
        return content, hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _validate(spec: _ContentSpec, content: str) -> None:
        if spec.kind == "rule" and not content.strip():
            raise ValueError("rule 内容不能为空")
        if spec.kind == "schema":
            if not isinstance(json.loads(content), dict):
                raise ValueError("schema 必须是 JSON object")
        if spec.kind == "skill":
            lines = content.splitlines()
            if len(lines) < 4 or lines[0] != "---" or "---" not in lines[1:]:
                raise ValueError("skill 缺少 frontmatter")
            end = lines[1:].index("---") + 1
            try:
                metadata = yaml.safe_load("\n".join(lines[1:end]))
            except yaml.YAMLError as error:
                raise ValueError("skill frontmatter 不是合法 YAML") from error
            if not isinstance(metadata, dict):
                raise ValueError("skill frontmatter 必须是 mapping")
            expected_name = spec.uri.rsplit("/", 1)[-1]
            name = metadata.get("name")
            if not isinstance(name, str) or name.strip() != expected_name:
                raise ValueError("skill name 与资源 URI 不匹配")
            description = metadata.get("description")
            if not isinstance(description, str) or not description.strip():
                raise ValueError("skill description 不能为空")

    @staticmethod
    def _default_content_root() -> Path:
        source_root = Path(__file__).resolve().parents[2]
        if (source_root / "rules/main-agent.md").is_file():
            return source_root
        return Path(sysconfig.get_path("data")) / "share/video-create"
