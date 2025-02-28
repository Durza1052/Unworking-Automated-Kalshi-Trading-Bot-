import streamlit as st
import requests
import pandas as pd
import datetime
import logging
from typing import Optional
from dotenv import load_dotenv
import os

from api3 import fetch_hourly_markets, place_trade
from bot3 import KalshiBot

import plotly.graph_objects as go

load_dotenv()
logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")

# 1) Title
st.title("Kalshi Bot (Profit Goal + Candlestick + Auto-Trading)")

# 2) Sidebar Configuration
st.sidebar.subheader("Trading Parameters")
entry_price_low = st.sidebar.slider("Entry Price Low", 0.0, 1.0, 0.30, 0.01)
entry_price_high = st.sidebar.slider("Entry Price High", 0.0, 1.0, 0.80, 0.01)
exit_price_profit = st.sidebar.slider("Exit Price Profit", 0.0, 1.0, 0.90, 0.01)
exit_price_loss = st.sidebar.slider("Exit Price Stop Loss", 0.0, 1.0, 0.15, 0.01)
trade_size = st.sidebar.number_input("Trade Size", min_value=1, max_value=100, value=10)
profit_goal = st.sidebar.number_input("Profit Goal ($)", min_value=0, value=100)
max_drawdown = st.sidebar.number_input("Max Drawdown ($)", min_value=0, value=50)
auto_trading = st.sidebar.checkbox("Enable Auto-Trading", value=False)
underlying_symbol = st.sidebar.selectbox("Underlying Symbol", ["ethereum", "bitcoin"])
chart_interval = st.sidebar.selectbox("Candlestick Interval (minutes)", [1, 5, 15, 30, 60], index=1)
refresh_rate = st.sidebar.slider("Refresh Interval (seconds)", 5, 60, 15, 1)

# 3) Session State Initialization
if "candles" not in st.session_state:
    st.session_state.candles = pd.DataFrame(columns=["time", "open", "high", "low", "close"])
if "positions" not in st.session_state:
    st.session_state.positions = {}
if "cumulative_pnl" not in st.session_state:
    st.session_state.cumulative_pnl = 0.0

# 4) Instantiate the Trading Bot
bot = KalshiBot(
    entry_price_low=entry_price_low,
    entry_price_high=entry_price_high,
    exit_price_profit=exit_price_profit,
    exit_price_loss=exit_price_loss,
    trade_size=trade_size,
    profit_goal=profit_goal,
    max_drawdown=max_drawdown
)

# 5) Fetch Hourly Markets
SERIES_LIST = ["KXETHD", "KXETH", "KXBTCD", "KXBTC"]

@st.cache_data(ttl=30)
def get_hourly_markets() -> list:
    all_markets = []
    for s_ticker in SERIES_LIST:
        # Fetch markets closing within the next 1 hour.
        hourly = fetch_hourly_markets(s_ticker, hours=1)
        if hourly:
            all_markets.extend(hourly)
    return all_markets

all_markets = get_hourly_markets()
st.write(f"Loaded {len(all_markets)} HOURLY markets (within 1 hour) from series: {SERIES_LIST}.")

# 6) Underlying Price and Candlestick Chart Functions
def fetch_current_price(symbol: str) -> Optional[float]:
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol}&vs_currencies=usd"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get(symbol, {}).get("usd", None)
    except:
        return None

def update_candles(symbol: str, interval: int):
    now = datetime.datetime.now(datetime.timezone.utc)
    price = fetch_current_price(symbol)
    if price is None:
        return
    df = st.session_state.candles
    new_row = pd.DataFrame([{"time": now, "open": price, "high": price, "low": price, "close": price}])
    if df.empty:
        df = new_row
    else:
        last_time = df.iloc[-1]["time"]
        if not isinstance(last_time, datetime.datetime):
            last_time = pd.to_datetime(last_time)
        delta = (now - last_time).total_seconds() / 60.0
        if delta < interval:
            idx = df.index[-1]
            df.at[idx, "high"] = max(df.at[idx, "high"], price)
            df.at[idx, "low"] = min(df.at[idx, "low"], price)
            df.at[idx, "close"] = price
        else:
            df = pd.concat([df, new_row], ignore_index=True)
    st.session_state.candles = df

def plot_candles():
    df = st.session_state.candles.copy()
    if df.empty:
        st.warning("No candlestick data yet.")
        return
    df["time_str"] = df["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    fig = go.Figure(data=[go.Candlestick(
        x=df["time_str"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"]
    )])
    fig.update_layout(xaxis_rangeslider_visible=False, width=700, height=400)
    st.plotly_chart(fig)

# 7) PnL Helper Function
def update_pnl(profit: float):
    st.session_state.cumulative_pnl += profit

# 8) Auto-Trading Logic (Scanning both Yes and No sides)
def auto_trade_logic():
    if st.session_state.cumulative_pnl >= bot.profit_goal:
        st.write("**Profit goal reached! Stopping trades.**")
        return
    if st.session_state.cumulative_pnl <= -bot.max_drawdown:
        st.write("**Max drawdown reached! Stopping trades.**")
        return

    for market in all_markets:
        ticker = market.get("ticker")
        yes_bid = market.get("yes_bid")
        no_bid = market.get("no_bid")
        if not ticker or (yes_bid is None and no_bid is None):
            continue

        # Check both sides using your bot's logic.
        enter_yes = yes_bid is not None and bot.should_enter_trade(yes_bid)
        enter_no = no_bid is not None and bot.should_enter_trade(no_bid)
        chosen_side = None
        chosen_price = None

        if enter_yes and enter_no:
            if yes_bid <= no_bid:
                chosen_side = "yes"
                chosen_price = yes_bid
            else:
                chosen_side = "no"
                chosen_price = no_bid
        elif enter_yes:
            chosen_side = "yes"
            chosen_price = yes_bid
        elif enter_no:
            chosen_side = "no"
            chosen_price = no_bid
        else:
            st.write(f"No action for {ticker}: yes_bid={yes_bid}, no_bid={no_bid}")
            continue

        st.write(f"Placing order on {ticker} for side '{chosen_side}' at price {chosen_price:.2f}")
        price_in_cents = int(chosen_price * 100)

        if chosen_side == "yes":
            order_response = place_trade(
                action="buy",
                side="yes",
                ticker=ticker,
                count=bot.trade_size,
                order_type="Market",
                yes_price=price_in_cents,
                no_price=0,
                sell_position_floor=0,
                client_order_id="order_" + ticker.replace("-", "_")
            )
        else:
            order_response = place_trade(
                action="buy",
                side="no",
                ticker=ticker,
                count=bot.trade_size,
                order_type="Market",
                yes_price=0,
                no_price=price_in_cents,
                sell_position_floor=0,
                client_order_id="order_" + ticker.replace("-", "_")
            )

        if order_response:
            st.write("Order placed successfully:", order_response)
            st.session_state.positions[ticker] = {
                "side": chosen_side,
                "entry_price": chosen_price,
                "quantity": bot.trade_size
            }
        else:
            st.write("Order placement failed for", ticker)

# 9) Main Loop: Update Candles, Display Chart, Run Auto-Trading, and Refresh
update_candles(underlying_symbol, chart_interval)
st.subheader(f"{underlying_symbol.capitalize()} Candlestick Chart")
plot_candles()

st.subheader("Current PnL and Open Positions")
st.write(f"**Cumulative PnL:** ${st.session_state.cumulative_pnl:.2f}")
st.write("Open Positions:", st.session_state.positions)

if auto_trading:
    auto_trade_logic()

st.write(f"Auto-refresh in {refresh_rate} seconds...")
if hasattr(st, "experimental_rerun"):
    st.experimental_rerun()
else:
    st.write("Rerun not supported in this Streamlit version. Please refresh manually.")
