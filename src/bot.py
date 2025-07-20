
import os
import sys
import urllib
from typing import Generator, Literal
from dataclasses import dataclass

import telebot
from dotenv import load_dotenv
from time import time
from langchain_core.messages import AIMessage

from agents.graph import FinportAgent
from agents.aws import get_aws_bedrock_llm


load_dotenv()

# It's a good practice to get the bot token from an environment variable.
telegram_api_key = os.environ.get("API_KEY")
bot = telebot.TeleBot(telegram_api_key, threaded=False)

nb_max_retries = int(os.environ.get("MAX_RETRIES", "5"))


@dataclass
class OutputMessage:
    type: Literal["text", "image_url"]
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "content": self.content}


def message_output_stream(agent_ai_message: AIMessage) -> Generator[OutputMessage, None, None]:
    if isinstance(agent_ai_message.content, str):
        yield OutputMessage("text", agent_ai_message.content)
    elif isinstance(agent_ai_message.content, list):
        for content in agent_ai_message.content:
            if content['type'] == 'text':
                yield OutputMessage("text", f"-->{content['text']}")
            elif content['type'] == 'image_url':
                yield OutputMessage("image_url", content["image_url"])


@bot.message_handler(func=lambda message: True)
def process_user_input_with_agent(message: telebot.types.Message):
    # initialize agent
    llm_id = os.environ.get('BEDROCK_LLM_ID')
    llm = get_aws_bedrock_llm(llm_id)
    agent = FinportAgent(llm)

    # process message
    return_contents = []
    input_text = message.text
    starttime = time()
    nb_retries = 0
    for value in agent.stream_graph_updates(input_text):
        print("======================", file=sys.stderr)
        print(value, file=sys.stderr)
        if 'messages' in value:
            for agent_message in value['messages']:
                print(agent_message, file=sys.stderr)
                print(type(agent_message), file=sys.stderr)
                if isinstance(agent_message, AIMessage):
                    for output_content in message_output_stream(agent_message):
                        if output_content.type == "text":
                            bot.reply_to(message, output_content.content)
                        elif output_content.type == "image_url":
                            image_file = urllib.request.urlopen(output_content.content)
                            bot.send_photo(message.chat.id, image_file, "", reply_to_message_id=message.id)
                    return_contents.append(output_content.to_dict())
        nb_retries += 1
        print(f"Number of retries: {nb_retries}", file=sys.stderr)
        if nb_retries > nb_max_retries:
            print("Quitting the loop and tell the user.", file=sys.stderr)
            bot.send_message(message.chat.id, "I am in a dead loop! I am stopping now!")
            return_contents.append(OutputMessage(
                "text", 
                "I am in a dead loop! I am stopping now!").to_dict()
            )
            break

    endtime = time()
    print(f"Total time elapsed: {endtime - starttime} sec")
    return return_contents
