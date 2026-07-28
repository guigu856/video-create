"""维护固定内容与受控发现的角色 Rule、Skill 版本化目录。

本模块从源码或安装数据目录加载受控内容，校验最低结构，计算文件哈希，并通过稳定 URI
提供目录发现与精确读取；调用方不直接传入任意文件路径。
"""

import hashlib
import json
import re
import sysconfig
from pathlib import Path
from typing import Annotated, Literal, NamedTuple, NoReturn

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


_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_VERSION_PATTERN = re.compile(r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")

_FIXED_RULES = (
    _ContentSpec(
        "rule_main_agent",
        "1.0.0",
        "rule",
        "video-create://rules/main-agent",
        "rules/main-agent.md",
        "text/markdown",
    ),
)

_FIXED_SCHEMAS = (
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
    _ContentSpec(
        "schema_reference_study",
        "1.0.0",
        "schema",
        "video-create://schemas/reference-study",
        "schemas/reference-study.schema.json",
        "application/schema+json",
    ),
)


class ContextCatalog:
    def __init__(self, content_root: Path | None = None) -> None:
        self._content_root = content_root or self._default_content_root()
        self._content: dict[str, str] = {}
        entries: list[CatalogEntry] = []
        specs = (
            *_FIXED_RULES,
            *self._discover_role_rules(),
            *self._discover_skills(),
            *_FIXED_SCHEMAS,
        )
        self._validate_unique_specs(specs)
        for spec in specs:
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

    def _discover_role_rules(self) -> tuple[_ContentSpec, ...]:
        root = self._content_root / "rules/roles"
        return tuple(self._role_rule_spec(path) for path in sorted(root.glob("*.md")))

    def _discover_skills(self) -> tuple[_ContentSpec, ...]:
        root = self._content_root / "skills"
        return tuple(self._skill_spec(path) for path in sorted(root.glob("*/SKILL.md")))

    def _role_rule_spec(self, path: Path) -> _ContentSpec:
        relative_path, metadata = self._read_metadata(path)
        try:
            role_id = self._required_string(metadata, "role_id")
            version = self._required_string(metadata, "version")
            self._required_string(metadata, "description")
            self._validate_name(role_id)
            self._validate_version(version)
            if role_id != path.stem:
                raise ValueError("role_id 与文件名不匹配")
        except ValueError as error:
            self._raise_invalid(relative_path, error)
        return _ContentSpec(
            f"rule_{role_id.replace('-', '_')}",
            version,
            "rule",
            f"video-create://rules/{role_id}",
            relative_path,
            "text/markdown",
        )

    def _skill_spec(self, path: Path) -> _ContentSpec:
        relative_path, frontmatter = self._read_metadata(path)
        try:
            name = self._required_string(frontmatter, "name")
            self._required_string(frontmatter, "description")
            metadata = frontmatter.get("metadata")
            if not isinstance(metadata, dict):
                raise ValueError("skill metadata 必须是 mapping")
            version = self._required_string(metadata, "resource_version")
            self._validate_name(name)
            self._validate_version(version)
            if name != path.parent.name:
                raise ValueError("skill name 与目录名不匹配")
        except ValueError as error:
            self._raise_invalid(relative_path, error)
        return _ContentSpec(
            f"skill_{name.replace('-', '_')}",
            version,
            "skill",
            f"video-create://skills/{name}",
            relative_path,
            "text/markdown",
        )

    def _read_metadata(self, path: Path) -> tuple[str, dict[object, object]]:
        relative_path = path.relative_to(self._content_root).as_posix()
        try:
            if not path.resolve().is_relative_to(self._content_root.resolve()):
                raise ValueError("内容路径越界")
            content = path.read_bytes().decode("utf-8")
            return relative_path, self._parse_frontmatter(content)
        except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as error:
            self._raise_invalid(relative_path, error)

    @classmethod
    def _validate(cls, spec: _ContentSpec, content: str) -> None:
        if spec.kind == "rule":
            if not content.strip():
                raise ValueError("rule 内容不能为空")
            if spec.uri != "video-create://rules/main-agent":
                metadata = cls._parse_frontmatter(content)
                role_id = cls._required_string(metadata, "role_id")
                version = cls._required_string(metadata, "version")
                cls._required_string(metadata, "description")
                if role_id != spec.uri.rsplit("/", 1)[-1] or version != spec.version:
                    raise ValueError("role frontmatter 与资源目录不匹配")
        if spec.kind == "schema":
            if not isinstance(json.loads(content), dict):
                raise ValueError("schema 必须是 JSON object")
        if spec.kind == "skill":
            metadata = cls._parse_frontmatter(content)
            expected_name = spec.uri.rsplit("/", 1)[-1]
            name = metadata.get("name")
            if not isinstance(name, str) or name.strip() != expected_name:
                raise ValueError("skill name 与资源 URI 不匹配")
            description = metadata.get("description")
            if not isinstance(description, str) or not description.strip():
                raise ValueError("skill description 不能为空")
            resource_metadata = metadata.get("metadata")
            if not isinstance(resource_metadata, dict):
                raise ValueError("skill metadata 必须是 mapping")
            skill_version = resource_metadata.get("resource_version")
            if not isinstance(skill_version, str) or skill_version.strip() != spec.version:
                raise ValueError("skill resource_version 与资源目录不匹配")

    @staticmethod
    def _parse_frontmatter(content: str) -> dict[object, object]:
        lines = content.splitlines()
        if len(lines) < 4 or lines[0] != "---" or "---" not in lines[1:]:
            raise ValueError("内容缺少 frontmatter")
        end = lines[1:].index("---") + 1
        try:
            metadata = yaml.safe_load("\n".join(lines[1:end]))
        except yaml.YAMLError as error:
            raise ValueError("frontmatter 不是合法 YAML") from error
        if not isinstance(metadata, dict):
            raise ValueError("frontmatter 必须是 mapping")
        return metadata

    @staticmethod
    def _required_string(metadata: dict[object, object], key: str) -> str:
        value = metadata.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} 必须是非空字符串")
        return value.strip()

    @staticmethod
    def _validate_name(value: str) -> None:
        if _NAME_PATTERN.fullmatch(value) is None:
            raise ValueError("资源名称格式无效")

    @staticmethod
    def _validate_version(value: str) -> None:
        if _VERSION_PATTERN.fullmatch(value) is None:
            raise ValueError("资源版本格式无效")

    def _validate_unique_specs(self, specs: tuple[_ContentSpec, ...]) -> None:
        content_ids: set[str] = set()
        uris: set[str] = set()
        for spec in specs:
            if spec.content_id in content_ids or spec.uri in uris:
                self._raise_invalid(spec.relative_path, ValueError("资源 ID 或 URI 重复"))
            content_ids.add(spec.content_id)
            uris.add(spec.uri)

    @staticmethod
    def _raise_invalid(relative_path: str, error: Exception) -> NoReturn:
        details: dict[str, JsonValue] = {"path": relative_path}
        raise PluginError(
            "context_content_invalid",
            "上下文资源校验失败",
            details=details,
        ) from error

    @staticmethod
    def _default_content_root() -> Path:
        source_root = Path(__file__).resolve().parents[2]
        if (source_root / "rules/main-agent.md").is_file():
            return source_root
        return Path(sysconfig.get_path("data")) / "share/video-create"
