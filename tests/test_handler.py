import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from botocore.exceptions import ClientError
from clients import aws as aws_client
from src import main


class TestLambdaHandler(unittest.TestCase):

    @patch('src.main.bot')
    def test_handler_success(self, mock_bot):
        """
        Test the Lambda handler for a successful invocation via webhook.
        """
        # Create a sample Telegram update event
        event = {
            "body": json.dumps({
                "update_id": 123456789,
                "message": {
                    "message_id": 123,
                    "from": {"id": 123456, "is_bot": False, "first_name": "Test", "last_name": "User", "username": "testuser"},
                    "chat": {"id": 123456, "first_name": "Test", "last_name": "User", "username": "testuser", "type": "private"},
                    "date": 1678886400,
                    "text": "/start"
                }
            })
        }
        
        context = {}
        response = main.handler(event, context)
        
        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(json.loads(response['body']), {"approach": "webhook"})
        mock_bot.process_new_messages.assert_called_once()

    @patch('src.main.bot')
    def test_handler_polling(self, mock_bot):
        """
        Test the Lambda handler for polling mode.
        """
        event = {
            "body": json.dumps({"polling": True})
        }
        context = {}
        response = main.handler(event, context)

        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(json.loads(response['body']), {"approach": "polling"})
        mock_bot.polling.assert_called_once()

    @patch('src.main.bot')
    def test_handler_no_message(self, mock_bot):
        """
        Test handler when update has no message field.
        """
        event = {
            "body": json.dumps({
                "update_id": 123456789
            })
        }
        context = {}
        response = main.handler(event, context)

        self.assertEqual(response['statusCode'], 500)
        self.assertEqual(json.loads(response['body']), {"message": "Not handled exception."})

    @patch('src.main.bot')
    def test_handler_attribute_error(self, mock_bot):
        """
        Test handler when processing messages raises an AttributeError.
        """
        mock_bot.process_new_messages.side_effect = AttributeError("Telegram error")
        event = {
            "body": json.dumps({
                "update_id": 123456789,
                "message": {
                    "message_id": 123,
                    "chat": {"id": 123456, "type": "private"},
                    "date": 1678886400,
                    "text": "/start"
                }
            })
        }
        context = {}
        response = main.handler(event, context)

        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(json.loads(response['body']), {"approach": "webhook"})
        mock_bot.send_message.assert_called_once_with(123456, "API error!")

    @patch('src.main.bot')
    def test_handler_throttling_client_error(self, mock_bot):
        """
        Test handler when processing messages encounters a ThrottlingException ClientError.
        """
        mock_bot.process_new_messages.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException"}}, "InvokeModel"
        )
        event = {
            "body": json.dumps({
                "update_id": 123456789,
                "message": {
                    "message_id": 123,
                    "chat": {"id": 123456, "type": "private"},
                    "date": 1678886400,
                    "text": "/start"
                }
            })
        }
        context = {}
        response = main.handler(event, context)

        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(json.loads(response['body']), {"approach": "webhook", "text": "Loop!"})
        mock_bot.send_message.assert_called_once_with(123456, "I am in a dead loop! I am stopping now!")

    def test_handler_error(self):
        """
        Test the Lambda handler for an error scenario (e.g., invalid JSON).
        """
        event = {
            "body": "this is not json"
        }
        
        context = {}
        response = main.handler(event, context)
        
        self.assertEqual(response['statusCode'], 500)
        self.assertEqual(json.loads(response['body']), {"message": "Internal Server Error"})


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


if __name__ == '__main__':
    unittest.main()