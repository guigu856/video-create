"""创建并启动视频创作 stdio MCP Server，集中组装协议层资源注册。"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from video_create_plugin import __version__
from video_create_plugin.context import ContextCatalog
from video_create_plugin.mcp.context import register_context_resources


def create_server(content_root: Path | None = None) -> FastMCP:
    server = FastMCP(
        name="video-create",
        instructions="通过分阶段合同完成参考学习与视频创作。",
        log_level="WARNING",
    )
    server._mcp_server.version = __version__
    register_context_resources(server, ContextCatalog(content_root))
    return server


mcp = create_server()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
