
import os

import boto3
from botocore.config import Config
from langchain.chat_models import init_chat_model
from langchain_aws.chat_models.bedrock_converse import ChatBedrockConverse
from dotenv import load_dotenv
load_dotenv()


_bedrock_llm_instance: ChatBedrockConverse | None = None


def get_aws_bedrock_llm(bedrock_llm_id: str | None = None) -> ChatBedrockConverse:
    """Return a singleton instance of the AWS Bedrock Converse chat model."""
    global _bedrock_llm_instance
    if _bedrock_llm_instance is None:
        model_id = bedrock_llm_id or os.environ.get("BEDROCK_LLM_ID")
        bedrock_runtime = boto3.client(
            service_name="bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            config=Config(read_timeout=1024),
            # aws_access_key_id=os.environ.get("AWS_ACC_ACCESS_TOKEN"),
            # aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
        )
        _bedrock_llm_instance = init_chat_model(
            model_id,
            model_provider="bedrock_converse",
            client=bedrock_runtime,
            config={"max_tokens": 4096, "temperature": 0.7, "top_p": 0.8}
        )
    return _bedrock_llm_instance
