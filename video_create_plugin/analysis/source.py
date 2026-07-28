"""解析参考来源、固化源文件，并保存可复现的 ffprobe 技术元数据。"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import uuid
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal, Protocol

from components.video_download import DownloadConfig, DownloadResult, download_video
from video_create_plugin.contracts import FileRef
from video_create_plugin.errors import PluginError

from .models import MediaProbe, MediaStream, SourceMedia

ProbeRunner = Callable[..., subprocess.CompletedProcess[str]]


class Downloader(Protocol):
    def __call__(self, source: str, config: DownloadConfig) -> DownloadResult: ...


class SourceMediaResolver:
    def __init__(
        self,
        workspace_root: Path,
        *,
        source_dir: Path | None = None,
        downloader: Downloader = download_video,
        ffprobe_binary: str = "ffprobe",
        probe_runner: ProbeRunner | None = None,
    ) -> None:
        self._workspace_root = workspace_root.resolve()
        self._source_dir = (
            source_dir.resolve()
            if source_dir is not None
            else self._workspace_root / "output/plugin/sources"
        )
        if not self._source_dir.is_relative_to(self._workspace_root):
            raise ValueError("source_dir 必须位于 workspace_root 内")
        self._downloader = downloader
        self._ffprobe_binary = ffprobe_binary
        self._probe_runner = probe_runner or subprocess.run

    def resolve(self, source: str) -> SourceMedia:
        original = source.strip()
        if not original:
            raise PluginError("file_not_found", "参考来源为空")

        local_path = Path(original).expanduser()
        if local_path.is_file():
            source_kind: Literal["local", "download"] = "local"
            source_url = None
            acquired_path = local_path.resolve()
        elif "http://" not in original and "https://" not in original:
            raise PluginError(
                "file_not_found",
                "本地参考文件不存在",
                details={"path": original},
            )
        else:
            source_kind = "download"
            try:
                downloaded = self._downloader(
                    original,
                    DownloadConfig(output_dir=self._source_dir),
                )
            except Exception as error:
                code = getattr(error, "code", "download_failed")
                raise PluginError(
                    code,
                    str(error),
                    details={"component": "video_download"},
                ) from error
            acquired_path = Path(downloaded.file_path).resolve()
            source_url = downloaded.source_url

        if not acquired_path.is_file():
            raise PluginError(
                "file_not_found",
                "参考源文件不存在",
                details={"path": str(acquired_path)},
            )

        sha256 = _sha256(acquired_path)
        fixed_path = self._solidify(acquired_path, sha256)
        probe = self._probe(fixed_path)
        relative_path = fixed_path.relative_to(self._workspace_root).as_posix()
        return SourceMedia(
            source_id=f"source_{sha256[:16]}",
            source_kind=source_kind,
            original_input=original,
            source_url=source_url,
            file=FileRef(path=relative_path, sha256=sha256, schema_version="1.0"),
            probe=probe,
        )

    def _solidify(self, source: Path, sha256: str) -> Path:
        self._source_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower() or ".bin"
        target = self._source_dir / f"{sha256}{suffix}"
        if target.is_file():
            if _sha256(target) != sha256:
                raise PluginError("file_hash_mismatch", "已固化源文件哈希不匹配")
            return target
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            shutil.copyfile(source, temporary)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def _probe(self, path: Path) -> MediaProbe:
        argv = [
            self._ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            (
                "format=duration:"
                "stream=index,codec_type,codec_name,time_base,start_pts,duration_ts,"
                "width,height,sample_rate,channels"
            ),
            "-of",
            "json",
            str(path),
        ]
        try:
            completed = self._probe_runner(
                argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
        except FileNotFoundError as error:
            raise PluginError("analysis_failed", "未找到 ffprobe") from error
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PluginError("analysis_failed", f"媒体探测失败：{error}") from error
        if completed.returncode != 0:
            raise PluginError(
                "analysis_failed",
                "ffprobe 未能读取参考媒体",
                details={"stderr": completed.stderr[-2000:]},
            )
        try:
            payload = json.loads(completed.stdout)
            streams = tuple(
                _parse_stream(stream)
                for stream in payload["streams"]
                if stream.get("codec_type") in {"video", "audio"}
            )
            duration_us = round(float(payload["format"]["duration"]) * 1_000_000)
            return MediaProbe(duration_us=duration_us, streams=streams)
        except (KeyError, TypeError, ValueError) as error:
            raise PluginError("analysis_failed", "ffprobe 返回结构无效") from error


def _parse_stream(value: dict[str, Any]) -> MediaStream:
    time_base = str(value["time_base"])
    duration_ts = _optional_int(value.get("duration_ts"))
    duration_us = (
        round(duration_ts * Fraction(time_base) * 1_000_000) if duration_ts is not None else None
    )
    return MediaStream(
        index=int(value["index"]),
        codec_type=value["codec_type"],
        codec_name=str(value["codec_name"]),
        time_base=time_base,
        start_pts=_optional_int(value.get("start_pts")),
        duration_ts=duration_ts,
        duration_us=duration_us,
        width=_optional_int(value.get("width")),
        height=_optional_int(value.get("height")),
        sample_rate=_optional_int(value.get("sample_rate")),
        channels=_optional_int(value.get("channels")),
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
