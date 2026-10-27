
import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain.tools import tool


def get_joke_tool(llm: BaseChatModel):
    """Factory that returns a joke tool bound to the given LLM."""

    @tool
    def give_a_joke() -> str:
        """Give a joke."""
        response = llm.invoke("Tell me a joke.")
        return json.dumps({"joke": response.content})

    return give_a_joke
