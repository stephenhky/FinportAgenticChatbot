# Telegram Bot Webhook - AWS Lambda

This project is a template for creating a Telegram bot webhook hosted on AWS Lambda.

## Project Structure

- `src/`: This directory contains the main source code for the Lambda function.
  - `main.py`: The entry point for the AWS Lambda function. It handles the incoming webhook requests from Telegram.
  - `bot.py`: This file contains the core logic for your Telegram bot. You can define your command handlers and message processors here.
  - `cli.py`: A local CLI (`finport-chat`) that sends your typed messages through the Lambda handler and prints the bot's replies.
- `tests/`: This directory is for your tests.
  - `test_handler.py`: An example test file for the Lambda handler.
- `Dockerfile`: Container definition for building the AWS Lambda image with Python 3.13.
- `requirements.txt`: This file lists the Python dependencies for the project. You can install them using `pip install -r requirements.txt`.
- `.gitignore`: This file specifies which files and directories should be ignored by Git.

## Local Testing (CLI)

Chat with the bot from your terminal, as if you were on Telegram. Each message goes through the real Lambda handler, AWS Bedrock and the tool APIs; the bot's replies are printed instead of being sent to Telegram, so no Telegram token is needed.

```bash
pip install -e .
finport-chat                    # interactive chat; type 'exit' to quit
finport-chat "Tell me a joke"   # send one message and exit
finport-chat -v                 # also show handler/agent debug logs
```

Configuration is read from `--env-file`, otherwise from `./.env` and then `src/.env` (`BEDROCK_LLM_ID`, `AWS_REGION`, `STOCKINFO_API_URL`, `STOCKCORR_API_URL`, `CRASH_PREDICTOR_API_URL`). AWS credentials are picked up the usual boto3 way.

## Deployment

You can deploy this application as a container image to AWS Lambda (e.g. via Amazon ECR).

1. **Build and Tag Docker Image**:
   ```bash
   docker build -t finport-telegram-bot .
   docker tag finport-telegram-bot:latest <aws_account_id>.dkr.ecr.<region>.amazonaws.com/finport-telegram-bot:latest
   ```

2. **Push to Amazon ECR**:
   ```bash
   aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <aws_account_id>.dkr.ecr.<region>.amazonaws.com
   docker push <aws_account_id>.dkr.ecr.<region>.amazonaws.com/finport-telegram-bot:latest
   ```

3. **Deploy or Update AWS Lambda Function**:
   When creating or updating your Lambda function, configure the timeout to **59 seconds** (recommended for LLM reasoning and API calls):
   ```bash
   aws lambda create-function \
       --function-name finport-telegram-bot \
       --package-type Image \
       --code ImageUri=<aws_account_id>.dkr.ecr.<region>.amazonaws.com/finport-telegram-bot:latest \
       --role <lambda_execution_role_arn> \
       --timeout 59
   ```
   Or update the timeout for an existing function:
   ```bash
   aws lambda update-function-configuration \
       --function-name finport-telegram-bot \
       --timeout 59
   ```