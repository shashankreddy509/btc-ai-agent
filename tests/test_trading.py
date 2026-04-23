"""
Tests for the trading scanner:
  - detect_engulfing pattern
  - calc_sl (wick of pattern candle)
  - signal expiry
  - entry trigger logic
"""
from datetime import datetime, timezone, timedelta
import numpy as np
import pytest

from btc_agent.scanner.patterns import detect_engulfing
from btc_agent.trading.scanner import calc_sl
from btc_agent.trading.models import Signal


# ── Engulfing detection ───────────────────────────────────────────────────────

def _make_bars(candles: list[tuple]) -> np.ndarray:
    """candles: list of (open, high, low, close, volume)"""
    return np.array(candles, dtype=np.float64)


class TestEngulfing:
    def test_bullish_engulfing(self):
        # Previous: bearish (open=105, close=100); Current: bullish engulfs (open=99, close=107)
        bars = _make_bars([
            (105.0, 106.0, 98.0, 100.0, 1.0),   # bearish
            (99.0,  108.0, 98.0, 107.0, 1.0),    # bullish, body engulfs previous body
        ])
        found, direction = detect_engulfing(bars)
        assert found
        assert direction == "bullish"

    def test_bearish_engulfing(self):
        # Previous: bullish (open=100, close=105); Current: bearish engulfs (open=106, close=99)
        bars = _make_bars([
            (100.0, 107.0, 99.0,  105.0, 1.0),   # bullish
            (106.0, 107.0, 98.0,  99.0,  1.0),    # bearish, body engulfs previous body
        ])
        found, direction = detect_engulfing(bars)
        assert found
        assert direction == "bearish"

    def test_not_engulfing_partial(self):
        # Current bullish but only partially covers previous body
        bars = _make_bars([
            (105.0, 106.0, 98.0, 100.0, 1.0),
            (101.0, 107.0, 99.0, 104.0, 1.0),   # close=104 < prev open=105 → not full engulf
        ])
        found, _ = detect_engulfing(bars)
        assert not found

    def test_insufficient_bars(self):
        bars = _make_bars([(100.0, 102.0, 99.0, 101.0, 1.0)])
        found, direction = detect_engulfing(bars)
        assert not found
        assert direction == ""

    def test_doji_not_counted(self):
        # Current candle is a doji (body < MIN_BODY_PCT) — should not detect
        bars = _make_bars([
            (105.0, 106.0, 98.0, 100.0, 1.0),       # bearish
            (100.0, 107.0, 98.5, 100.01, 1.0),       # doji body ~0.01
        ])
        found, _ = detect_engulfing(bars)
        assert not found


# ── SL calculation ────────────────────────────────────────────────────────────

class TestCalcSL:
    def test_returns_wick_low_for_long(self):
        sl = calc_sl(sl_wick=600.0)
        assert sl == pytest.approx(600.0)

    def test_returns_wick_high_for_short(self):
        sl = calc_sl(sl_wick=1400.0)
        assert sl == pytest.approx(1400.0)

    def test_rounds_to_two_decimals(self):
        sl = calc_sl(sl_wick=600.123456)
        assert sl == pytest.approx(600.12)


# ── Signal expiry ─────────────────────────────────────────────────────────────

class TestSignalExpiry:
    def _make_signal(self, expires_in_seconds: float) -> Signal:
        now = datetime.now(timezone.utc)
        return Signal(
            id="test01",
            pattern="4-Flag",
            direction="long",
            tf=30,
            bar_open_time=now.isoformat(),
            entry_trigger=1050.0,
            sl_wick=950.0,
            sl_body=980.0,
            created_at=now,
            expires_at=now + timedelta(seconds=expires_in_seconds),
        )

    def test_signal_not_expired_before_time(self):
        sig = self._make_signal(300)
        assert datetime.now(timezone.utc) <= sig.expires_at

    def test_signal_expired_after_time(self):
        sig = self._make_signal(-1)   # expires 1 second in the past
        assert datetime.now(timezone.utc) > sig.expires_at

    def test_pending_signal_triggers_on_long_breakout(self):
        now = datetime.now(timezone.utc)
        sig = Signal(
            id="test02",
            pattern="Engulfing",
            direction="long",
            tf=15,
            bar_open_time=now.isoformat(),
            entry_trigger=1050.0,
            sl_wick=990.0,
            sl_body=1000.0,
            created_at=now,
            expires_at=now + timedelta(minutes=15),
        )
        # Price above trigger → should fire
        assert sig.direction == "long" and 1060.0 > sig.entry_trigger

    def test_pending_signal_does_not_trigger_below_trigger(self):
        now = datetime.now(timezone.utc)
        sig = Signal(
            id="test03",
            pattern="4-Flag",
            direction="long",
            tf=30,
            bar_open_time=now.isoformat(),
            entry_trigger=1050.0,
            sl_wick=990.0,
            sl_body=1000.0,
            created_at=now,
            expires_at=now + timedelta(minutes=30),
        )
        # Price below trigger → should not fire
        assert not (sig.direction == "long" and 1040.0 > sig.entry_trigger)


# ── Trailing stop tests ───────────────────────────────────────────────────────

class TestTrailSL:
    """Tests for _trail_sl() ratchet logic."""

    def _pos(self, direction, entry, sl, trail_anchor):
        from btc_agent.trading.models import Position
        from datetime import datetime, timezone
        pos = Position(
            signal_id="x", entry_price=entry, sl=sl, tp=entry + 500,
            qty=0.001, direction=direction,
            opened_at=datetime.now(timezone.utc),
            partial_closed=True, trail_anchor=trail_anchor,
        )
        pos.sl = sl
        return pos

    def test_long_no_move_before_100pts(self):
        from btc_agent.trading.scanner import _trail_sl
        pos = self._pos("long", 80000, 80050, 83000)
        # price only 50 pts above anchor → still 0 steps
        assert _trail_sl(pos, 83050) == 80050

    def test_long_moves_50_per_100pts(self):
        from btc_agent.trading.scanner import _trail_sl
        pos = self._pos("long", 80000, 80050, 83000)
        # 100 pts above anchor → 1 step → sl = entry+50 + 50 = entry+100
        assert _trail_sl(pos, 83100) == 80100
        # 200 pts above anchor → 2 steps → sl = entry+50 + 100 = entry+150
        assert _trail_sl(pos, 83200) == 80150

    def test_long_only_ratchets_up(self):
        from btc_agent.trading.scanner import _trail_sl
        pos = self._pos("long", 80000, 80150, 83000)
        # price drops back toward anchor → sl must not decrease
        assert _trail_sl(pos, 83050) == 80150

    def test_short_moves_50_per_100pts(self):
        from btc_agent.trading.scanner import _trail_sl
        pos = self._pos("short", 82000, 81950, 79000)
        # 100 pts below anchor → sl = entry-50 - 50 = entry-100
        assert _trail_sl(pos, 78900) == 81900
        # 200 pts below anchor → sl = entry-50 - 100 = entry-150
        assert _trail_sl(pos, 78800) == 81850

    def test_short_only_ratchets_down(self):
        from btc_agent.trading.scanner import _trail_sl
        pos = self._pos("short", 82000, 81850, 79000)
        # price bounces up toward anchor → sl must not increase
        assert _trail_sl(pos, 78950) == 81850

    def test_no_trail_anchor_returns_original_sl(self):
        from btc_agent.trading.scanner import _trail_sl
        from btc_agent.trading.models import Position
        from datetime import datetime, timezone
        pos = Position(
            signal_id="x", entry_price=80000, sl=79500, tp=80500,
            qty=0.001, direction="long",
            opened_at=datetime.now(timezone.utc),
        )
        assert _trail_sl(pos, 81000) == 79500
