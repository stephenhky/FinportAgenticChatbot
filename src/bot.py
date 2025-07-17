
import os
import sys

import telebot
from dotenv import load_dotenv
from time import time
from langchain_core.messages import AIMessage

from .agents.graph import FinportAgent
from .agents.aws import get_aws_bedrock_llm


load_dotenv()

# It's a good practice to get the bot token from an environment variable.
telegram_api_key = os.environ.get("API_KEY")
bot = telebot.TeleBot(telegram_api_key, threaded=False)


@bot.message_handler(func=lambda message: True)
def process_user_input_with_agent(message: telebot.types.Message):
    # initialize agent
    llm_id = os.environ.get('BEDROCK_LLM_ID')
    llm = get_aws_bedrock_llm(llm_id)
    agent = FinportAgent(llm)

    # process message
    input_text = message.text
    starttime = time()
    # TODO: make it to reply
    for value in agent.stream_graph_updates(input_text):
        print("======================", file=sys.stderr)
        current_time = time()
        print(f"Time elapsed: {current_time - starttime} sec", file=sys.stderr)
        print(value, file=sys.stderr)
        if 'messages' in value:
            for message in value['messages']:
                print(message, file=sys.stderr)
                print(type(message), file=sys.stderr)
                if isinstance(message, AIMessage):
                    if isinstance(message.content, str):
                        yield message.content
                    elif isinstance(message.content, list):
                        for content in message.content:
                            if content['type'] == 'text':
                                yield "-->" + content['text']
                            elif content['type'] == 'image_url':
                                yield f"Image URL: {content['image_url']}"
