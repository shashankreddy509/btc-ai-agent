"""
Unit tests for btc_agent/scanner/levels.py and _calc_tp in trading/scanner.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from btc_agent.scanner.levels import compute_levels


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal 1m-candle DataFrame from a list of dicts."""
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


# Fixed "now" anchor: Wednesday 2026-01-07 14:30 UTC
# Monday of that week = 2026-01-05 00:00 UTC
_NOW = datetime(2026, 1, 7, 14, 30, 0, tzinfo=timezone.utc)
_TODAY = _NOW.replace(hour=0, minute=0, second=0, microsecond=0)    # 2026-01-07 00:00 UTC
_YEST  = _TODAY - timedelta(days=1)                                  # 2026-01-06 00:00 UTC
_MON   = _TODAY - timedelta(days=2)                                  # 2026-01-05 00:00 UTC


def _patched_levels(df: pd.DataFrame, weekly_adj: float = 0.0324) -> dict:
    """Call compute_levels with a fixed 'now' so tests are deterministic."""
    with patch("btc_agent.scanner.levels.datetime") as mock_dt:
        mock_dt.now.return_value = _NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        return compute_levels(df, weekly_adj=weekly_adj)


# ── MRP (VWAP) ────────────────────────────────────────────────────────────────

def test_vwap_uses_only_todays_candles():
    """Yesterday's candles must not affect MRP."""
    yesterday_candle = {"timestamp": _ms(_YEST), "open": 70000, "high": 71000,
                        "low": 69000, "close": 70500, "volume": 100}
    today_candle     = {"timestamp": _ms(_TODAY), "open": 80000, "high": 81000,
                        "low": 79000, "close": 80500, "volume": 10}
    df = _make_df([yesterday_candle, today_candle])

    result = _patched_levels(df)
    # typical_price of today's candle = (81000 + 79000 + 80500) / 3 = 80166.67
    # volume = 10 → VWAP = 80166.67
    assert result["mrp"] == pytest.approx((81000 + 79000 + 80500) / 3, abs=1)


def test_vwap_typical_price_weighted():
    """VWAP = Σ(tp × vol) / Σ(vol) across today's candles."""
    c1 = {"timestamp": _ms(_TODAY),                          "open": 100, "high": 110, "low": 90,  "close": 105, "volume": 2}
    c2 = {"timestamp": _ms(_TODAY + timedelta(minutes=1)),   "open": 105, "high": 115, "low": 100, "close": 110, "volume": 3}
    df = _make_df([c1, c2])

    tp1 = (110 + 90  + 105) / 3   # 101.667
    tp2 = (115 + 100 + 110) / 3   # 108.333
    expected = (tp1 * 2 + tp2 * 3) / (2 + 3)

    result = _patched_levels(df)
    assert result["mrp"] == pytest.approx(expected, abs=0.1)


def test_vwap_none_when_no_today_candles():
    yest_candle = {"timestamp": _ms(_YEST), "open": 100, "high": 110, "low": 90, "close": 105, "volume": 5}
    df = _make_df([yest_candle])
    result = _patched_levels(df)
    assert result["mrp"] is None


# ── Daily POC ─────────────────────────────────────────────────────────────────

def test_daily_poc_uses_yesterday():
    """Daily POC = (prev_H + prev_L + prev_C) / 3 from yesterday's candles."""
    yest_c1 = {"timestamp": _ms(_YEST),                         "open": 100, "high": 120, "low": 80,  "close": 105, "volume": 5}
    yest_c2 = {"timestamp": _ms(_YEST + timedelta(minutes=1)),  "open": 105, "high": 130, "low": 90,  "close": 110, "volume": 5}
    today_c = {"timestamp": _ms(_TODAY),                         "open": 110, "high": 115, "low": 108, "close": 112, "volume": 3}
    df = _make_df([yest_c1, yest_c2, today_c])

    result = _patched_levels(df)
    prev_h = 130
    prev_l = 80
    prev_c = 110   # last close of yesterday
    expected = round((prev_h + prev_l + prev_c) / 3, 2)
    assert result["daily_poc"] == expected


def test_daily_poc_none_when_no_yesterday_candles():
    today_c = {"timestamp": _ms(_TODAY), "open": 100, "high": 110, "low": 90, "close": 105, "volume": 5}
    df = _make_df([today_c])
    result = _patched_levels(df)
    assert result["daily_poc"] is None


# ── Weekly POC ────────────────────────────────────────────────────────────────

def test_weekly_poc_formula():
    """Weekly POC = weekly_open × (1 + weekly_adj / 100)."""
    mon_c = {"timestamp": _ms(_MON), "open": 71000, "high": 72000, "low": 70000, "close": 71500, "volume": 10}
    df = _make_df([mon_c])

    result = _patched_levels(df, weekly_adj=0.0324)
    expected_poc  = round(71000 * (1 + 0.0324 / 100), 2)
    assert result["weekly_open"] == 71000
    assert result["weekly_poc"]  == expected_poc


def test_weekly_poc_uses_first_candle_of_week():
    """weekly_open = open of the very first 1m candle of the current week."""
    mon_c1 = {"timestamp": _ms(_MON),                         "open": 70000, "high": 71000, "low": 69000, "close": 70500, "volume": 5}
    mon_c2 = {"timestamp": _ms(_MON + timedelta(minutes=1)),  "open": 70500, "high": 71500, "low": 70000, "close": 71000, "volume": 5}
    df = _make_df([mon_c1, mon_c2])

    result = _patched_levels(df)
    assert result["weekly_open"] == 70000   # first candle's open, not second


def test_weekly_poc_none_when_no_week_candles():
    # Only candle is before this week
    old = {"timestamp": _ms(_MON - timedelta(days=7)), "open": 68000, "high": 69000, "low": 67000, "close": 68500, "volume": 5}
    df = _make_df([old])
    result = _patched_levels(df)
    assert result["weekly_poc"] is None


# ── _calc_tp ──────────────────────────────────────────────────────────────────

def _calc_tp(direction, entry, levels):
    """Import and call _calc_tp with a temporary min_tp of 500."""
    from btc_agent.trading import scanner as sc
    with patch.object(sc, "min_tp", return_value=500.0):
        return sc._calc_tp(direction, entry, levels)


def test_calc_tp_long_picks_nearest_above():
    levels = {"mrp": 84000, "daily_poc": 83000, "weekly_poc": 85000}
    tp, reason = _calc_tp("long", 82000, levels)
    assert tp == 83000   # nearest above entry
    assert reason == "Daily POC"


def test_calc_tp_short_picks_nearest_below():
    levels = {"mrp": 80000, "daily_poc": 79000, "weekly_poc": 78000}
    tp, reason = _calc_tp("short", 81000, levels)
    assert tp == 80000   # nearest below entry
    assert reason == "MRP"


def test_calc_tp_enforces_min_floor_long():
    """If nearest level is only 100 pts above entry, TP should be floored at entry + 500."""
    levels = {"mrp": 82100, "daily_poc": None, "weekly_poc": None}
    tp, reason = _calc_tp("long", 82000, levels)
    assert tp == pytest.approx(82500, abs=1)
    assert "min_floor" in reason


def test_calc_tp_enforces_min_floor_short():
    levels = {"mrp": 81900, "daily_poc": None, "weekly_poc": None}
    tp, reason = _calc_tp("short", 82000, levels)
    assert tp == pytest.approx(81500, abs=1)
    assert "min_floor" in reason


def test_calc_tp_fallback_when_no_levels_ahead_long():
    """No levels above entry → fixed_500 fallback."""
    levels = {"mrp": 80000, "daily_poc": 79000, "weekly_poc": 78000}
    tp, reason = _calc_tp("long", 82000, levels)
    assert tp == pytest.approx(82500, abs=1)
    assert reason == "fixed_500"


def test_calc_tp_fallback_when_no_levels_ahead_short():
    levels = {"mrp": 84000, "daily_poc": 85000, "weekly_poc": 86000}
    tp, reason = _calc_tp("short", 82000, levels)
    assert tp == pytest.approx(81500, abs=1)
    assert reason == "fixed_500"


def test_calc_tp_none_levels_treated_as_absent():
    """None values for individual levels must be skipped (not raise TypeError)."""
    levels = {"mrp": None, "daily_poc": 83500, "weekly_poc": None}
    tp, reason = _calc_tp("long", 82000, levels)
    assert tp == 83500
    assert reason == "Daily POC"
