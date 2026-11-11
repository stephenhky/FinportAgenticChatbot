
"""Client for the Finport FastMCP server (deployed separately on AWS Lambda).

The financial tools (stock statistics, stock correlation, crash prediction, ...)
live on the MCP server. This module discovers them over the Streamable HTTP
transport and exposes them as LangChain tools.

Configuration (environment variables, read from `.env` locally or from the
AWS Lambda configuration tab):
    MCP_SERVER_URL          Base URL or full MCP endpoint of the server, e.g.
                            https://<id>.lambda-url.<region>.on.aws/mcp
                            (`/mcp` is appended when only the base URL is given).
    MCP_SERVER_AUTH_TOKEN   Optional. Sent as `Authorization: Bearer <token>`.
    MCP_TIMEOUT_SECONDS     Optional. HTTP timeout for MCP calls (default: 50).
"""

import os
from datetime import timedelta
from urllib.parse import urlparse

from dotenv import load_dotenv
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()


MCP_SERVER_NAME = "finport"
DEFAULT_MCP_PATH = "/mcp"
DEFAULT_TIMEOUT_SECONDS = 50.0

_mcp_client_instance: MultiServerMCPClient | None = None
_mcp_tools_cache: list[BaseTool] | None = None


def normalize_mcp_url(url: str) -> str:
    """Append the default FastMCP endpoint path if only a base URL is given."""
    url = url.strip()
    parsed = urlparse(url)
    if parsed.path in ("", "/"):
        return url.rstrip("/") + DEFAULT_MCP_PATH
    return url


def build_mcp_connection() -> dict:
    """Build the Streamable HTTP connection config from environment variables."""
    url = os.environ.get("MCP_SERVER_URL")
    if not url:
        raise RuntimeError("MCP_SERVER_URL is not set; cannot reach the Finport MCP server.")

    timeout_seconds = float(os.environ.get("MCP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    connection = {
        "transport": "streamable_http",
        "url": normalize_mcp_url(url),
        "timeout": timedelta(seconds=timeout_seconds),
        "sse_read_timeout": timedelta(seconds=timeout_seconds),
    }

    auth_token = os.environ.get("MCP_SERVER_AUTH_TOKEN")
    if auth_token:
        connection["headers"] = {"Authorization": f"Bearer {auth_token}"}

    return connection


def get_mcp_client() -> MultiServerMCPClient:
    """Return a singleton MCP client connected to the Finport MCP server."""
    global _mcp_client_instance
    if _mcp_client_instance is None:
        _mcp_client_instance = MultiServerMCPClient({MCP_SERVER_NAME: build_mcp_connection()})
    return _mcp_client_instance


async def get_mcp_tools() -> list[BaseTool]:
    """Discover the MCP server's tools and return them as LangChain tools (cached).

    Each returned tool opens its own short-lived MCP session per call, so the
    tools can safely be reused across event loops (e.g. Lambda invocations).
    """
    global _mcp_tools_cache
    if _mcp_tools_cache is None:
        tools = await get_mcp_client().get_tools()
        for mcp_tool in tools:
            # Tool errors reported by the server (e.g. no market data for a symbol)
            # are returned to the LLM instead of crashing the graph.
            mcp_tool.handle_tool_error = True
        _mcp_tools_cache = tools
    return _mcp_tools_cache
