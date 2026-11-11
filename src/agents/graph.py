
from datetime import date
from typing import Any, AsyncGenerator, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode, create_react_agent

from clients.mcp_client import get_mcp_tools
from .tools import get_joke_tool


SYSTEM_PROMPT = """
You are Finport, a financial portfolio assistant chatting with a user on Telegram.
Use the tools available to you to answer the user's request, and return the results back to the user.

Guidelines:
- Use Yahoo Finance ticker symbols (e.g. AAPL, MSFT, ^GSPC for the S&P 500).
- Dates passed to tools must be in YYYY-mm-dd format.
- Return/risk statistics and correlations require a multi-day date range: startdate must be strictly
  earlier than enddate, spanning at least several trading days. If the user asks for a single date or
  does not specify a full range, either explain that a date range is required or use an appropriate
  multi-day window around the requested date, and tell the user which window you used.
- For crash prediction, if the symbol is not given, use the S&P 500 (^GSPC); if the date range is not
  given, leave it out so the last one year is used.
- If the user asks for a joke, get one from the joke tool and return it.
- If a tool returns an error, briefly explain the problem to the user.
- Be concise and present numbers clearly.
"""


def _build_prompt(system_prompt: str):
    """Return a prompt callable that prepends the system prompt with today's date."""
    def _prompt(state: dict) -> list:
        today = date.today().isoformat()
        content = f"{system_prompt.strip()}\nToday's date is {today}."
        return [SystemMessage(content=content)] + state["messages"]

    return _prompt


class FinportAgent:
    """ReAct agent combining the local tools with the tools served by the Finport MCP server."""

    def __init__(self, llm: BaseChatModel, mcp_tools: Sequence[BaseTool]):
        self.tools: list[BaseTool] = [get_joke_tool(llm), *mcp_tools]
        self.graph = create_react_agent(
            llm,
            # handle_tool_errors=True: any tool failure (including MCP connection
            # errors) is returned to the LLM as a ToolMessage instead of raising.
            tools=ToolNode(self.tools, handle_tool_errors=True),
            prompt=_build_prompt(SYSTEM_PROMPT),
        )

    @classmethod
    async def create(cls, llm: BaseChatModel) -> "FinportAgent":
        """Discover the MCP server's tools and build the agent."""
        mcp_tools = await get_mcp_tools()
        return cls(llm, mcp_tools)

    async def astream_graph_updates(
            self,
            user_input: str,
            recursion_limit: int | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream the state updates (new messages) produced by each graph step."""
        config = {"recursion_limit": recursion_limit} if recursion_limit is not None else None
        async for event in self.graph.astream(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config,
                stream_mode="updates",
        ):
            for value in event.values():
                yield value
