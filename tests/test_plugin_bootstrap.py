"""验证跨宿主 Plugin 身份一致、MCP Server 身份稳定并可通过 stdio 初始化。"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from video_create_plugin import __version__
from video_create_plugin.mcp.server import create_server

ROOT = Path(__file__).parents[1]


def test_host_manifests_share_plugin_identity() -> None:
    codex = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    claude = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    mcp_config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))

    assert codex["name"] == claude["name"] == "video-create"
    assert codex["version"] == claude["version"] == __version__
    assert codex["mcpServers"] == claude["mcpServers"] == "./.mcp.json"
    assert codex["skills"] == claude["skills"] == "./skills/"
    assert mcp_config["mcpServers"]["video-create"]["args"] == [
        "run",
        "video-create-mcp",
    ]


def test_server_has_stable_identity() -> None:
    assert create_server().name == "video-create"


def test_stdio_server_initializes() -> None:
    async def initialize() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "video_create_plugin.mcp.server"],
            cwd=ROOT,
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                result = await session.initialize()
                assert result.serverInfo.name == "video-create"
                assert result.serverInfo.version

    asyncio.run(initialize())
