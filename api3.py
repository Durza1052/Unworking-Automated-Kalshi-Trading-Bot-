import os
import requests
import logging
from typing import Optional, Dict, Any, List
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import datetime

logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")

KALSHI_API_KEY: str = os.getenv("KALSHI_API_KEY", "")
BASE_URL: str = os.getenv("KALSHI_BASE_URL", "https://api.elections.kalshi.com/trade-api/v2")

HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "Authorization": f"Bearer {KALSHI_API_KEY}" if KALSHI_API_KEY else ""
}

session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500,502,503,504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)

def fetch_event_data(series_ticker: str, with_nested_markets: bool = True) -> Optional[Dict[str, Any]]:
    """
    Fetch event data for a given series ticker using the GetEvents endpoint.
    Returns the JSON data or None on error.
    """
    url = f"{BASE_URL}/events"
    params = {"series_ticker": series_ticker}
    if with_nested_markets:
        params["with_nested_markets"] = "true"

    try:
        resp = session.get(url, headers=HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        events = data.get("events", [])
        logging.warning("Series %s: fetched %d events (with_nested_markets=%s)", series_ticker, len(events), with_nested_markets)
        return data
    except Exception as e:
        logging.error("Error fetching event data for %s: %s", series_ticker, str(e))
        return None

def fetch_hourly_markets(series_ticker: str, hours: int = 1) -> List[Dict[str, Any]]:
    """
    Fetch all markets for a series, then return only those that:
      - Are NOT finalized
      - Have a close_time within the next 'hours' hours (default is 1 hour).
    """
    data = fetch_event_data(series_ticker, with_nested_markets=True)
    if not data:
        return []

    # Use an offset-aware datetime in UTC.
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now + datetime.timedelta(hours=hours)

    def is_hourly(market: Dict[str, Any]) -> bool:
        if market.get("status", "").lower() == "finalized":
            return False
        close_str = market.get("close_time")
        if not close_str:
            return False
        try:
            close_time = datetime.datetime.fromisoformat(close_str.replace("Z", "+00:00"))
        except ValueError:
            return False
        return now < close_time <= cutoff

    hourly_markets = []
    if "markets" in data:
        for m in data["markets"]:
            if is_hourly(m):
                hourly_markets.append(m)
    elif "events" in data:
        for event in data["events"]:
            for m in event.get("markets", []):
                if is_hourly(m):
                    hourly_markets.append(m)
    logging.warning("Series %s: returning %d HOURLY markets (non-finalized, within %d hour(s)).", series_ticker, len(hourly_markets), hours)
    return hourly_markets

def place_trade(
    action: str,
    side: str,
    ticker: str,
    count: int,
    order_type: str = "Market",
    yes_price: int = 0,
    no_price: int = 0,
    sell_position_floor: int = 0,
    client_order_id: str = "myorder001"
) -> Optional[Dict[str, Any]]:
    """
    Place an order on Kalshi via the /portfolio/orders endpoint.
    All prices are expressed in cents.
    """
    url = f"{BASE_URL}/portfolio/orders"
    payload = {
        "action": action,           # "buy" or "sell"
        "client_order_id": client_order_id,
        "count": count,
        "sell_position_floor": sell_position_floor,
        "side": side,               # "yes" or "no"
        "ticker": ticker,
        "type": order_type,         # "Market" or "Limit"
        "yes_price": yes_price,
        "no_price": no_price
    }
    try:
        resp = session.post(url, json=payload, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        logging.warning("Order placed successfully: %s", resp.json())
        return resp.json()
    except Exception as e:
        logging.error("Error placing order for %s: %s", ticker, str(e))
        logging.error("Response text: %s", getattr(resp, 'text', 'No response'))
        return None
