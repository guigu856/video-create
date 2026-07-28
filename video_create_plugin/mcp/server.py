"""创建并启动视频创作 stdio MCP Server，集中组装协议层资源注册。"""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from video_create_plugin import __version__
from video_create_plugin.application.reference_runtime import ReferenceRuntime
from video_create_plugin.context import ContextCatalog
from video_create_plugin.mcp.context import register_context_resources
from video_create_plugin.mcp.reference import register_reference_capabilities


def create_server(
    content_root: Path | None = None,
    workspace_root: Path | None = None,
) -> FastMCP:
    server = FastMCP(
        name="video-create",
        instructions="通过分阶段合同完成参考学习与视频创作。",
        log_level="WARNING",
    )
    server._mcp_server.version = __version__
    active_content_root = content_root or _environment_path("VIDEO_CREATE_CONTENT_ROOT")
    active_workspace = workspace_root or _environment_path("VIDEO_CREATE_WORKSPACE") or Path.cwd()
    register_context_resources(server, ContextCatalog(active_content_root))
    register_reference_capabilities(server, ReferenceRuntime(active_workspace))
    return server


def _environment_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


mcp = create_server()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
