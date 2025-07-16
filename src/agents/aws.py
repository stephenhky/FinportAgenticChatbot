
import os

import boto3
from botocore.config import Config
from langchain.chat_models import init_chat_model
from langchain_aws.chat_models.bedrock_converse import ChatBedrockConverse
from dotenv import load_dotenv
load_dotenv()


def get_aws_bedrock_llm(bedrock_llm_id: str=None) -> ChatBedrockConverse:
    bedrock_runtime = boto3.client(
        service_name="bedrock-runtime",
        region_name="us-east-1",
        config=Config(read_timeout=1024),
        aws_access_key_id=os.environ.get("AWS_ACC_ACCESS_TOKEN"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
    )
    llm = init_chat_model(
        os.environ.get("BEDROCK_LLM_ID") if bedrock_llm_id is None else bedrock_llm_id,
        model_provider="bedrock_converse",
        client=bedrock_runtime,
        config={"max_tokens": 4096, "temperature": 0.7, "top_p": 0.8}
    )
    return llm
