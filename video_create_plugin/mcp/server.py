"""视频创作 MCP Server 入口。"""

from mcp.server.fastmcp import FastMCP


def create_server() -> FastMCP:
    return FastMCP(
        name="video-create",
        instructions="通过分阶段合同完成参考学习与视频创作。",
        log_level="WARNING",
    )


mcp = create_server()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
