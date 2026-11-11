"""Tests for the MCP integration.

A local stub MCP server (Streamable HTTP, same tool names and signatures as the
FinportFastMCP server) is started in a background thread, so these tests need
neither AWS nor the deployed MCP server.
"""

import asyncio
import json
import os
import socket
import sys
import threading
import time
import unittest
from datetime import timedelta
from typing import Any, Optional
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import uvicorn
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from mcp.server.fastmcp import FastMCP

import bot as bot_module
from agents.graph import FinportAgent
from clients import mcp_client


# ---------------------------------------------------------------------------
# Stub MCP server
# ---------------------------------------------------------------------------

def _build_stub_server() -> FastMCP:
    stub = FastMCP(name="Stub Financial Calculator MCP Server", stateless_http=True, json_response=True)

    @stub.tool()
    def estimate_symbol_info(symbol: str, startdate: str, enddate: str, index: str = '^GSPC') -> dict:
        """Estimate information about the given symbol within the start and end dates."""
        return {"symbol": symbol, "r": 0.1, "volatility": 0.2, "downside_risk": 0.15, "upside_risk": 0.12,
                "beta": 1.1, "data_startdate": startdate, "data_enddate": enddate, "nbrecords": 250}

    @stub.tool()
    def estimate_symbols_correlation(symbol1: str, symbol2: str, startdate: str, enddate: str) -> dict:
        """Estimate the correlation between two given symbols within the start and end dates."""
        return {"symbol1": symbol1, "symbol2": symbol2, "correlation": 0.42}

    @stub.tool()
    def predict_crash(symbol: str = "^GSPC", startdate: Optional[str] = None, enddate: Optional[str] = None) -> dict:
        """Predict the crash date of the given symbol and within the start and end dates."""
        if symbol == "BAD":
            raise ValueError("No market data returned for symbol 'BAD'.")
        return {"symbol": symbol, "estimated_crash_date": "2027-01-01"}

    return stub


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _StubServer:
    def __init__(self):
        self.port = _free_port()
        config = uvicorn.Config(_build_stub_server().streamable_http_app(), host="127.0.0.1",
                                port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started:
            if time.time() > deadline:
                raise RuntimeError("Stub MCP server did not start.")
            time.sleep(0.05)

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Scripted fake chat model
# ---------------------------------------------------------------------------

class ScriptedChatModel(BaseChatModel):
    """Returns pre-defined AIMessages in order; records the messages it receives."""
    responses: list[AIMessage]
    received: list[list[Any]] = []
    index: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.received.append(list(messages))
        response = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


def _tool_call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


def _fake_message(text: str) -> MagicMock:
    message = MagicMock()
    message.text = text
    message.chat.id = 42
    message.id = 7
    return message


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMcpConfig(unittest.TestCase):

    def test_normalize_mcp_url(self):
        self.assertEqual(mcp_client.normalize_mcp_url("https://x.on.aws"), "https://x.on.aws/mcp")
        self.assertEqual(mcp_client.normalize_mcp_url("https://x.on.aws/"), "https://x.on.aws/mcp")
        self.assertEqual(mcp_client.normalize_mcp_url("https://x.on.aws/mcp/"), "https://x.on.aws/mcp/")
        self.assertEqual(mcp_client.normalize_mcp_url("https://x.on.aws/custom"), "https://x.on.aws/custom")

    def test_build_connection(self):
        env = {"MCP_SERVER_URL": "https://x.on.aws", "MCP_SERVER_AUTH_TOKEN": "secret", "MCP_TIMEOUT_SECONDS": "20"}
        with patch.dict(os.environ, env):
            connection = mcp_client.build_mcp_connection()
        self.assertEqual(connection["transport"], "streamable_http")
        self.assertEqual(connection["url"], "https://x.on.aws/mcp")
        self.assertEqual(connection["headers"], {"Authorization": "Bearer secret"})
        self.assertEqual(connection["timeout"], timedelta(seconds=20))

    def test_missing_url(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                mcp_client.build_mcp_connection()


class TestMcpIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = _StubServer()
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        self.env = patch.dict(os.environ, {"MCP_SERVER_URL": self.server.base_url})
        self.env.start()
        mcp_client._mcp_client_instance = None
        mcp_client._mcp_tools_cache = None
        bot_module._agent_instance = None

    def tearDown(self):
        self.env.stop()
        mcp_client._mcp_client_instance = None
        mcp_client._mcp_tools_cache = None
        bot_module._agent_instance = None

    def test_tool_discovery_and_call(self):
        tools = asyncio.run(mcp_client.get_mcp_tools())
        names = {t.name for t in tools}
        self.assertEqual(names, {"estimate_symbol_info", "estimate_symbols_correlation", "predict_crash"})
        # cached, and callable from a fresh event loop
        self.assertIs(asyncio.run(mcp_client.get_mcp_tools()), tools)
        corr = next(t for t in tools if t.name == "estimate_symbols_correlation")
        result = asyncio.run(corr.ainvoke(
            {"symbol1": "AAPL", "symbol2": "MSFT", "startdate": "2025-01-01", "enddate": "2025-06-30"}))
        self.assertIn("0.42", str(result))

    def test_agent_uses_mcp_tools(self):
        llm = ScriptedChatModel(responses=[
            _tool_call("estimate_symbol_info", {"symbol": "AAPL", "startdate": "2025-01-01",
                                                "enddate": "2025-06-30"}, "call_1"),
            AIMessage(content="AAPL beta is 1.1."),
        ])
        agent = asyncio.run(FinportAgent.create(llm))
        self.assertIn("give_a_joke", {t.name for t in agent.tools})

        async def collect():
            return [v async for v in agent.astream_graph_updates("AAPL stats for H1 2025")]

        updates = asyncio.run(collect())
        messages = [m for u in updates for m in u["messages"]]
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        self.assertEqual(len(tool_messages), 1)
        # older adapters return a string, newer ones a list of content blocks
        content = tool_messages[0].content
        if isinstance(content, list):
            content = "".join(block["text"] for block in content if block.get("type") == "text")
        self.assertEqual(json.loads(content)["beta"], 1.1)
        self.assertEqual(messages[-1].content, "AAPL beta is 1.1.")
        # system prompt includes today's date
        self.assertIn("Today's date is", llm.received[0][0].content)

    def test_mcp_tool_error_returned_to_llm(self):
        llm = ScriptedChatModel(responses=[
            _tool_call("predict_crash", {"symbol": "BAD"}, "call_1"),
            AIMessage(content="Sorry, no data for BAD."),
        ])
        with patch.object(bot_module, "get_aws_bedrock_llm", return_value=llm), \
                patch.object(bot_module, "bot") as mock_bot:
            contents = bot_module.process_user_input_with_agent(_fake_message("When will BAD crash?"))
        self.assertEqual(contents, [{"type": "text", "content": "Sorry, no data for BAD."}])
        mock_bot.reply_to.assert_called_once()
        tool_message = llm.received[1][-1]
        self.assertIsInstance(tool_message, ToolMessage)
        self.assertIn("No market data", str(tool_message.content))

    def test_bot_dead_loop_guard(self):
        llm = ScriptedChatModel(responses=[_tool_call("predict_crash", {}, "call_x")])
        with patch.object(bot_module, "get_aws_bedrock_llm", return_value=llm), \
                patch.object(bot_module, "nb_max_retries", 2), \
                patch.object(bot_module, "bot") as mock_bot:
            contents = bot_module.process_user_input_with_agent(_fake_message("loop forever"))
        self.assertEqual(contents, [{"type": "text", "content": bot_module.DEAD_LOOP_MESSAGE}])
        mock_bot.send_message.assert_called_once_with(42, bot_module.DEAD_LOOP_MESSAGE)
        self.assertEqual(llm.index, 2)

    def test_bot_mcp_unavailable(self):
        mcp_client._mcp_client_instance = None
        with patch.dict(os.environ, {"MCP_SERVER_URL": f"http://127.0.0.1:{_free_port()}/mcp",
                                     "MCP_TIMEOUT_SECONDS": "2"}), \
                patch.object(bot_module, "get_aws_bedrock_llm", return_value=ScriptedChatModel(responses=[])), \
                patch.object(bot_module, "bot") as mock_bot:
            contents = bot_module.process_user_input_with_agent(_fake_message("hi"))
        self.assertEqual(contents, [{"type": "text", "content": bot_module.TOOLS_UNAVAILABLE_MESSAGE}])
        mock_bot.send_message.assert_called_once_with(42, bot_module.TOOLS_UNAVAILABLE_MESSAGE)
        self.assertIsNone(bot_module._agent_instance)


if __name__ == '__main__':
    unittest.main()
