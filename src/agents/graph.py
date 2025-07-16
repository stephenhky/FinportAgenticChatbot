
from typing import Generator, Any

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import tools_condition

from .state import State
from .agents import get_task_router_node, get_joker_node, get_stock_information_retriever_node, \
    get_stock_correlation_retriever_node, get_crash_predictor_node


class FinportAgent:
    def __init__(self):
        self._init_graph()

    def _init_graph(self) -> None:
        graph_builder = StateGraph(State)

        graph_builder.add_node("task_router", get_task_router_node)
        graph_builder.add_node("joker", get_joker_node)
        graph_builder.add_node("stock_information_retriever", get_stock_information_retriever_node)
        graph_builder.add_node("stock_correlation_retriever", get_stock_correlation_retriever_node)
        graph_builder.add_node("crash_predictor", get_crash_predictor_node)

        graph_builder.add_edge(START, "task_router")
        graph_builder.add_conditional_edges(
            "task_router",
            tools_condition,
            {
                "joker": "joker",
                "stock_information_retriever": "stock_information_retriever",
                "stock_correlation_retriever": "stock_correlation_retriever",
                "crash_predictor": "crash_predictor",
                "__end__": END
            }
        )

        self.graph = graph_builder.compile()

    def stream_graph_updates(self, user_input: str) -> Generator[dict[str, Any], None, None]:
        for event in self.graph.stream({"messages": [{"role": "user", "content": user_input}]}):
            for value in event.values():
                yield value
