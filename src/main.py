import base64
import hmac
import json
import os
import sys
import traceback

import boto3
from botocore.exceptions import ClientError

ASYNC_WORKER_KEY = "_finport_async_worker"
DEAD_LOOP_MESSAGE = "I am in a dead loop! I am stopping now!"
GENERIC_ERROR_MESSAGE = "Sorry, something went wrong while processing your message. Please try again later."

# Lazy-loaded module singletons so webhook ACKs stay fast on cold starts,
# while remaining patchable in unit tests (e.g. `@patch("src.main.bot")`).
bot = None
_lambda_client = None


def _get_bot():
    global bot
    if bot is not None:
        return bot
    from bot import bot as _bot
    bot = _bot
    return bot


def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client(
            "lambda",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
    return _lambda_client


def _safe_send_message(active_bot, chat_id: int, text: str) -> None:
    """Send a fallback Telegram message without ever raising back into the handler."""
    try:
        active_bot.send_message(chat_id, text)
    except Exception:
        print("[ERROR] Failed to send fallback error message to Telegram.", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)


def _verify_webhook_secret(event: dict) -> bool:
    """Verify X-Telegram-Bot-Api-Secret-Token when TELEGRAM_WEBHOOK_SECRET is configured."""
    expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if not expected_secret:
        return True
    headers = (event.get("headers") if isinstance(event, dict) else None) or {}
    provided_secret = ""
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == "x-telegram-bot-api-secret-token":
            provided_secret = value or ""
            break
    return hmac.compare_digest(provided_secret, expected_secret)


def _parse_webhook_body(event: dict) -> dict:
    """Extract and parse the JSON body from a Lambda Function URL or API Gateway event."""
    if not isinstance(event, dict) or "body" not in event:
        raise ValueError("Webhook event does not contain a 'body' field.")
    raw_body = event["body"]
    if isinstance(raw_body, dict):
        return raw_body
    if raw_body is None:
        raise ValueError("Webhook event 'body' is None.")
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")
    parsed = json.loads(raw_body)
    if not isinstance(parsed, dict):
        raise ValueError("Webhook JSON payload must be an object.")
    return parsed


def _get_self_function_target(context) -> str | None:
    """Return the Lambda ARN/name for async self-invocation, or None when running locally."""
    flag = os.environ.get("ASYNC_SELF_INVOKE", "true").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return None
    arn = getattr(context, "invoked_function_arn", None)
    if not arn and isinstance(context, dict):
        arn = context.get("invoked_function_arn")
    return arn or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or None


def _invoke_worker_async(function_target: str, update_payload: dict) -> None:
    """Asynchronously invoke this same Lambda function as a background worker."""
    payload = json.dumps({
        ASYNC_WORKER_KEY: True,
        "update": update_payload,
    }).encode("utf-8")
    _get_lambda_client().invoke(
        FunctionName=function_target,
        InvocationType="Event",
        Payload=payload,
    )


def _remaining_timeout_seconds(context, safety_margin_seconds: float = 5.0) -> float | None:
    """Compute an in-Python execution budget slightly shorter than Lambda's hard timeout."""
    get_remaining = getattr(context, "get_remaining_time_in_millis", None)
    if not callable(get_remaining):
        return None
    try:
        remaining_ms = get_remaining()
        if remaining_ms is None:
            return None
        return max(1.0, (remaining_ms / 1000.0) - safety_margin_seconds)
    except Exception:
        return None


def bot_polling():
    active_bot = _get_bot()
    active_bot.polling()
    return {
        "statusCode": 200,
        "body": json.dumps({"approach": "polling"}),
    }


def bot_webhook(message: dict, context=None):
    import telebot
    from bot import execution_timeout_context

    update = telebot.types.Update.de_json(message)
    print(update)
    if update is None or update.message is None:
        print("Ignoring non-message Telegram update.")
        return {
            "statusCode": 200,
            "body": json.dumps({"approach": "webhook", "ignored": True}),
        }

    tg_message = update.message
    chat_id = tg_message.chat.id
    active_bot = _get_bot()
    timeout_seconds = _remaining_timeout_seconds(context)

    try:
        with execution_timeout_context(timeout_seconds):
            active_bot.process_new_messages([tg_message])
        print("Processed.")
        return {
            "statusCode": 200,
            "body": json.dumps({"approach": "webhook"}),
        }
    except AttributeError:
        print("[ERROR] Telegram AttributeError during message processing.", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        _safe_send_message(active_bot, chat_id, "API error!")
        return {
            "statusCode": 200,
            "body": json.dumps({"approach": "webhook"}),
        }
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "ThrottlingException":
            print("[ERROR] Bedrock ThrottlingException / infinite loop.", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            _safe_send_message(active_bot, chat_id, DEAD_LOOP_MESSAGE)
            return {
                "statusCode": 200,
                "body": json.dumps({"approach": "webhook", "text": "Loop!"}),
            }
        print(f"[ERROR] AWS ClientError ({error_code}).", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        _safe_send_message(active_bot, chat_id, GENERIC_ERROR_MESSAGE)
        return {
            "statusCode": 200,
            "body": json.dumps({"approach": "webhook", "error": "client_error"}),
        }
    except Exception:
        print("[ERROR] Unhandled exception during Telegram message processing.", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        _safe_send_message(active_bot, chat_id, GENERIC_ERROR_MESSAGE)
        return {
            "statusCode": 200,
            "body": json.dumps({"approach": "webhook", "error": "handled"}),
        }


def handler(event, context):
    """AWS Lambda entry point supporting both Telegram HTTP webhooks and async worker events.

    Option A (Self-Invoke):
      1. Webhook call (`event` has `"body"`): validates the update, fires an async
         `InvocationType="Event"` call to this same Lambda function, and immediately
         returns `200 OK` to Telegram so Telegram never backs off or replays old updates.
      2. Worker call (`event` has `"_finport_async_worker": True`): runs the LangGraph +
         MCP agent and sends the reply back to Telegram.
      3. Local CLI / tests (no Lambda ARN): runs `bot_webhook` synchronously in-process.
    """
    print(event)
    print(type(event))

    # 1. Background worker invocation (never self-invokes again).
    if isinstance(event, dict) and event.get(ASYNC_WORKER_KEY):
        update_payload = event.get("update") or {}
        return bot_webhook(update_payload, context=context)

    # 2. Optional Telegram secret-token verification on incoming HTTP webhooks.
    if not _verify_webhook_secret(event):
        print("[WARN] Rejected webhook request with invalid secret token.", file=sys.stderr)
        return {
            "statusCode": 401,
            "body": json.dumps({"message": "Unauthorized"}),
        }

    # 3. Incoming Telegram HTTP webhook (or polling trigger).
    try:
        message = _parse_webhook_body(event)
        if message.get("polling", False):
            return bot_polling()

        # Fast-ignore non-message updates (e.g. edited_message, my_chat_member)
        # without spawning a background worker Lambda.
        if message.get("message") is None:
            print("Ignoring non-message Telegram update at webhook gateway.")
            return {
                "statusCode": 200,
                "body": json.dumps({"approach": "webhook", "ignored": True}),
            }

        target_fn = _get_self_function_target(context)
        if target_fn:
            try:
                _invoke_worker_async(target_fn, message)
                return {
                    "statusCode": 200,
                    "body": json.dumps({"approach": "webhook", "queued": True}),
                }
            except Exception:
                # Graceful fallback (e.g. if lambda:InvokeFunction IAM permission is missing):
                # process synchronously rather than dropping the user's message.
                print(
                    "[WARN] Async self-invoke failed; falling back to synchronous execution.",
                    file=sys.stderr,
                )
                print(traceback.format_exc(), file=sys.stderr)
                return bot_webhook(message, context=context)

        return bot_webhook(message, context=context)
    except Exception as e:
        # Always return 200 OK to Telegram so malformed/unexpected updates are acknowledged
        # and cannot stall the webhook queue.
        print(f"[ERROR] Failed to parse or dispatch webhook event: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return {
            "statusCode": 200,
            "body": json.dumps({"approach": "webhook", "error": "invalid_event"}),
        }


if __name__ == "__main__":
    _ = bot_polling()
