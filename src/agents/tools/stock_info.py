
import os

import requests
from langchain.tools import tool


@tool
def stock_information_retriever(symbol: str, startdate: str, enddate: str) -> str:
    """Compute return, volatility, downside/upside risk, and beta for a given stock over a multi-day date range.
    Dates must be in YYYY-mm-dd format and startdate must be strictly earlier than enddate (spanning at least several trading days).
    """
    payload = {'symbol': symbol, 'startdate': startdate, 'enddate': enddate}
    headers = {'Content-Type': 'application/json'}
    response = requests.request(
        "GET",
        os.environ['STOCKINFO_API_URL'],
        headers=headers, params=payload
    )
    return response.text
