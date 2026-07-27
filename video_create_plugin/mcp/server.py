"""视频创作 MCP Server 入口。"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from video_create_plugin.context import ContextCatalog
from video_create_plugin.mcp.context import register_context_resources


def create_server(content_root: Path | None = None) -> FastMCP:
    server = FastMCP(
        name="video-create",
        instructions="通过分阶段合同完成参考学习与视频创作。",
        log_level="WARNING",
    )
    register_context_resources(server, ContextCatalog(content_root))
    return server


mcp = create_server()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
