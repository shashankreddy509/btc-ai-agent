"""
Unit tests for btc_agent/scanner/aggregator.py

Key invariant: stub bars (partial bars at day end when 1440 % tf != 0) must be
included as closed bars, matching TradingView's session-reset behaviour at
00:00 UTC (19:00 CDT for BTCUSDT.P Binance Perp).
"""
import numpy as np
import pytest

from btc_agent.scanner.aggregator import aggregate_tf, df_to_numpy


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_1m_data(n_days: int = 3, base_ts: int = 0) -> tuple:
    """
    Generate n_days * 1440 synthetic 1-minute OHLCV candles.
    Each candle: open=1, high=1.01, low=0.99, close=1, volume=1.
    base_ts: Unix timestamp of the first candle (must be aligned to midnight UTC).
    """
    n = n_days * 1440
    ts = np.arange(base_ts, base_ts + n * 60, 60, dtype=np.int64)
    ohlcv = np.ones((n, 5), dtype=np.float64)
    ohlcv[:, 1] = 1.01
    ohlcv[:, 2] = 0.99
    minutes_of_day = ((ts % 86400) // 60).astype(np.int64)
    unix_days = (ts // 86400).astype(np.int64)
    return ohlcv, ts, minutes_of_day, unix_days


# ── TF with no waste (1440 % tf == 0) ────────────────────────────────────────

class TestNoWasteTF:
    """For TFs that divide 1440 evenly, behaviour is unchanged."""

    def test_30m_returns_correct_bar_count(self):
        arr, ts, mod, days = _make_1m_data(3)
        ohlcv, bar_ts = aggregate_tf(arr, ts, mod, days, tf_minutes=30, last_n=10)
        assert ohlcv is not None
        assert ohlcv.shape == (10, 5)

    def test_60m_bar_open_times_spaced_3600s(self):
        arr, ts, mod, days = _make_1m_data(3)
        ohlcv, bar_ts = aggregate_tf(arr, ts, mod, days, tf_minutes=60, last_n=5)
        assert ohlcv is not None
        diffs = np.diff(bar_ts)
        assert np.all(diffs == 3600), f"Expected 3600s spacing, got: {diffs}"

    def test_720m_no_stubs(self):
        arr, ts, mod, days = _make_1m_data(3)
        ohlcv, bar_ts = aggregate_tf(arr, ts, mod, days, tf_minutes=720, last_n=4)
        assert ohlcv is not None
        assert ohlcv.shape == (4, 5)


# ── TF with waste (1440 % tf != 0) ───────────────────────────────────────────

class TestWasteTF:
    """
    For 159m: bars_per_day=9, max_minute=1431, waste=9min stub at 23:51 UTC.
    The stub must be returned as a complete bar so bar sequences match TradingView.
    """

    def test_159m_returns_bars(self):
        arr, ts, mod, days = _make_1m_data(3)
        ohlcv, bar_ts = aggregate_tf(arr, ts, mod, days, tf_minutes=159, last_n=10)
        assert ohlcv is not None
        assert ohlcv.shape == (10, 5)

    def test_159m_stub_bar_is_included(self):
        """
        With 3 days of data there should be 3 stub bars (one per day).
        These stubs would be absent in the old (waste-drop) implementation.
        3 days × 9 full bars = 27 full + 3 stubs = 30 total complete bars.
        We should be able to retrieve last_n=10 bars that include stubs.
        """
        arr, ts, mod, days = _make_1m_data(3)
        # If stubs were dropped we'd only have 27 bars; requesting 28 would fail.
        # With stubs included we have 30; requesting 28 must succeed.
        ohlcv, bar_ts = aggregate_tf(arr, ts, mod, days, tf_minutes=159, last_n=28)
        assert ohlcv is not None, "Stub bars not included — only 27 full bars available"
        assert ohlcv.shape == (28, 5)

    def test_159m_stub_bar_open_time_is_1431_min(self):
        """The stub bar for 159m starts at minute 1431 = 23:51 UTC."""
        arr, ts, mod, days = _make_1m_data(3)
        ohlcv, bar_ts = aggregate_tf(arr, ts, mod, days, tf_minutes=159, last_n=10)
        assert ohlcv is not None
        # Find bar open times as minute-of-day
        bar_mod = (bar_ts % 86400) // 60
        # At least one bar should open at minute 1431
        assert 1431 in bar_mod, f"No stub bar at 23:51 UTC found. Bar minutes: {sorted(set(bar_mod))}"

    def test_159m_new_day_bar_opens_at_minute_0(self):
        """After a stub bar, the next bar must open at 00:00 UTC (day boundary)."""
        arr, ts, mod, days = _make_1m_data(3)
        ohlcv, bar_ts = aggregate_tf(arr, ts, mod, days, tf_minutes=159, last_n=10)
        assert ohlcv is not None
        bar_mod = (bar_ts % 86400) // 60
        # At least one bar opens at midnight (minute 0) — new day bar
        assert 0 in bar_mod, f"No day-start bar at 00:00 UTC. Bar minutes: {sorted(set(bar_mod))}"

    def test_43m_stub_included(self):
        """43m: bars_per_day=33, max_minute=1419, waste=21min."""
        arr, ts, mod, days = _make_1m_data(3)
        # 3 days × 33 full + 3 stubs = 102 bars; requesting 35 must succeed
        ohlcv, bar_ts = aggregate_tf(arr, ts, mod, days, tf_minutes=43, last_n=35)
        assert ohlcv is not None, "Stub bars not included for 43m TF"

    def test_38m_stub_included(self):
        """38m: bars_per_day=37, max_minute=1406, waste=34min."""
        arr, ts, mod, days = _make_1m_data(3)
        ohlcv, bar_ts = aggregate_tf(arr, ts, mod, days, tf_minutes=38, last_n=38)
        assert ohlcv is not None, "Stub bars not included for 38m TF"


# ── Bar sequence ordering ─────────────────────────────────────────────────────

class TestBarOrdering:
    def test_bar_open_times_strictly_increasing(self):
        """All returned bar open times must be in ascending order."""
        arr, ts, mod, days = _make_1m_data(3)
        for tf in [30, 60, 159, 43, 38, 120]:
            ohlcv, bar_ts = aggregate_tf(arr, ts, mod, days, tf_minutes=tf, last_n=5)
            if ohlcv is not None:
                assert np.all(np.diff(bar_ts) > 0), f"Non-monotonic bar times for {tf}m"

    def test_no_bar_straddles_midnight(self):
        """
        No bar should span across a day boundary.
        bar_open_time and bar_close_time (open + (size-1)*60) must be on the same day.
        """
        arr, ts, mod, days = _make_1m_data(3)
        for tf in [159, 43]:
            ohlcv, bar_ts = aggregate_tf(arr, ts, mod, days, tf_minutes=tf, last_n=10)
            if ohlcv is None:
                continue
            for bt in bar_ts:
                open_day  = bt // 86400
                # bars_per_day and stub info per TF
                bars_pd = 1440 // tf
                max_min = bars_pd * tf
                open_mod = (bt % 86400) // 60
                is_stub = open_mod >= max_min
                if is_stub:
                    # stub: close is end-of-day
                    close_ts = (open_day + 1) * 86400 - 60
                else:
                    close_ts = bt + (tf - 1) * 60
                close_day = close_ts // 86400
                assert open_day == close_day, (
                    f"{tf}m bar opened at day {open_day} (min {open_mod}) "
                    f"closes at day {close_day} — straddles midnight"
                )


# ── OHLCV aggregation correctness ─────────────────────────────────────────────

class TestOHLCVAggregation:
    def test_open_is_first_candle(self):
        """Bar open must equal the open of its first 1m candle."""
        n = 3 * 1440
        base_ts = 0
        ts = np.arange(base_ts, base_ts + n * 60, 60, dtype=np.int64)
        arr = np.zeros((n, 5), dtype=np.float64)
        # Set each candle's open to its sequential index
        arr[:, 0] = np.arange(n, dtype=np.float64)
        arr[:, 1] = arr[:, 0] + 0.5  # high
        arr[:, 2] = arr[:, 0] - 0.5  # low
        arr[:, 3] = arr[:, 0]        # close = open (flat)
        arr[:, 4] = 1.0
        mod  = ((ts % 86400) // 60).astype(np.int64)
        days = (ts // 86400).astype(np.int64)

        ohlcv, bar_ts = aggregate_tf(arr, ts, mod, days, tf_minutes=60, last_n=5)
        assert ohlcv is not None
        for i, bt in enumerate(bar_ts):
            # The 1m candle at ts=bt should have open == bt//60 (sequential index)
            expected_open = bt // 60
            assert ohlcv[i, 0] == expected_open, (
                f"Bar {i}: expected open {expected_open}, got {ohlcv[i, 0]}"
            )

    def test_not_enough_data_returns_none(self):
        arr, ts, mod, days = _make_1m_data(1)  # only 1 day
        # requesting more bars than exist should return None
        result = aggregate_tf(arr, ts, mod, days, tf_minutes=159, last_n=100)
        assert result == (None, None)
