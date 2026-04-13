"""
Unit tests for btc_agent/scanner/oi.py

Uses mocked ccxt responses so no real exchange connection is needed.
Verifies aggregation, delta calculation, threshold detection, RSI, and display modes.
"""
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from btc_agent.scanner.oi import (
    _fetch_source,
    _aggregate_oi,
    _rsi,
    _fmt_value,
    _fmt_delta,
)


BTC_PRICE = 80_000.0

# ── helpers ───────────────────────────────────────────────────────────────────

def _make_oi_rows(values: list[float], is_coin_margined: bool = False) -> list[dict]:
    """
    Build fake ccxt OI rows.
    is_coin_margined=False (linear): values are in BTC  → stored in openInterestAmount
    is_coin_margined=True  (inverse): values are in USD → stored in openInterestValue
    """
    base_ts = 1_700_000_000_000  # ms
    rows = []
    for i, v in enumerate(values):
        row: dict = {"timestamp": base_ts + i * 3_600_000}
        if is_coin_margined:
            row["openInterestValue"] = v
            row["openInterestAmount"] = v / BTC_PRICE
        else:
            row["openInterestAmount"] = v
            row["openInterestValue"] = v * BTC_PRICE
        rows.append(row)
    return rows


def _mock_exchange(rows: list[dict]) -> MagicMock:
    ex = MagicMock()
    ex.load_markets.return_value = {}
    ex.fetch_open_interest_history.return_value = rows
    return ex


# ── _fetch_source ─────────────────────────────────────────────────────────────

class TestFetchSource:
    def test_linear_uses_openinterestamount_as_btc(self):
        # Linear (oi_in_usd=False): openInterestAmount is BTC — returned as-is
        btc_values = [10.0, 11.0, 10.5]   # 10 BTC, 11 BTC, etc.
        rows = _make_oi_rows(btc_values, is_coin_margined=False)
        # Patch openInterestAmount to the BTC value explicitly
        for i, r in enumerate(rows):
            r["openInterestAmount"] = btc_values[i]
            r["openInterestValue"] = None   # not used for linear
        factory = lambda: _mock_exchange(rows)
        ts, arr = _fetch_source("test", factory, "BTC/USDT:USDT", False, BTC_PRICE)
        assert arr is not None
        np.testing.assert_allclose(arr, btc_values, rtol=1e-6)

    def test_inverse_divides_usd_by_price_to_get_btc(self):
        # Inverse (oi_in_usd=True): openInterestValue is USD → divide by price = BTC
        usd_values = [800_000_000.0, 810_000_000.0]   # $800M, $810M
        rows = _make_oi_rows(usd_values, is_coin_margined=True)
        for i, r in enumerate(rows):
            r["openInterestValue"] = usd_values[i]
        factory = lambda: _mock_exchange(rows)
        ts, arr = _fetch_source("test", factory, "BTC/USD:BTC", True, BTC_PRICE)
        assert arr is not None
        expected_btc = [v / BTC_PRICE for v in usd_values]
        np.testing.assert_allclose(arr, expected_btc, rtol=1e-6)

    def test_returns_none_on_not_supported(self):
        import ccxt
        factory = MagicMock(side_effect=ccxt.NotSupported)
        result = _fetch_source("test", factory, "BTC/X:X", False, BTC_PRICE)
        assert result is None

    def test_returns_none_on_bad_symbol(self):
        import ccxt
        ex = MagicMock()
        ex.load_markets.return_value = {}
        ex.fetch_open_interest_history.side_effect = ccxt.BadSymbol("bad")
        factory = lambda: ex
        result = _fetch_source("test", factory, "BAD/SYM", False, BTC_PRICE)
        assert result is None

    def test_returns_none_on_empty_rows(self):
        factory = lambda: _mock_exchange([])
        result = _fetch_source("test", factory, "BTC/USDT:USDT", False, BTC_PRICE)
        assert result is None

    def test_returns_none_on_generic_exception(self):
        ex = MagicMock()
        ex.load_markets.side_effect = RuntimeError("boom")
        factory = lambda: ex
        result = _fetch_source("test", factory, "BTC/USDT:USDT", False, BTC_PRICE)
        assert result is None


# ── _aggregate_oi ─────────────────────────────────────────────────────────────

class TestAggregateOI:
    def _patch_sources(self, source_values: list[list[float] | None]):
        """
        Patch _OI_SOURCES with N sources, each returning the given value list (or None).
        source_values: list where each entry is a list of USD OI values or None (failure).
        """
        fake_sources = []
        for i, vals in enumerate(source_values):
            if vals is None:
                factory = MagicMock(side_effect=Exception("fail"))
            else:
                rows = _make_oi_rows(vals)
                factory = lambda r=rows: _mock_exchange(r)
            fake_sources.append((f"src{i}", factory, "BTC/USDT:USDT", False))
        return fake_sources

    def test_single_source_sums_correctly(self):
        values = [1e9, 1.1e9, 1.2e9, 1.3e9, 1.4e9]
        sources = self._patch_sources([values])
        with patch("btc_agent.scanner.oi._OI_SOURCES", sources):
            ts, agg, ok = _aggregate_oi(BTC_PRICE)
        assert agg is not None
        assert ok == ["src0"]
        np.testing.assert_allclose(agg, values, rtol=1e-6)

    def test_two_sources_summed(self):
        a = [1e9, 1.1e9, 1.2e9]
        b = [0.5e9, 0.6e9, 0.7e9]
        sources = self._patch_sources([a, b])
        with patch("btc_agent.scanner.oi._OI_SOURCES", sources):
            ts, agg, ok = _aggregate_oi(BTC_PRICE)
        expected = [x + y for x, y in zip(a, b)]
        assert len(ok) == 2
        np.testing.assert_allclose(agg, expected, rtol=1e-6)

    def test_failed_source_contributes_zero(self):
        a = [1e9, 1.1e9, 1.2e9]
        sources = self._patch_sources([a, None])  # second source fails
        with patch("btc_agent.scanner.oi._OI_SOURCES", sources):
            ts, agg, ok = _aggregate_oi(BTC_PRICE)
        assert ok == ["src0"]
        np.testing.assert_allclose(agg, a, rtol=1e-6)

    def test_all_sources_fail_returns_none(self):
        sources = self._patch_sources([None, None, None])
        with patch("btc_agent.scanner.oi._OI_SOURCES", sources):
            ts, agg, ok = _aggregate_oi(BTC_PRICE)
        assert agg is None
        assert ok == []

    def test_aligns_on_common_timestamps(self):
        # Source A has bars at t=0,1,2,3 (4 bars); source B has t=1,2,3 (3 bars).
        # Intersection = t=1,2,3 → only those 3 bars are summed.
        base_ts = 1_700_000_000_000  # ms
        step = 3_600_000

        rows_a = [
            {"timestamp": base_ts + i * step, "openInterestAmount": float(i + 1), "openInterestValue": None}
            for i in range(4)
        ]
        rows_b = [
            {"timestamp": base_ts + (i + 1) * step, "openInterestAmount": float(i + 10), "openInterestValue": None}
            for i in range(3)
        ]

        ex_a = MagicMock()
        ex_a.load_markets.return_value = {}
        ex_a.fetch_open_interest_history.return_value = rows_a

        ex_b = MagicMock()
        ex_b.load_markets.return_value = {}
        ex_b.fetch_open_interest_history.return_value = rows_b

        sources = [
            ("srcA", lambda: ex_a, "BTC/USDT:USDT", False),
            ("srcB", lambda: ex_b, "BTC/USDT:USDT", False),
        ]
        with patch("btc_agent.scanner.oi._OI_SOURCES", sources):
            ts, agg, ok = _aggregate_oi(BTC_PRICE)

        # Common timestamps: base_ts+1*step, base_ts+2*step, base_ts+3*step
        assert len(agg) == 3
        # Values: A[1]+B[0]=2+10=12, A[2]+B[1]=3+11=14, A[3]+B[2]=4+12=16
        np.testing.assert_allclose(agg, [12.0, 14.0, 16.0], rtol=1e-6)


# ── delta and threshold ───────────────────────────────────────────────────────

class TestDeltaAndThreshold:
    def test_delta_is_diff_of_agg(self):
        agg = np.array([10e9, 10.1e9, 9.9e9, 10.3e9])
        deltas = np.diff(agg)
        assert deltas[0] == pytest.approx(0.1e9)
        assert deltas[1] == pytest.approx(-0.2e9)
        assert deltas[2] == pytest.approx(0.4e9)

    def test_large_oi_up_detected(self):
        # 300 small positive deltas → avg = 10M, thresh = 10M × 4 = 40M
        # last delta = 100M > 40M → large OI up
        pos_deltas = np.full(300, 10e6)
        neg_deltas = np.full(300, -10e6)
        mult = 4.0
        p_thresh = float(np.mean(pos_deltas)) * mult   # 40M
        n_thresh = float(np.mean(neg_deltas)) * mult   # -40M
        assert 100e6 > p_thresh    # large up
        assert -5e6 > n_thresh     # not large down

    def test_large_oi_down_detected(self):
        neg_deltas = np.full(300, -10e6)
        mult = 4.0
        n_thresh = float(np.mean(neg_deltas)) * mult   # -40M
        assert -100e6 < n_thresh   # large down


# ── RSI ───────────────────────────────────────────────────────────────────────

class TestRSI:
    def test_rsi_length_matches_input(self):
        series = np.linspace(100, 200, 50)
        result = _rsi(series, period=14)
        assert len(result) == len(series)

    def test_rsi_overbought_on_rising_series(self):
        # Steadily rising series → RSI should be high (overbought)
        series = np.linspace(100, 200, 50)
        result = _rsi(series, period=14)
        assert result[-1] > 70

    def test_rsi_oversold_on_falling_series(self):
        # Steadily falling series → RSI should be low (oversold)
        series = np.linspace(200, 100, 50)
        result = _rsi(series, period=14)
        assert result[-1] < 30

    def test_rsi_bounded_0_to_100(self):
        np.random.seed(42)
        series = np.cumsum(np.random.randn(100)) + 1000
        result = _rsi(series, period=14)
        valid = result[~np.isnan(result)]
        assert np.all(valid >= 0) and np.all(valid <= 100)

    def test_first_value_is_nan(self):
        series = np.linspace(100, 200, 30)
        result = _rsi(series, period=14)
        assert np.isnan(result[0])


# ── formatting ────────────────────────────────────────────────────────────────

class TestFormatting:
    def test_fmt_delta_positive_millions_usd(self):
        import btc_agent.config as cfg
        orig = cfg.OI_QUOTED_IN
        cfg.OI_QUOTED_IN = "USD"
        assert _fmt_delta(320e6) == "+$320M"
        cfg.OI_QUOTED_IN = orig

    def test_fmt_delta_negative_millions_usd(self):
        import btc_agent.config as cfg
        orig = cfg.OI_QUOTED_IN
        cfg.OI_QUOTED_IN = "USD"
        assert _fmt_delta(-410e6) == "-$410M"
        cfg.OI_QUOTED_IN = orig

    def test_fmt_delta_billions_usd(self):
        import btc_agent.config as cfg
        orig = cfg.OI_QUOTED_IN
        cfg.OI_QUOTED_IN = "USD"
        assert _fmt_delta(1.5e9) == "+$1.50B"
        cfg.OI_QUOTED_IN = orig

    def test_fmt_delta_coin_mode(self):
        import btc_agent.config as cfg
        orig = cfg.OI_QUOTED_IN
        cfg.OI_QUOTED_IN = "COIN"
        assert _fmt_delta(140.0) == "+140 BTC"
        assert _fmt_delta(-582.0) == "-582 BTC"
        cfg.OI_QUOTED_IN = orig

    def test_fmt_value_oi_usd(self):
        import btc_agent.config as cfg
        orig = cfg.OI_QUOTED_IN
        cfg.OI_QUOTED_IN = "USD"
        result = _fmt_value(28.4e9, "Open Interest", BTC_PRICE)
        cfg.OI_QUOTED_IN = orig
        assert "$28.400B" in result or "28.4" in result

    def test_fmt_value_rsi(self):
        result = _fmt_value(65.3, "Open Interest RSI", BTC_PRICE)
        assert "65.3" in result
