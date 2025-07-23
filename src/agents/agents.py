
import os
import json
from typing import Literal
from types import FunctionType

import requests
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.tools import tool
from langgraph.types import Command
from langgraph.graph import END
from langgraph.prebuilt import create_react_agent

from .state import State, Router


def get_task_router_node(llm: BaseChatModel) -> FunctionType:
    TASK_ROUTER_PROMPT = """
    You are a task router tasked with managing a conversation between the following workers:
                                  "joker", "stock_information_retriever", "stock_correlation_retriever", "crash_predictor".

                                  Given the following user request, respond with the worker to act next.
                                  Each worker will perform a task and respond with their results and status.
                                  Analyze the results carefully and decide which worker to call next accordingly.
                                  When finished, respond with FINISH.
    """

    def task_router_node(state: State) -> Command[
        Literal["joker", "stock_information_retriever", "stock_correlation_retriever", "crash_predictor", "__end__"]]:
        messages = [{"role": "system", "content": TASK_ROUTER_PROMPT}, ] + state["messages"]
        response = llm.with_structured_output(Router).invoke(messages)
        print(">>>>>>>")
        print(response)
        goto = response["next"]
        if goto == "FINISH":
            goto = END

        return Command(goto=goto, update={"next": goto})

    return task_router_node


def get_joker_node(llm: BaseChatModel) -> FunctionType:
    @tool
    def give_a_joke() -> str:
        """Give a joke."""
        response = llm.invoke("Tell me a joke.")
        return json.dumps({"joke": response.content})

    joker_agent = create_react_agent(
        llm, tools=[give_a_joke], prompt="""
        You are an entertainer who give a joke.
        You get one joke from the large language model and you return this joke back to the user.
        """
    )

    def joker_node(state: State) -> Command[Literal["__end__"]]:
        result = joker_agent.invoke(state)
        return Command(goto="__end__", update={"messages": result['messages']})

    return joker_node


def get_stock_information_retriever_node(llm: BaseChatModel) -> FunctionType:
    @tool
    def stock_information_retriever(symbol: str, startdate: str, enddate: str) -> str:
        """Compute information for a given stock with a given date range, with dates in the format YYYY-mm-dd."""
        payload = {'symbol': symbol, 'startdate': startdate, 'enddate': enddate}
        headers = {'Content-Type': 'application/json'}
        response = requests.request(
            "GET",
            os.environ['STOCKINFO_API_URL'],
            headers=headers, params=payload
        )
        return response.text

    stock_information_retriever_agent = create_react_agent(
        llm, tools=[stock_information_retriever], prompt="""
        You are a stock information retriever, computing information about a stock given its symbole and a date range.
        And you return the information back to the user.
        """
    )

    def stock_information_retriever_node(state: State) -> Command[Literal["__end__"]]:
        result = stock_information_retriever_agent.invoke(state)
        return Command(goto="__end__", update={"messages": result['messages']})

    return stock_information_retriever_node


def get_stock_correlation_retriever_node(llm: BaseChatModel) -> FunctionType:
    @tool
    def stock_correlation_retriever(symbol1: str, symbol2: str, startdate: str, enddate: str) -> str:
        """Compute the correlation between two stocks with a given date range, with dates in the format YYYY-mm-dd."""
        payload = {'symbol1': symbol1, 'symbol2': symbol2, 'startdate': startdate, 'enddate': enddate}
        headers = {'Content-Type': 'application/json'}
        response = requests.request(
            "GET",
            os.environ['STOCKCORR_API_URL'],
            headers=headers,
            params=payload
        )
        return response.text

    stock_correlation_retriever_agent = create_react_agent(
        llm, tools=[stock_correlation_retriever], prompt="""
        You are an analyst who computes the correlation between two stocks for a given date range.
        And you return the information back to the user.
        """
    )

    def stock_correlation_retriever_node(state: State) -> Command[Literal["__end__"]]:
        result = stock_correlation_retriever_agent.invoke(state)
        return Command(goto="__end__", update={"messages": result['messages']})

    return stock_correlation_retriever_node


def get_crash_predictor_node(llm: BaseChatModel) -> FunctionType:
    @tool
    def crash_predictor(symbol: str = "^GSPC", startdate: str = None, enddate: str = None) -> str:
        """Compute the potential crash date for either a given stock or S&P 500.
        If the symbol is not given, it is assumed to be S&P 500 (^GSPC).
        If the date range is not given, it is assumed to be the last one year.
        And you return the information back to the user.
        """
        payload = {'symbol': symbol, 'startdate': startdate, 'enddate': enddate}
        headers = {'Content-Type': 'application/json'}
        response = requests.request(
            "GET",
            os.environ['CRASH_PREDICTOR_API_URL'],
            headers=headers,
            params=payload
        )
        return response.text

    crash_predictor_agent = create_react_agent(
        llm, tools=[crash_predictor], prompt="""
        You are a scientist who computes or predict the potential crash date of either a stock or S&P 500.
        And you return the information back to the user.
        """
    )

    def crash_predictor_node(state: State) -> Command[Literal["__end__"]]:
        result = crash_predictor_agent.invoke(state)
        return Command(goto="__end__", update={"messages": result['messages']})

    return crash_predictor_node
