
import os

import requests
from langchain.tools import tool


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
