"""
Market structure levels for the trading scanner.

  MRP        = VWAP (daily reset at 00:00 UTC)
  Daily POC  = (prev_H + prev_L + prev_C) / 3  (yesterday UTC)
  Weekly POC = weekly_open × (1 + WEEKLY_ADJ / 100)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd


def compute_levels(df: pd.DataFrame, weekly_adj: float = 0.0324) -> dict:
    """
    Compute MRP, Daily POC, and Weekly POC from 1-minute OHLCV data.

    Parameters
    ----------
    df : pd.DataFrame
        Must have columns: timestamp (UTC unix ms), open, high, low, close, volume.
        Rows should be sorted oldest-first.
    weekly_adj : float
        Percentage adjustment applied to weekly open (default 0.0324).
        Weekly POC = weekly_open × (1 + weekly_adj / 100).

    Returns
    -------
    dict with keys: mrp, daily_poc, weekly_poc, weekly_open
        None for any level that cannot be computed from available data.
    """
    now_utc   = datetime.now(timezone.utc)
    today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    today_start_ms = int(today_utc.timestamp() * 1000)
    yest_start_ms  = int((today_utc - timedelta(days=1)).timestamp() * 1000)

    days_since_monday = now_utc.weekday()  # Mon=0 … Sun=6
    week_start_ms     = int((today_utc - timedelta(days=days_since_monday)).timestamp() * 1000)

    # ── MRP — VWAP from today's candles ──────────────────────────────────────
    today_df = df[df["timestamp"] >= today_start_ms]
    if len(today_df) and today_df["volume"].sum() > 0:
        tp  = (today_df["high"] + today_df["low"] + today_df["close"]) / 3
        mrp = float((tp * today_df["volume"]).sum() / today_df["volume"].sum())
        mrp = round(mrp, 2)
    else:
        mrp = None

    # ── Daily POC — pivot from yesterday ────────────────────────────────────
    yest_df = df[(df["timestamp"] >= yest_start_ms) & (df["timestamp"] < today_start_ms)]
    if len(yest_df):
        prev_h    = float(yest_df["high"].max())
        prev_l    = float(yest_df["low"].min())
        prev_c    = float(yest_df["close"].iloc[-1])
        daily_poc = round((prev_h + prev_l + prev_c) / 3, 2)
    else:
        daily_poc = None

    # ── Weekly POC — single level from current week open ────────────────────
    week_df = df[df["timestamp"] >= week_start_ms]
    if len(week_df):
        weekly_open = round(float(week_df["open"].iloc[0]), 2)
        weekly_poc  = round(weekly_open * (1 + weekly_adj / 100), 2)
    else:
        weekly_open = None
        weekly_poc  = None

    return {
        "mrp":         mrp,
        "daily_poc":   daily_poc,
        "weekly_poc":  weekly_poc,
        "weekly_open": weekly_open,
    }
