import json
from . import bot

def handler(event, context):
    """
    AWS Lambda handler function.

    :param event: The event passed by AWS Lambda.
    :param context: The context passed by AWS Lambda.
    """
    try:
        # Telegram sends a POST request with the update in the body
        body = json.loads(event.get("body", "{}"))
        
        # Process the update with your bot logic
        response = bot.process_update(body)
        
        # A 200 OK response tells Telegram the webhook is working.
        return {
            "statusCode": 200,
            "body": json.dumps(response)
        }

    except Exception as e:
        # If anything goes wrong, log the error
        print(f"Error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Internal Server Error"})
        }