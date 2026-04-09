import time

import ccxt
import pandas as pd
from rich.console import Console

console = Console()

# BTCUSDT Perpetual contract (BTCUSDT.P)
# Primary: Binance USDT-Margined Futures (fapi.binance.com)
# Fallback: Bybit perpetual — same contract, different venue, not geo-blocked in the US
_EXCHANGE_CANDIDATES = [
    ("Binance USDT-M Futures", "BTC/USDT:USDT", lambda: ccxt.binanceusdm({"enableRateLimit": True})),
    ("Bybit",                  "BTC/USDT:USDT", lambda: ccxt.bybit({"enableRateLimit": True})),
]


def _get_exchange() -> tuple:
    """
    Return (exchange, symbol) for the first venue that is reachable.
    Skips exchanges that return a geo-block (HTTP 451) error.
    """
    for name, symbol, factory in _EXCHANGE_CANDIDATES:
        try:
            ex = factory()
            ex.load_markets()
            console.print(f"[green]Using exchange: {name} ({symbol})[/green]")
            return ex, symbol
        except ccxt.ExchangeNotAvailable as e:
            if "451" in str(e) or "restricted location" in str(e).lower():
                console.print(f"[yellow]{name} geo-blocked (451), trying next…[/yellow]")
                continue
            raise
        except Exception as e:
            console.print(f"[yellow]{name} unavailable ({e}), trying next…[/yellow]")
            continue
    raise RuntimeError("No accessible exchange found for BTCUSDT perpetual. Check your network.")


def fetch_1m_candles(limit: int = 21600) -> pd.DataFrame:
    """
    Fetch the latest `limit` 1-minute OHLCV candles for BTCUSDT perpetual (BTCUSDT.P).
    Tries Binance USDT-M Futures first, falls back to Bybit if geo-blocked.
    Returns a DataFrame with columns: timestamp, open, high, low, close, volume.
    """
    exchange, symbol = _get_exchange()
    all_candles: list = []
    remaining = limit

    console.print(f"[cyan]Fetching {limit} x 1m candles for {symbol} (perpetual, {limit//1440} days)...[/cyan]")

    # First page: no since → gets the most recent candles
    page = exchange.fetch_ohlcv(symbol, "1m", limit=min(1000, remaining))
    if not page:
        raise RuntimeError(f"No candles returned from {exchange.id}")

    all_candles = page + all_candles
    remaining -= len(page)

    # Walk backward using the oldest timestamp in the current page
    while remaining > 0 and len(page) > 0:
        oldest_ts = page[0][0]
        since = oldest_ts - (min(1000, remaining) * 60 * 1000)
        page = exchange.fetch_ohlcv(symbol, "1m", since=since, limit=min(1000, remaining))
        all_candles = page + all_candles
        remaining -= len(page)
        time.sleep(exchange.rateLimit / 1000)

    df = pd.DataFrame(
        all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = (
        df.drop_duplicates("timestamp")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    df = df.tail(limit).reset_index(drop=True)
    console.print(
        f"[green]Fetched {len(df)} candles. "
        f"Range: {df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]}[/green]"
    )
    return df
