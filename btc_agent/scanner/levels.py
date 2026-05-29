"""
Market structure levels for the trading scanner.

  MRP        = VWAP (daily reset at 00:00 UTC)
  Daily POC  = (prev_H + prev_L + prev_C) / 3  (yesterday UTC)
  Weekly POC = weekly_open × (1 + WEEKLY_ADJ / 100)
"""
from __future__ import annotations

import pandas as pd


def compute_levels(df: pd.DataFrame, weekly_adj: float = 0.0324) -> dict:
    """
    Compute MRP, Daily POC, and Weekly POC from 1-minute OHLCV data.

    Parameters
    ----------
    df : pd.DataFrame
        Must have columns: timestamp (UTC datetime64 or unix ms int), open, high,
        low, close, volume.  Rows should be sorted oldest-first.
    weekly_adj : float
        Percentage adjustment applied to weekly open (default 0.0324).
        Weekly POC = weekly_open × (1 + weekly_adj / 100).

    Returns
    -------
    dict with keys: mrp, daily_poc, weekly_poc, weekly_open
        None for any level that cannot be computed from available data.
    """
    now_ts    = pd.Timestamp.now(tz="UTC")
    today_ts  = now_ts.normalize()                           # 00:00 UTC today
    yest_ts   = today_ts - pd.Timedelta(days=1)
    week_ts   = today_ts - pd.Timedelta(days=now_ts.dayofweek)  # Mon=0

    ts = df["timestamp"]
    # Support both datetime64[ns, UTC] and plain integer ms columns
    if pd.api.types.is_integer_dtype(ts):
        today_start = int(today_ts.timestamp() * 1000)
        yest_start  = int(yest_ts.timestamp()  * 1000)
        week_start  = int(week_ts.timestamp()  * 1000)
        today_mask  = ts >= today_start
        yest_mask   = (ts >= yest_start) & (ts < today_start)
        week_mask   = ts >= week_start
    else:
        today_mask  = ts >= today_ts
        yest_mask   = (ts >= yest_ts) & (ts < today_ts)
        week_mask   = ts >= week_ts

    # ── MRP — VWAP from today's candles ──────────────────────────────────────
    today_df = df[today_mask]
    if len(today_df) and today_df["volume"].sum() > 0:
        tp  = (today_df["high"] + today_df["low"] + today_df["close"]) / 3
        mrp = float((tp * today_df["volume"]).sum() / today_df["volume"].sum())
        mrp = round(mrp, 2)
    else:
        mrp = None

    # ── Daily POC — pivot from yesterday ────────────────────────────────────
    yest_df = df[yest_mask]
    if len(yest_df):
        prev_h    = float(yest_df["high"].max())
        prev_l    = float(yest_df["low"].min())
        prev_c    = float(yest_df["close"].iloc[-1])
        daily_poc = round((prev_h + prev_l + prev_c) / 3, 2)
    else:
        daily_poc = None

    # ── Weekly POC — single level from current week open ────────────────────
    week_df = df[week_mask]
    if len(week_df):
        weekly_open = round(float(week_df["open"].iloc[0]), 2)
        weekly_poc  = round(weekly_open * (1 + weekly_adj / 100), 2)
    else:
        weekly_open = None
        weekly_poc  = None

    # ── 4H POC — daily-VWAP at close of previous 4H bar ─────────────────────
    # At each 4H boundary, the accumulated daily VWAP through the previous bar's
    # close becomes the static POC level for the new 4H window. During the first
    # window of the day (00:00–04:00 UTC) the previous bar closed at the daily
    # reset, so the level carries yesterday's full-day VWAP.
    current_4h_hour = (now_ts.hour // 4) * 4
    if current_4h_hour == 0:
        win_start_ts, win_end_ts = yest_ts, today_ts
    else:
        win_start_ts = today_ts
        win_end_ts   = today_ts + pd.Timedelta(hours=current_4h_hour)
    if pd.api.types.is_integer_dtype(ts):
        win_start_ms = int(win_start_ts.timestamp() * 1000)
        win_end_ms   = int(win_end_ts.timestamp()   * 1000)
        h4_mask = (ts >= win_start_ms) & (ts < win_end_ms)
    else:
        h4_mask = (ts >= win_start_ts) & (ts < win_end_ts)
    vwap_4h = None
    sub = df[h4_mask].copy()
    if len(sub) and sub["volume"].sum() > 0:
        # Aggregate 1m candles → 4H bars to match TradingView's VWAP formula:
        # each bar's typical price = (MAX_H + MIN_L + LAST_C) / 3 of the 4H period
        if pd.api.types.is_integer_dtype(sub["timestamp"]):
            bar_ms = 4 * 60 * 60 * 1000
            sub["_bar"] = (sub["timestamp"] // bar_ms) * bar_ms
        else:
            sub["_bar"] = sub["timestamp"].dt.floor("4h")
        g = sub.groupby("_bar").agg(
            high=("high", "max"), low=("low", "min"),
            close=("close", "last"), volume=("volume", "sum"),
        )
        tp_4h   = (g["high"] + g["low"] + g["close"]) / 3
        vwap_4h = round(float((tp_4h * g["volume"]).sum() / g["volume"].sum()), 2)

    return {
        "mrp":         mrp,
        "daily_poc":   daily_poc,
        "weekly_poc":  weekly_poc,
        "weekly_open": weekly_open,
        "4h_poc":      vwap_4h,
    }
