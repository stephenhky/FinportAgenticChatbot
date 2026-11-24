# Telegram Bot Webhook - AWS Lambda

This project is a template for creating a Telegram bot webhook hosted on AWS Lambda.

## Architecture

The bot is a single LangGraph ReAct agent (AWS Bedrock LLM) whose tools come from two places:

- **Finport MCP server** ([FinportFastMCP](../FinportFastMCP), deployed separately on AWS Lambda): the financial tools —
  `estimate_symbol_info` (return, volatility, downside/upside risk, beta), `estimate_symbols_correlation`,
  `predict_crash` (LPPL crash-date prediction), etc. They are discovered at start-up over the Streamable HTTP
  transport via `langchain-mcp-adapters`, so new tools added to the MCP server become available without changing this bot.
- **Local tools** (`src/agents/tools/`): `give_a_joke`, which uses the LLM itself.

## Project Structure

- `src/`: This directory contains the main source code for the Lambda function.
  - `main.py`: The entry point for the AWS Lambda function. It handles the incoming webhook requests from Telegram.
  - `bot.py`: This file contains the core logic for your Telegram bot. You can define your command handlers and message processors here.
  - `agents/graph.py`: The ReAct agent (`FinportAgent`) combining the local tools with the MCP tools.
  - `clients/aws.py`: AWS Bedrock chat model.
  - `clients/mcp_client.py`: Connection to the Finport MCP server and tool discovery.
  - `cli.py`: A local CLI (`finport-chat`) that sends your typed messages through the Lambda handler and prints the bot's replies.
- `tests/`: This directory is for your tests.
  - `test_handler.py`: Tests for the Lambda handler.
  - `test_mcp.py`: Tests for the MCP client configuration and the agent's use of MCP tools (against a local stub MCP server).
- `Dockerfile`: Container definition for building the AWS Lambda image with Python 3.13.
- `requirements.txt`: This file lists the Python dependencies for the project. You can install them using `pip install -r requirements.txt`.
- `.gitignore`: This file specifies which files and directories should be ignored by Git.

## Configuration

Environment variables, read from `.env` locally or from the AWS Lambda configuration tab:

| Variable | Required | Description |
|---|---|---|
| `API_KEY` | yes (Lambda) | Telegram bot token. |
| `BEDROCK_LLM_ID` | yes | AWS Bedrock model ID. |
| `AWS_REGION` | no | Bedrock region (default `us-east-1`; set automatically on Lambda). |
| `MCP_SERVER_URL` | yes | Finport MCP server endpoint, e.g. `https://<id>.lambda-url.<region>.on.aws/mcp`. If only the base URL is given, `/mcp` is appended. |
| `MCP_SERVER_AUTH_TOKEN` | no | Sent as `Authorization: Bearer <token>` to the MCP server, if it is protected. |
| `MCP_TIMEOUT_SECONDS` | no | HTTP timeout for MCP calls (default `50`, below the 59 s Lambda timeout). |
| `MAX_RETRIES` | no | Maximum number of LLM turns per message before giving up (default `5`). |

`STOCKINFO_API_URL`, `STOCKCORR_API_URL` and `CRASH_PREDICTOR_API_URL` are no longer used.

## Local Testing (CLI)

Chat with the bot from your terminal, as if you were on Telegram. Each message goes through the real Lambda handler, AWS Bedrock and the MCP server; the bot's replies are printed instead of being sent to Telegram, so no Telegram token is needed.

```bash
pip install -e .
finport-chat                    # interactive chat; type 'exit' to quit
finport-chat "Tell me a joke"   # send one message and exit
finport-chat -v                 # also show handler/agent debug logs
```

Configuration is read from `--env-file`, otherwise from `./.env` and then `src/.env` (see [Configuration](#configuration)). AWS credentials are picked up the usual boto3 way.

Run the tests with `pytest`.

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

4. **Configure environment variables** in the Lambda configuration tab (see [Configuration](#configuration)); in particular
   set `MCP_SERVER_URL` to the endpoint of the deployed Finport MCP server.