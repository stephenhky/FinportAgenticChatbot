
import os

import telebot


# It's a good practice to get the bot token from an environment variable.
telegram_api_key = os.environ.get("API_KEY")
bot = telebot.TeleBot(telegram_api_key, threaded=False)


@bot.message_handler(func=lambda message: True)
def process_user_input_with_agent(message):
    pass
