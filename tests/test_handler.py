import json
import unittest
from unittest.mock import patch, MagicMock
from src import main

class TestLambdaHandler(unittest.TestCase):

    @patch('src.main.bot')
    def test_handler_success(self, mock_bot):
        """
        Test the Lambda handler for a successful invocation.
        """
        # Mock the bot's response
        mock_bot.process_update.return_value = {"message": "Update processed"}

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
        self.assertEqual(json.loads(response['body']), {"message": "Update processed"})
        mock_bot.process_update.assert_called_once()

    def test_handler_error(self):
        """
        Test the Lambda handler for an error scenario.
        """
        # Create an event that will cause an error (e.g., invalid JSON)
        event = {
            "body": "this is not json"
        }
        
        context = {}
        response = main.handler(event, context)
        
        self.assertEqual(response['statusCode'], 500)
        self.assertEqual(json.loads(response['body']), {"message": "Internal Server Error"})

if __name__ == '__main__':
    unittest.main()