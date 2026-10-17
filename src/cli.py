"""
Local CLI runner for the Finport Telegram bot.

Simulates Telegram webhook calls to the AWS Lambda handler (`main.handler`)
so you can chat with the bot from your terminal. Outbound Telegram API calls
(reply_to / send_message / send_photo) are intercepted and printed instead of
being sent to Telegram, so no real Telegram token or network access to Telegram
is required. AWS Bedrock and the tool APIs are still called for real.

Usage (after `pip install -e .`):
    finport-chat                    # interactive chat
    finport-chat "Tell me a joke"   # send a single message and exit
    finport-chat -v                 # also show handler / agent debug logs

Without installing:
    python src/cli.py [...]
"""

import argparse
import contextlib
import io
import json
import os
import sys
import time
from types import ModuleType

# The Lambda modules use top-level imports (`from bot import bot`,
# `from agents.graph import ...`) because the Lambda image copies `src/` to the
# task root. Put this directory on sys.path so those imports resolve whether
# this file is run directly or via the installed `finport-chat` entry point.
SRC_DIR = os.path.dirname(os.path.abspath(__file__))

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


def _load_lambda_handler(env_file: str | None) -> ModuleType:
    """Load env vars, import the Lambda `main` module, and stub Telegram output."""
    if SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)

    from dotenv import find_dotenv, load_dotenv

    if env_file:
        load_dotenv(env_file)
    else:
        # Check ./.env, ./src/.env (when run from repo root after non-editable install),
        # and SRC_DIR/.env (when run via editable install or `python src/cli.py`).
        load_dotenv(find_dotenv(usecwd=True))
        load_dotenv(os.path.join(os.getcwd(), "src", ".env"))
        load_dotenv(os.path.join(SRC_DIR, ".env"))

    # telebot validates the token format at construction time; a dummy token is
    # enough because outbound Telegram calls are intercepted below.
    if not os.environ.get("API_KEY"):
        os.environ["API_KEY"] = "000000000:LOCAL_CLI_DUMMY_TOKEN"

    import main as lambda_main
    from bot import bot

    bot.reply_to = _fake_reply_to
    bot.send_message = _fake_send_message
    bot.send_photo = _fake_send_photo
    return lambda_main


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


def invoke(lambda_main: ModuleType, text: str, update_id: int, verbose: bool) -> dict:
    event = build_event(text, update_id)
    start = time.time()
    if verbose:
        response = lambda_main.handler(event, {})
    else:
        sink_out = io.StringIO()
        sink_err = io.StringIO()
        with contextlib.redirect_stdout(sink_out), contextlib.redirect_stderr(sink_err):
            response = lambda_main.handler(event, {})
        if response.get("statusCode") != 200 or "Traceback" in sink_err.getvalue():
            captured = (sink_out.getvalue() + "\n" + sink_err.getvalue()).strip()
            if captured:
                print(captured, file=_out, flush=True)
    elapsed = time.time() - start
    print(f"[Lambda response {elapsed:.1f}s] {response}", file=_out, flush=True)
    return response


def main_cli() -> None:
    parser = argparse.ArgumentParser(
        prog="finport-chat",
        description="Chat with the Finport bot locally through the AWS Lambda handler.",
    )
    parser.add_argument("message", nargs="*", help="Send a single message and exit.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show handler and agent debug output.")
    parser.add_argument("--env-file", help="Path to a .env file (default: ./.env, then src/.env).")
    args = parser.parse_args()

    lambda_main = _load_lambda_handler(args.env_file)

    if args.message:
        invoke(lambda_main, " ".join(args.message), 1, args.verbose)
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
        invoke(lambda_main, text, update_id, args.verbose)
        update_id += 1


if __name__ == "__main__":
    main_cli()
