"""
Local CLI runner for the Finport Telegram bot.

Simulates Telegram webhook calls to the AWS Lambda handler (`src/main.py::handler`)
so you can chat with the bot from your terminal. Outbound Telegram API calls
(reply_to / send_message / send_photo) are intercepted and printed instead of
being sent to Telegram, so no real Telegram token or network access to Telegram
is required. AWS Bedrock and the tool APIs are still called for real.

Usage:
    python cli.py                  # interactive chat
    python cli.py "Tell me a joke" # send a single message and exit
    python cli.py -v               # also show handler / agent debug logs
"""

import argparse
import contextlib
import io
import json
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
sys.path.insert(0, SRC_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(SRC_DIR, ".env"))
# telebot validates the token format at construction time; a dummy token is
# enough because outbound Telegram calls are intercepted below.
if not os.environ.get("API_KEY"):
    os.environ["API_KEY"] = "000000000:LOCAL_CLI_DUMMY_TOKEN"

import main  # noqa: E402
from bot import bot  # noqa: E402

# Bot output always goes to the real terminal, even when debug logs are hidden.
_out = sys.__stdout__

CHAT_ID = 1
USER = {"id": 1, "is_bot": False, "first_name": "Local", "username": "local_cli_user"}


def _print_bot(text: str) -> None:
    print(f"\n🤖 Bot: {text}\n", file=_out, flush=True)


def _fake_reply_to(message, text, **kwargs):
    _print_bot(text)


def _fake_send_message(chat_id, text, **kwargs):
    _print_bot(text)


def _fake_send_photo(chat_id, photo, caption=None, **kwargs):
    source = getattr(photo, "url", None) or getattr(photo, "name", None) or repr(photo)
    caption_part = f" — {caption}" if caption else ""
    print(f"\n🖼️  Bot [photo]: {source}{caption_part}\n", file=_out, flush=True)


bot.reply_to = _fake_reply_to
bot.send_message = _fake_send_message
bot.send_photo = _fake_send_photo


def build_event(text: str, update_id: int) -> dict:
    """Build an API Gateway-style event wrapping a Telegram webhook update."""
    update = {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": USER,
            "chat": {"id": CHAT_ID, "type": "private", "first_name": USER["first_name"]},
            "date": int(time.time()),
            "text": text,
        },
    }
    return {"body": json.dumps(update)}


def invoke(text: str, update_id: int, verbose: bool) -> dict:
    event = build_event(text, update_id)
    start = time.time()
    if verbose:
        response = main.handler(event, {})
    else:
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            response = main.handler(event, {})
    elapsed = time.time() - start
    print(f"[Lambda response {elapsed:.1f}s] {response}", file=_out, flush=True)
    return response


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="Chat with the Finport bot locally via the Lambda handler.")
    parser.add_argument("message", nargs="*", help="Send a single message and exit.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show handler and agent debug output.")
    args = parser.parse_args()

    if args.message:
        invoke(" ".join(args.message), 1, args.verbose)
        return

    print("Finport bot local CLI — type a message, or 'exit' to quit.", file=_out)
    update_id = 1
    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=_out)
            break
        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            break
        invoke(text, update_id, args.verbose)
        update_id += 1


if __name__ == "__main__":
    main_cli()
