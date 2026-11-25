
import os

import boto3
from botocore.config import Config
from langchain.chat_models import init_chat_model
from langchain_aws.chat_models.bedrock_converse import ChatBedrockConverse
from dotenv import load_dotenv
load_dotenv()


DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 4096

_bedrock_llm_instance: ChatBedrockConverse | None = None


def _build_inference_kwargs() -> dict[str, float | int]:
    """Build inference parameters from environment variables.

    Supports `TEMPERATURE` (or `BEDROCK_TEMPERATURE`) and `TOP_P` (or `BEDROCK_TOP_P`).
    When neither is set, defaults to `temperature=0.7`. When only `TOP_P` is set,
    `temperature` is omitted so models that forbid specifying both (e.g. Claude 4.5)
    do not reject the request.
    """
    kwargs: dict[str, float | int] = {"max_tokens": DEFAULT_MAX_TOKENS}

    temperature_str = os.environ.get("TEMPERATURE") or os.environ.get("BEDROCK_TEMPERATURE")
    top_p_str = os.environ.get("TOP_P") or os.environ.get("BEDROCK_TOP_P")

    if temperature_str is not None and temperature_str.strip() != "":
        kwargs["temperature"] = float(temperature_str)
    if top_p_str is not None and top_p_str.strip() != "":
        kwargs["top_p"] = float(top_p_str)

    if "temperature" not in kwargs and "top_p" not in kwargs:
        kwargs["temperature"] = DEFAULT_TEMPERATURE

    return kwargs


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
            **_build_inference_kwargs(),
        )
    return _bedrock_llm_instance
