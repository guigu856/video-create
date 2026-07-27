"""把 Context Catalog 映射为可发现、可按稳定 URI 读取的 MCP Resources。"""

from mcp.server.fastmcp import FastMCP

from video_create_plugin.context import CatalogEntry, ContextCatalog


def register_context_resources(server: FastMCP, catalog: ContextCatalog) -> None:
    @server.resource(
        "video-create://catalog",
        name="context_catalog",
        mime_type="application/json",
    )
    def read_catalog() -> str:
        return catalog.document().model_dump_json(indent=2)

    for entry in catalog.document().entries:
        _register_content_resource(server, catalog, entry)


def _register_content_resource(
    server: FastMCP,
    catalog: ContextCatalog,
    entry: CatalogEntry,
) -> None:
    @server.resource(
        entry.uri,
        name=entry.content_id,
        mime_type=entry.mime_type,
    )
    def read_content() -> str:
        return catalog.read(entry.uri)
