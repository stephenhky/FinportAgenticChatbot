
import sys
import json
import traceback

import telebot
from botocore.exceptions import ClientError

from bot import bot


def bot_polling():
    bot.polling()
    return {
        'statusCode': 200,
        'body': json.dumps({'approach': 'polling'})
    }


def bot_webhook(message):
    update = telebot.types.Update.de_json(message)
    print(update)
    if update.message is not None:
        message = update.message

        try:
            bot.process_new_messages([message])
            print('Processed.')
            return {
                'statusCode': 200,
                'body': json.dumps({'approach': 'webhook'})
            }
        except AttributeError:
            bot.send_message(message.chat.id, "API error!")
            print('Telegram error.', file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            return {
                'statusCode': 200,
                'body': json.dumps({'approach': 'webhook'})
            }
        except ClientError as e:
            if e.response['Error']['Code'] == 'ThrottlingException':
                print("Infinite loop.", file=sys.stderr)
                print(traceback.format_exc(), file=sys.stderr)
                bot.send_message(message.chat.id, "I am in a dead loop! I am stopping now!")
                return {
                    'statusCode': 200,
                    'body': json.dumps({'approach': 'webhook', 'text': 'Loop!'})
                }
            else:
                bot.send_message(message.chat.id, "Unknown error!")
                return {
                    'statusCode': 200,
                    'body': json.dumps({'approach': 'webhook', 'text': 'Loop!'})
                }
    else:
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Not handled exception.'})
        }


def handler(event, context):
    """
    AWS Lambda handler function.

    :param event: The event passed by AWS Lambda.
    :param context: The context passed by AWS Lambda.
    """

    # Telegram sends a POST request with the update in the body
    print(event)
    print(type(event))
    # Process the update with your bot logic
    message = json.loads(event['body'])
    try:
        if message.get('polling', False):
            return bot_polling()
        else:
            return bot_webhook(message)
        # A 200 OK response tells Telegram the webhook is working.
    except Exception as e:
        # If anything goes wrong, log the error
        print(f"Error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Internal Server Error"})
        }


if __name__ == '__main__':
    _ = bot_polling()
