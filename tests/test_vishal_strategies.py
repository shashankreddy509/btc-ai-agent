"""Unit tests for Vishal Sir strategy detection functions."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from btc_agent.trading.vishal_strategies import (
    check_chaukepechauka,
    check_doubleprofit,
    check_escalator,
    check_highwinrate,
    check_pingpong,
    check_rainharv,
)

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc


def _sc(vishal_settings: dict, open_positions=None):
    return SimpleNamespace(
        settings={"vishal": vishal_settings},
        vishal_state={},
        open_positions=open_positions or [],
    )


def _ist(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=IST).astimezone(UTC)


# ── Ping Pong ─────────────────────────────────────────────────────────────────

class TestPingPong:
    S = {"pingpong_tf": "1h", "pingpong_tp": 400, "pingpong_sl": 200}

    def test_new_session_records_open_no_signal(self):
        sc = _sc(self.S)
        sigs = check_pingpong(sc, 75000.0, _ist(2026, 4, 26, 10, 0))
        assert sigs == []
        assert sc.vishal_state["pp_session_open"] == 75000.0

    def test_long_at_lower_band(self):
        sc = _sc(self.S)
        check_pingpong(sc, 75000.0, _ist(2026, 4, 26, 10, 0))
        sigs = check_pingpong(sc, 74800.0, _ist(2026, 4, 26, 10, 5))
        assert len(sigs) == 1
        sig = sigs[0]
        assert sig.direction == "long"
        assert sig.pattern == "Ping Pong"
        assert sig.sl_wick == 74600.0    # lower - sl_pts
        assert sig.custom_tp == 75200.0  # lower + tp_pts

    def test_short_at_upper_band(self):
        sc = _sc(self.S)
        check_pingpong(sc, 75000.0, _ist(2026, 4, 26, 10, 0))
        sigs = check_pingpong(sc, 75200.0, _ist(2026, 4, 26, 10, 5))
        assert len(sigs) == 1
        sig = sigs[0]
        assert sig.direction == "short"
        assert sig.sl_wick == 75400.0    # upper + sl_pts
        assert sig.custom_tp == 74800.0  # upper - tp_pts

    def test_long_does_not_fire_twice(self):
        sc = _sc(self.S)
        check_pingpong(sc, 75000.0, _ist(2026, 4, 26, 10, 0))
        check_pingpong(sc, 74800.0, _ist(2026, 4, 26, 10, 5))
        assert check_pingpong(sc, 74750.0, _ist(2026, 4, 26, 10, 10)) == []

    def test_new_session_resets_fired_flags(self):
        sc = _sc(self.S)
        check_pingpong(sc, 75000.0, _ist(2026, 4, 26, 10, 0))
        check_pingpong(sc, 74800.0, _ist(2026, 4, 26, 10, 5))
        sigs = check_pingpong(sc, 76000.0, _ist(2026, 4, 26, 11, 0))
        assert sigs == []
        assert sc.vishal_state["pp_session_open"] == 76000.0
        assert sc.vishal_state["pp_long_fired"] is False

    def test_4h_preset_applied(self):
        sc = _sc({"pingpong_tf": "4h"})
        check_pingpong(sc, 75000.0, _ist(2026, 4, 26, 1, 30))
        sigs = check_pingpong(sc, 74500.0, _ist(2026, 4, 26, 1, 35))  # lower = 75000-500
        assert len(sigs) == 1
        assert sigs[0].direction == "long"
        assert sigs[0].sl_wick == 74000.0    # 74500 - 500
        assert sigs[0].custom_tp == 75500.0  # 74500 + 1000


# ── Escalator ─────────────────────────────────────────────────────────────────

class TestEscalator:
    S = {"pingpong_tf": "1h", "pingpong_sl": 200, "escalator_trigger": 200, "escalator_max_sl": 3}

    def _sc_with_pp(self, pp_open=75000.0):
        sc = _sc(self.S)
        sc.vishal_state["pp_session_key"]  = "2026-04-26_1000"
        sc.vishal_state["pp_session_open"] = pp_open
        return sc

    def test_no_pp_session_returns_empty(self):
        assert check_escalator(_sc(self.S), 75600.0, _ist(2026, 4, 26, 10, 5)) == []

    def test_baselines_derived_from_pp_session(self):
        sc = self._sc_with_pp(75000.0)
        check_escalator(sc, 74000.0, _ist(2026, 4, 26, 10, 5))
        assert sc.vishal_state["esc_long_baseline"]  == 75400.0  # 75000 + 2*200
        assert sc.vishal_state["esc_short_baseline"] == 74600.0  # 75000 - 2*200

    def test_long_entry_above_long_baseline_plus_trigger(self):
        sc = self._sc_with_pp(75000.0)
        sigs = check_escalator(sc, 75600.0, _ist(2026, 4, 26, 10, 5))  # 75400+200
        assert len(sigs) == 1
        assert sigs[0].direction == "long"
        assert sigs[0].sl_wick == 75400.0
        assert sc.vishal_state["esc_active"] is True

    def test_short_entry_below_short_baseline_minus_trigger(self):
        sc = self._sc_with_pp(75000.0)
        sigs = check_escalator(sc, 74400.0, _ist(2026, 4, 26, 10, 5))  # 74600-200
        assert len(sigs) == 1
        assert sigs[0].direction == "short"
        assert sigs[0].sl_wick == 74600.0

    def test_trailing_sl_updates_open_position(self):
        sc = self._sc_with_pp(75000.0)
        sigs = check_escalator(sc, 75600.0, _ist(2026, 4, 26, 10, 5))
        pos = SimpleNamespace(signal_id=sigs[0].id, status="open",
                              sl_wick=75400.0, sl_body=75400.0)
        sc.open_positions = [pos]
        check_escalator(sc, 75800.0, _ist(2026, 4, 26, 10, 10))
        assert pos.sl_wick == 75600.0
        assert pos.sl_body == 75600.0
        assert sc.vishal_state["esc_sl"] == 75600.0

    def test_sl_hit_increments_consec_and_resets_baseline(self):
        sc = self._sc_with_pp(75000.0)
        check_escalator(sc, 75600.0, _ist(2026, 4, 26, 10, 5))
        sc.vishal_state["esc_sl"] = 75400.0
        sc.open_positions = []  # position closed at SL
        check_escalator(sc, 75500.0, _ist(2026, 4, 26, 10, 10))
        assert sc.vishal_state["esc_consec_sl"] == 1
        assert sc.vishal_state["esc_long_baseline"]  == 75400.0
        assert sc.vishal_state["esc_short_baseline"] == 75400.0
        assert sc.vishal_state["esc_active"] is False

    def test_stops_at_max_consecutive_sl(self):
        sc = self._sc_with_pp(75000.0)
        check_escalator(sc, 74000.0, _ist(2026, 4, 26, 10, 5))  # init baselines
        sc.vishal_state["esc_consec_sl"] = 3
        assert check_escalator(sc, 75600.0, _ist(2026, 4, 26, 10, 10)) == []

    def test_new_pp_session_resets_escalator(self):
        sc = self._sc_with_pp(75000.0)
        check_escalator(sc, 74000.0, _ist(2026, 4, 26, 10, 5))
        sc.vishal_state["esc_consec_sl"] = 2
        sc.vishal_state["pp_session_key"]  = "2026-04-26_1100"
        sc.vishal_state["pp_session_open"] = 76000.0
        check_escalator(sc, 74000.0, _ist(2026, 4, 26, 11, 5))
        assert sc.vishal_state["esc_consec_sl"] == 0
        assert sc.vishal_state["esc_long_baseline"] == 76400.0  # 76000 + 2*200


# ── High Win Rate ─────────────────────────────────────────────────────────────

class TestHighWinRate:
    S = {"hwt_sz": 76000.0, "hwt_dz": 74000.0, "hwt_target": 450, "hwt_sl": 100}

    def test_no_zones_returns_empty(self):
        assert check_highwinrate(_sc({}), 75000.0, datetime.now(UTC)) == []

    def test_long_above_sz(self):
        sc = _sc(self.S)
        sigs = check_highwinrate(sc, 76100.0, datetime.now(UTC))
        assert len(sigs) == 1
        assert sigs[0].direction == "long"

    def test_short_below_dz(self):
        sc = _sc(self.S)
        sigs = check_highwinrate(sc, 73900.0, datetime.now(UTC))
        assert len(sigs) == 1
        assert sigs[0].direction == "short"

    def test_no_signal_inside_zone(self):
        assert check_highwinrate(_sc(self.S), 75000.0, datetime.now(UTC)) == []

    def test_long_does_not_fire_twice(self):
        sc = _sc(self.S)
        check_highwinrate(sc, 76100.0, datetime.now(UTC))
        assert check_highwinrate(sc, 76200.0, datetime.now(UTC)) == []

    def test_sl_and_tp_values(self):
        sc = _sc(self.S)
        sig = check_highwinrate(sc, 76100.0, datetime.now(UTC))[0]
        assert sig.sl_wick   == pytest.approx(76000.0)   # price - sl_pts
        assert sig.custom_tp == pytest.approx(76550.0)   # price + target


# ── Chauke pe Chauka ──────────────────────────────────────────────────────────

class TestChaukepeChauka:
    S = {"cpc_sz": 76000.0, "cpc_dz": 74000.0, "cpc_target": 1950}

    def test_no_zones_returns_empty(self):
        assert check_chaukepechauka(_sc({}), 75000.0, datetime.now(UTC)) == []

    def test_long_within_tolerance_of_dz(self):
        sc = _sc(self.S)
        sigs = check_chaukepechauka(sc, 74030.0, datetime.now(UTC))
        assert len(sigs) == 1
        assert sigs[0].direction == "long"

    def test_short_within_tolerance_of_sz(self):
        sc = _sc(self.S)
        sigs = check_chaukepechauka(sc, 75980.0, datetime.now(UTC))
        assert len(sigs) == 1
        assert sigs[0].direction == "short"

    def test_no_signal_outside_tolerance(self):
        assert check_chaukepechauka(_sc(self.S), 74100.0, datetime.now(UTC)) == []

    def test_does_not_fire_twice_same_side(self):
        sc = _sc(self.S)
        check_chaukepechauka(sc, 74030.0, datetime.now(UTC))
        assert check_chaukepechauka(sc, 74010.0, datetime.now(UTC)) == []

    def test_sl_beyond_zone(self):
        sc = _sc(self.S)
        sig = check_chaukepechauka(sc, 74030.0, datetime.now(UTC))[0]
        assert sig.sl_wick == pytest.approx(73900.0)  # dz - 100


# ── Rain Harvesting ───────────────────────────────────────────────────────────

class TestRainHarvesting:
    S = {"rain_sz": 76000.0, "rain_dz": 74000.0, "rain_tp": 500}

    def _sunday_22h(self):
        return _ist(2026, 4, 26, 22, 5)  # April 26 2026 is a Sunday

    def test_wrong_day_returns_empty(self):
        assert check_rainharv(_sc(self.S), 76100.0, _ist(2026, 4, 27, 22, 5)) == []

    def test_wrong_time_returns_empty(self):
        assert check_rainharv(_sc(self.S), 76100.0, _ist(2026, 4, 26, 20, 0)) == []

    def test_after_window_returns_empty(self):
        assert check_rainharv(_sc(self.S), 76100.0, _ist(2026, 4, 26, 22, 31)) == []

    def test_long_above_sz_on_sunday(self):
        sc = _sc(self.S)
        sigs = check_rainharv(sc, 76100.0, self._sunday_22h())
        assert len(sigs) == 1
        assert sigs[0].direction == "long"

    def test_short_below_dz_on_sunday(self):
        sc = _sc(self.S)
        sigs = check_rainharv(sc, 73900.0, self._sunday_22h())
        assert len(sigs) == 1
        assert sigs[0].direction == "short"

    def test_does_not_fire_twice_same_sunday(self):
        sc = _sc(self.S)
        check_rainharv(sc, 76100.0, self._sunday_22h())
        assert check_rainharv(sc, 76200.0, self._sunday_22h()) == []

    def test_no_zones_returns_empty(self):
        assert check_rainharv(_sc({}), 76100.0, self._sunday_22h()) == []


# ── Double Profit ─────────────────────────────────────────────────────────────

class TestDoubleProfit:
    S = {"dp_sz": 76000.0, "dp_dz": 74000.0}
    # zone_dist=2000, tolerance=min(2000*0.05, 100)=100

    def test_no_zones_returns_empty(self):
        assert check_doubleprofit(_sc({}), 75000.0, datetime.now(UTC)) == []

    def test_long_at_dz_within_tolerance(self):
        sc = _sc(self.S)
        sigs = check_doubleprofit(sc, 74050.0, datetime.now(UTC))
        assert len(sigs) == 1
        assert sigs[0].direction == "long"
        assert sigs[0].custom_tp == 76000.0  # TP = sz

    def test_short_at_sz_within_tolerance(self):
        sc = _sc(self.S)
        sigs = check_doubleprofit(sc, 75950.0, datetime.now(UTC))
        assert len(sigs) == 1
        assert sigs[0].direction == "short"
        assert sigs[0].custom_tp == 74000.0  # TP = dz

    def test_no_signal_outside_tolerance(self):
        assert check_doubleprofit(_sc(self.S), 74200.0, datetime.now(UTC)) == []

    def test_does_not_fire_twice_same_side(self):
        sc = _sc(self.S)
        check_doubleprofit(sc, 74050.0, datetime.now(UTC))
        assert check_doubleprofit(sc, 74030.0, datetime.now(UTC)) == []

    def test_sl_is_10pct_zone_dist_beyond_dz(self):
        sc = _sc(self.S)
        sig = check_doubleprofit(sc, 74050.0, datetime.now(UTC))[0]
        assert sig.sl_wick == pytest.approx(73800.0)  # dz - 2000*0.1
