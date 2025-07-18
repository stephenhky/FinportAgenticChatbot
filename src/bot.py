
import os
import sys
import urllib

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
            for agent_message in value['messages']:
                print(agent_message, file=sys.stderr)
                print(type(agent_message), file=sys.stderr)
                if isinstance(agent_message, AIMessage):
                    if isinstance(agent_message.content, str):
                        bot.reply_to(message, agent_message.content)
                    elif isinstance(agent_message.content, list):
                        for content in agent_message.content:
                            if content['type'] == 'text':
                                bot.reply_to(
                                    message,
                                    "-->" + content['text']
                                )
                            elif content['type'] == 'image_url':
                                image_file = urllib.request.urlopen(content['image_url'])
                                bot.send_photo(
                                    message.chat.id,
                                    image_file,
                                    "",
                                    reply_to_message_id=message.id
                                )
