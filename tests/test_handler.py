import base64
import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from botocore.exceptions import ClientError
import bot as bot_module
from clients import aws as aws_client
import main


def _sample_telegram_update(text: str = "/start") -> dict:
    return {
        "update_id": 123456789,
        "message": {
            "message_id": 123,
            "from": {
                "id": 123456,
                "is_bot": False,
                "first_name": "Test",
                "last_name": "User",
                "username": "testuser",
            },
            "chat": {
                "id": 123456,
                "first_name": "Test",
                "last_name": "User",
                "username": "testuser",
                "type": "private",
            },
            "date": 1678886400,
            "text": text,
        },
    }


class TestLambdaHandler(unittest.TestCase):

    @patch("main.bot")
    def test_handler_sync_local_success(self, mock_bot):
        """When no Lambda ARN is present (local CLI/tests), handler processes synchronously."""
        event = {"body": json.dumps(_sample_telegram_update())}
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
            response = main.handler(event, {})

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {"approach": "webhook"})
        mock_bot.process_new_messages.assert_called_once()

    @patch("main._get_lambda_client")
    @patch("main.bot")
    def test_handler_async_self_invoke_on_lambda(self, mock_bot, mock_get_lambda_client):
        """Option A: On AWS Lambda, webhook ACKs with 200 immediately and self-invokes asynchronously."""
        mock_lambda = MagicMock()
        mock_get_lambda_client.return_value = mock_lambda

        update = _sample_telegram_update("Analyze AAPL")
        event = {"body": json.dumps(update)}
        context = SimpleNamespace(
            invoked_function_arn="arn:aws:lambda:us-east-1:123456789012:function:finport-telegram-bot"
        )

        response = main.handler(event, context)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {"approach": "webhook", "queued": True})
        mock_bot.process_new_messages.assert_not_called()

        mock_lambda.invoke.assert_called_once()
        call_kwargs = mock_lambda.invoke.call_args.kwargs
        self.assertEqual(
            call_kwargs["FunctionName"],
            "arn:aws:lambda:us-east-1:123456789012:function:finport-telegram-bot",
        )
        self.assertEqual(call_kwargs["InvocationType"], "Event")
        sent_payload = json.loads(call_kwargs["Payload"].decode("utf-8"))
        self.assertTrue(sent_payload[main.ASYNC_WORKER_KEY])
        self.assertEqual(sent_payload["update"], update)

    @patch("main._get_lambda_client")
    @patch("main.bot")
    def test_handler_async_worker_executes_without_reinvoking(self, mock_bot, mock_get_lambda_client):
        """Worker invocation processes the update and never re-invokes Lambda (no infinite loop)."""
        mock_lambda = MagicMock()
        mock_get_lambda_client.return_value = mock_lambda

        worker_event = {
            main.ASYNC_WORKER_KEY: True,
            "update": _sample_telegram_update("Analyze MSFT"),
        }
        context = SimpleNamespace(
            invoked_function_arn="arn:aws:lambda:us-east-1:123456789012:function:finport-telegram-bot",
            get_remaining_time_in_millis=lambda: 120_000,
        )

        response = main.handler(worker_event, context)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {"approach": "webhook"})
        mock_bot.process_new_messages.assert_called_once()
        mock_lambda.invoke.assert_not_called()

    @patch("main._get_lambda_client")
    @patch("main.bot")
    def test_handler_async_self_invoke_fallback_on_iam_error(self, mock_bot, mock_get_lambda_client):
        """If lambda:InvokeFunction fails (e.g. missing IAM permission), falls back to sync safely."""
        mock_lambda = MagicMock()
        mock_lambda.invoke.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException"}}, "Invoke"
        )
        mock_get_lambda_client.return_value = mock_lambda

        event = {"body": json.dumps(_sample_telegram_update())}
        context = SimpleNamespace(
            invoked_function_arn="arn:aws:lambda:us-east-1:123456789012:function:finport-telegram-bot"
        )

        response = main.handler(event, context)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {"approach": "webhook"})
        mock_bot.process_new_messages.assert_called_once()

    @patch("main.bot")
    def test_handler_polling(self, mock_bot):
        """Test the Lambda handler for polling mode."""
        event = {"body": json.dumps({"polling": True})}
        response = main.handler(event, {})

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {"approach": "polling"})
        mock_bot.polling.assert_called_once()

    @patch("main._get_lambda_client")
    @patch("main.bot")
    def test_handler_no_message_returns_200(self, mock_bot, mock_get_lambda_client):
        """Non-message updates (e.g. edited_message) return 200 OK without invoking worker or returning 500."""
        mock_lambda = MagicMock()
        mock_get_lambda_client.return_value = mock_lambda

        event = {
            "body": json.dumps({
                "update_id": 123456789,
                "edited_message": {"message_id": 123, "text": "typo fix"},
            })
        }
        context = SimpleNamespace(
            invoked_function_arn="arn:aws:lambda:us-east-1:123456789012:function:finport-telegram-bot"
        )
        response = main.handler(event, context)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {"approach": "webhook", "ignored": True})
        mock_lambda.invoke.assert_not_called()
        mock_bot.process_new_messages.assert_not_called()

        # Worker path also returns 200 if called directly with a non-message update
        worker_resp = main.bot_webhook({"update_id": 123456789})
        self.assertEqual(worker_resp["statusCode"], 200)

    @patch("main.bot")
    def test_handler_attribute_error(self, mock_bot):
        """AttributeError sends API error message and returns 200 OK."""
        mock_bot.process_new_messages.side_effect = AttributeError("Telegram error")
        event = {"body": json.dumps(_sample_telegram_update())}
        response = main.handler(event, {})

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {"approach": "webhook"})
        mock_bot.send_message.assert_called_once_with(123456, "API error!")

    @patch("main.bot")
    def test_handler_throttling_client_error(self, mock_bot):
        """ThrottlingException sends dead-loop message and returns 200 OK."""
        mock_bot.process_new_messages.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException"}}, "InvokeModel"
        )
        event = {"body": json.dumps(_sample_telegram_update())}
        response = main.handler(event, {})

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {"approach": "webhook", "text": "Loop!"})
        mock_bot.send_message.assert_called_once_with(123456, main.DEAD_LOOP_MESSAGE)

    @patch("main.bot")
    def test_handler_unexpected_exception_returns_200_even_if_send_fails(self, mock_bot):
        """Any unexpected runtime error returns 200 OK (never 500) even if fallback send_message fails."""
        mock_bot.process_new_messages.side_effect = RuntimeError("Bedrock stream broke")
        mock_bot.send_message.side_effect = RuntimeError("Telegram API unreachable")

        worker_event = {main.ASYNC_WORKER_KEY: True, "update": _sample_telegram_update()}
        response = main.handler(worker_event, {})

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {"approach": "webhook", "error": "handled"})
        mock_bot.send_message.assert_called_once_with(123456, main.GENERIC_ERROR_MESSAGE)

    def test_handler_invalid_json_returns_200(self):
        """Malformed JSON bodies are logged and ACKed with 200 OK so Telegram never stalls."""
        event = {"body": "this is not json"}
        response = main.handler(event, {})

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {"approach": "webhook", "error": "invalid_event"})

    @patch("main.bot")
    def test_handler_base64_body_and_secret_token(self, mock_bot):
        """Supports base64-encoded bodies and optional X-Telegram-Bot-Api-Secret-Token verification."""
        encoded = base64.b64encode(json.dumps(_sample_telegram_update()).encode("utf-8")).decode("utf-8")
        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": "my-secret"}, clear=False):
            os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
            unauthorized = main.handler(
                {"body": encoded, "isBase64Encoded": True, "headers": {}},
                {},
            )
            self.assertEqual(unauthorized["statusCode"], 401)

            authorized = main.handler(
                {
                    "body": encoded,
                    "isBase64Encoded": True,
                    "headers": {"X-Telegram-Bot-Api-Secret-Token": "my-secret"},
                },
                {},
            )
            self.assertEqual(authorized["statusCode"], 200)
            mock_bot.process_new_messages.assert_called_once()


class TestTelegramFormattingAndTimeout(unittest.TestCase):

    def test_split_telegram_text(self):
        short = "Hello Finport!"
        self.assertEqual(bot_module._split_telegram_text(short), [short])

        long_text = ("Line of analysis\n" * 400).strip()
        chunks = bot_module._split_telegram_text(long_text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), bot_module.TELEGRAM_MAX_MESSAGE_LENGTH)

    def test_execution_timeout_guard(self):
        async def slow_get_agent():
            import asyncio
            await asyncio.sleep(0.2)

        fake_msg = SimpleNamespace(text="hi", chat=SimpleNamespace(id=99), id=1)
        with patch.object(bot_module, "get_agent", side_effect=slow_get_agent), \
                patch.object(bot_module, "bot") as mock_bot:
            with bot_module.execution_timeout_context(0.02):
                contents = bot_module.process_user_input_with_agent(fake_msg)

        self.assertEqual(
            contents,
            [{"type": "text", "content": bot_module.EXECUTION_TIMEOUT_MESSAGE}],
        )
        mock_bot.send_message.assert_called_once_with(99, bot_module.EXECUTION_TIMEOUT_MESSAGE)


class TestAwsBedrockConfig(unittest.TestCase):

    def setUp(self):
        aws_client._bedrock_llm_instance = None

    def tearDown(self):
        aws_client._bedrock_llm_instance = None

    def test_default_temperature(self):
        with patch.dict(os.environ, {}, clear=True):
            kwargs = aws_client._build_inference_kwargs()
        self.assertEqual(kwargs, {"max_tokens": 4096, "temperature": 0.7})

    def test_custom_temperature(self):
        with patch.dict(os.environ, {"TEMPERATURE": "0.3"}, clear=True):
            kwargs = aws_client._build_inference_kwargs()
        self.assertEqual(kwargs, {"max_tokens": 4096, "temperature": 0.3})

    def test_custom_top_p_omits_default_temperature(self):
        with patch.dict(os.environ, {"TOP_P": "0.8"}, clear=True):
            kwargs = aws_client._build_inference_kwargs()
        self.assertEqual(kwargs, {"max_tokens": 4096, "top_p": 0.8})


if __name__ == "__main__":
    unittest.main()
