# Telegram Bot Webhook - AWS Lambda

This project is a template for creating a Telegram bot webhook hosted on AWS Lambda.

## Project Structure

- `src/`: This directory contains the main source code for the Lambda function.
  - `main.py`: The entry point for the AWS Lambda function. It handles the incoming webhook requests from Telegram.
  - `bot.py`: This file contains the core logic for your Telegram bot. You can define your command handlers and message processors here.
- `tests/`: This directory is for your tests.
  - `test_handler.py`: An example test file for the Lambda handler.
- `requirements.txt`: This file lists the Python dependencies for the project. You can install them using `pip install -r requirements.txt`.
- `template.yaml`: This file is an AWS Serverless Application Model (SAM) template. It defines the AWS resources needed for the application, such as the Lambda function, API Gateway, and necessary permissions.
- `.gitignore`: This file specifies which files and directories should be ignored by Git.

## Deployment

You can deploy this application using the AWS SAM CLI.

1.  Install the AWS SAM CLI.
2.  Configure your AWS credentials.
3.  Build the project: `sam build`
4.  Deploy the project: `sam deploy --guided`