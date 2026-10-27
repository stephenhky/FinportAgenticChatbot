
import os

import requests
from langchain.tools import tool


@tool
def stock_correlation_retriever(symbol1: str, symbol2: str, startdate: str, enddate: str) -> str:
    """Compute the correlation between two stocks over a multi-day date range.
    Dates must be in YYYY-mm-dd format and startdate must be strictly earlier than enddate (spanning at least several trading days).
    """
    payload = {'symbol1': symbol1, 'symbol2': symbol2, 'startdate': startdate, 'enddate': enddate}
    headers = {'Content-Type': 'application/json'}
    response = requests.request(
        "GET",
        os.environ['STOCKCORR_API_URL'],
        headers=headers,
        params=payload
    )
    return response.text
