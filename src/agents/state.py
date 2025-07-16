
from typing import Annotated, Literal

from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class Router(TypedDict):
    next: Literal["joker", "stock_information_retriever", "stock_correlation_retriever", "crash_predictor", "FINISH"]


class State(TypedDict):
    messages: Annotated[list, add_messages]
    next: str # next agent to call
    eda_images: list[str]
