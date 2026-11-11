
import os
import sys
import asyncio
import traceback
import urllib.request
from contextlib import aclosing
from typing import Generator, Literal
from dataclasses import dataclass

import telebot
from dotenv import load_dotenv
from time import time
from langchain_core.messages import AIMessage
from langgraph.errors import GraphRecursionError

from agents.graph import FinportAgent
from clients.aws import get_aws_bedrock_llm


load_dotenv()

# It's a good practice to get the bot token from an environment variable.
telegram_api_key = os.environ.get("API_KEY")
bot = telebot.TeleBot(telegram_api_key, threaded=False)

# maximum number of LLM turns (reasoning / tool-calling steps) per user message
nb_max_retries = int(os.environ.get("MAX_RETRIES", "5"))

DEAD_LOOP_MESSAGE = "I am in a dead loop! I am stopping now!"
TOOLS_UNAVAILABLE_MESSAGE = "Sorry, my financial tools are unavailable at the moment. Please try again later."


@dataclass
class OutputMessage:
    type: Literal["text", "image_url"]
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "content": self.content}


def message_output_stream(agent_ai_message: AIMessage) -> Generator[OutputMessage, None, None]:
    if isinstance(agent_ai_message.content, str):
        if agent_ai_message.content.strip():
            yield OutputMessage("text", agent_ai_message.content)
    elif isinstance(agent_ai_message.content, list):
        for content in agent_ai_message.content:
            if not isinstance(content, dict):
                continue
            if content.get('type') == 'text' and content.get('text', '').strip():
                yield OutputMessage("text", f"-->{content['text']}")
            elif content.get('type') == 'image_url':
                yield OutputMessage("image_url", content["image_url"])


_agent_instance: FinportAgent | None = None


async def get_agent() -> FinportAgent:
    """Return a singleton instance of FinportAgent (tools discovered from the MCP server)."""
    global _agent_instance
    if _agent_instance is None:
        llm = get_aws_bedrock_llm()
        _agent_instance = await FinportAgent.create(llm)
    return _agent_instance


def _send_dead_loop_message(message: telebot.types.Message, return_contents: list[dict[str, str]]) -> None:
    print("Quitting the loop and tell the user.", file=sys.stderr)
    bot.send_message(message.chat.id, DEAD_LOOP_MESSAGE)
    return_contents.append(OutputMessage("text", DEAD_LOOP_MESSAGE).to_dict())


async def aprocess_user_input_with_agent(message: telebot.types.Message) -> list[dict[str, str]]:
    return_contents = []

    # retrieve singleton agent (connects to the MCP server on first use)
    try:
        agent = await get_agent()
    except Exception:
        print("Failed to initialize the agent / MCP tools.", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        bot.send_message(message.chat.id, TOOLS_UNAVAILABLE_MESSAGE)
        return_contents.append(OutputMessage("text", TOOLS_UNAVAILABLE_MESSAGE).to_dict())
        return return_contents

    # process message
    input_text = message.text
    nb_retries = 0  # number of LLM turns so far
    wants_more_tools = False
    # backstop: each LLM turn is followed by at most one tool step
    recursion_limit = 2 * nb_max_retries + 2
    try:
        async with aclosing(agent.astream_graph_updates(input_text, recursion_limit=recursion_limit)) as stream:
            async for value in stream:
                print("======================", file=sys.stderr)
                print(value, file=sys.stderr)
                if not value or 'messages' not in value:
                    continue
                for agent_message in value['messages']:
                    print(agent_message, file=sys.stderr)
                    print(type(agent_message), file=sys.stderr)
                    if isinstance(agent_message, AIMessage):
                        nb_retries += 1
                        wants_more_tools = bool(agent_message.tool_calls)
                        for output_content in message_output_stream(agent_message):
                            if output_content.type == "text":
                                bot.reply_to(message, output_content.content)
                            elif output_content.type == "image_url":
                                image_file = urllib.request.urlopen(output_content.content)
                                bot.send_photo(message.chat.id, image_file, "", reply_to_message_id=message.id)
                            return_contents.append(output_content.to_dict())
                print(f"Number of retries: {nb_retries}", file=sys.stderr)
                if nb_retries >= nb_max_retries and wants_more_tools:
                    _send_dead_loop_message(message, return_contents)
                    break
    except GraphRecursionError:
        print(traceback.format_exc(), file=sys.stderr)
        _send_dead_loop_message(message, return_contents)

    return return_contents


@bot.message_handler(func=lambda message: True)
def process_user_input_with_agent(message: telebot.types.Message):
    starttime = time()
    return_contents = asyncio.run(aprocess_user_input_with_agent(message))
    endtime = time()
    print(f"Total time elapsed: {endtime - starttime} sec")
    return return_contents
