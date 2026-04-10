"""
Unit tests for btc_agent/scanner/patterns.py

Bar array shape: (N, 5) — [open, high, low, close, volume], oldest first.
"""
import numpy as np
import pytest

from btc_agent.scanner.patterns import detect_4flag, detect_morning_star, detect_evening_star


# ── helpers ───────────────────────────────────────────────────────────────────

def bar(open_, close, high=None, low=None):
    """Build a single OHLCV row. High/low default to outer bounds of body."""
    h = high if high is not None else max(open_, close) * 1.001
    l = low  if low  is not None else min(open_, close) * 0.999
    return [open_, h, l, close, 1000.0]


def bars(*rows):
    return np.array(rows, dtype=np.float64)


# ── detect_4flag ──────────────────────────────────────────────────────────────

class TestDetect4Flag:
    def test_valid_green_red_green_red(self):
        # Equal-body alternating G-R-G-R
        b = bars(
            bar(100, 110),  # green
            bar(110, 100),  # red
            bar(100, 110),  # green
            bar(110, 100),  # red
        )
        assert detect_4flag(b) == True

    def test_valid_red_green_red_green(self):
        b = bars(
            bar(110, 100),  # red
            bar(100, 110),  # green
            bar(110, 100),  # red
            bar(100, 110),  # green
        )
        assert detect_4flag(b) == True

    def test_non_alternating_colors(self):
        b = bars(
            bar(100, 110),  # green
            bar(100, 110),  # green  ← breaks alternation
            bar(110, 100),  # red
            bar(100, 110),  # green
        )
        assert detect_4flag(b) == False

    def test_body_size_too_varied(self):
        # Last candle body is 10x larger than others → fails tolerance
        b = bars(
            bar(100, 110),   # body=10
            bar(110, 100),   # body=10
            bar(100, 110),   # body=10
            bar(200, 100),   # body=100  ← way too large
        )
        assert detect_4flag(b) == False

    def test_doji_excluded(self):
        # Doji (open == close) breaks strict color requirement
        b = bars(
            bar(100, 110),  # green
            bar(105, 105),  # doji (not red)
            bar(100, 110),  # green
            bar(110, 100),  # red
        )
        assert detect_4flag(b) == False

    def test_too_few_bars(self):
        b = bars(bar(100, 110), bar(110, 100), bar(100, 110))
        assert detect_4flag(b) == False

    def test_uses_last_4_bars(self):
        # Prepend a bad bar — function should ignore it and use last 4
        b = bars(
            bar(100, 110),  # ignored (5th from end)
            bar(100, 110),  # green
            bar(110, 100),  # red
            bar(100, 110),  # green
            bar(110, 100),  # red
        )
        assert detect_4flag(b) == True


# ── detect_morning_star ───────────────────────────────────────────────────────

class TestDetectMorningStar:
    def _make(self, c2_close):
        """Build a morning star with controllable candle-2 close."""
        return bars(
            bar(110, 90),   # large bearish: o=110 c=90, body=20
            bar(89, 88),    # small star:    body=1 < 30% of 20
            bar(89, c2_close),  # bullish close varies
        )

    def test_valid_pattern(self):
        # Candle 2 closes above midpoint of candle 0 body (midpoint=100)
        assert detect_morning_star(self._make(102)) == True

    def test_candle2_below_midpoint(self):
        assert detect_morning_star(self._make(98)) == False

    def test_candle2_exactly_at_midpoint(self):
        # Midpoint = (110+90)/2 = 100; >= 100 should pass
        assert detect_morning_star(self._make(100)) == True

    def test_candle0_not_bearish(self):
        b = bars(
            bar(90, 110),   # bullish (not bearish)
            bar(89, 88),
            bar(89, 102),
        )
        assert detect_morning_star(b) == False

    def test_star_too_large(self):
        b = bars(
            bar(110, 90),   # body=20
            bar(100, 95),   # body=5 → 5 >= 30% of 20 (6) → actually 5 < 6, passes
            bar(89, 102),
        )
        # star body=5, threshold=0.30*20=6 → 5 < 6 → star OK → should pass
        assert detect_morning_star(b) == True

    def test_star_exactly_at_threshold(self):
        b = bars(
            bar(110, 90),   # body=20
            bar(100, 94),   # body=6 = 30% of 20 → fails (>= not <)
            bar(89, 102),
        )
        assert detect_morning_star(b) == False

    def test_candle2_bearish(self):
        b = bars(
            bar(110, 90),
            bar(89, 88),
            bar(102, 95),   # bearish
        )
        assert detect_morning_star(b) == False

    def test_too_few_bars(self):
        b = bars(bar(110, 90), bar(89, 88))
        assert detect_morning_star(b) == False

    def test_doji_candle0_filtered(self):
        # Candle 0 body too small relative to price → filtered by _MIN_BODY_PCT
        b = bars(
            bar(100.01, 100.00),  # body ~ 0.001/100 = 0.001% << 0.3%
            bar(99, 98),
            bar(99, 102),
        )
        assert detect_morning_star(b) == False


# ── detect_evening_star ───────────────────────────────────────────────────────

class TestDetectEveningStar:
    def _make(self, c2_close):
        """Build an evening star with controllable candle-2 close."""
        return bars(
            bar(90, 110),   # large bullish: o=90 c=110, body=20
            bar(111, 112),  # small star:    body=1 < 30% of 20
            bar(112, c2_close),  # bearish close varies
        )

    def test_valid_pattern(self):
        # Midpoint = (90+110)/2 = 100; candle 2 must close below 100
        assert detect_evening_star(self._make(98)) == True

    def test_candle2_above_midpoint(self):
        assert detect_evening_star(self._make(102)) == False

    def test_candle2_exactly_at_midpoint(self):
        # <= 100 should pass
        assert detect_evening_star(self._make(100)) == True

    def test_candle0_not_bullish(self):
        b = bars(
            bar(110, 90),   # bearish
            bar(111, 112),
            bar(112, 98),
        )
        assert detect_evening_star(b) == False

    def test_candle2_bullish(self):
        b = bars(
            bar(90, 110),
            bar(111, 112),
            bar(95, 105),   # bullish
        )
        assert detect_evening_star(b) == False

    def test_too_few_bars(self):
        b = bars(bar(90, 110), bar(111, 112))
        assert detect_evening_star(b) == False

    def test_star_too_large(self):
        b = bars(
            bar(90, 110),   # body=20
            bar(110, 104),  # body=6 = 30% of 20 → fails threshold
            bar(112, 98),
        )
        assert detect_evening_star(b) == False
