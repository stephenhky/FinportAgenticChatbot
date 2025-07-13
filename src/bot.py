import os
import telegram

# It's a good practice to get the bot token from an environment variable.
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telegram.Bot(token=BOT_TOKEN)

def process_update(update_data):
    """
    Processes a single update from Telegram.
    """
    update = telegram.Update.de_json(update_data, bot)

    # You can add your command handlers and message processors here.
    # For example, you can check `update.message.text` for commands.
    if update.message and update.message.text:
        if update.message.text.startswith('/start'):
            return start_command(update)
        else:
            return echo_message(update)
            
    return {"message": "Update processed"}

def start_command(update):
    """
    Handles the /start command.
    """
    chat_id = update.message.chat_id
    bot.send_message(chat_id=chat_id, text="Hello! I am your bot.")
    return {"message": "Start command processed"}

def echo_message(update):
    """
    Echoes back any message it receives.
    """
    chat_id = update.message.chat_id
    text = update.message.text
    bot.send_message(chat_id=chat_id, text=text)
    return {"message": "Message echoed"}