
import os

import requests
from langchain.tools import tool


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
