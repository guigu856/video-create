"""校验参考报告的证据引用闭包和可选文件哈希。"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from video_create_plugin.errors import PluginError

from .models import ReferenceStudyReport


def validate_reference_report(
    report: ReferenceStudyReport,
    workspace_root: Path | None = None,
) -> ReferenceStudyReport:
    available = {entry.evidence_id for entry in report.evidence_bundle.entries}
    missing = sorted(set(_evidence_refs(report.model_dump(mode="json"))) - available)
    if missing:
        raise PluginError(
            "evidence_not_found",
            "参考报告包含不存在的证据引用",
            details={"evidence_refs": ",".join(missing)},
        )
    if workspace_root is not None:
        root = workspace_root.resolve()
        for entry in report.evidence_bundle.entries:
            path = (root / entry.file.path).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise PluginError(
                    "file_not_found",
                    "EvidenceBundle 文件不存在",
                    details={"path": entry.file.path},
                )
            if _sha256(path) != entry.file.sha256:
                raise PluginError(
                    "file_hash_mismatch",
                    "EvidenceBundle 文件哈希不匹配",
                    details={"path": entry.file.path},
                )
    return report


def _evidence_refs(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_refs" and isinstance(item, list):
                yield from (str(reference) for reference in item)
            else:
                yield from _evidence_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _evidence_refs(item)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
