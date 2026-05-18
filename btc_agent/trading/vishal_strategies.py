"""
Vishal Sir Strategy detection functions.
Called each tick from run_trading_scanner via _tick_vishal().
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from btc_agent.trading.models import Signal

IST = ZoneInfo("Asia/Kolkata")

# Session open times per TF in IST (hour, minute)
_PP_SESSION_STARTS: dict[str, list[tuple[int, int]]] = {
    "1h":  [(h, 0) for h in range(24)],
    "4h":  [(1, 30), (5, 30), (9, 30), (13, 30), (17, 30), (21, 30)],
    "6h":  [(0, 0), (6, 0), (12, 0), (18, 0)],
    "12h": [(0, 0), (12, 0)],
}
_PP_TF_HOURS: dict[str, int] = {"1h": 1, "4h": 4, "6h": 6, "12h": 12}
_PP_PRESETS: dict[str, dict[str, int]] = {
    "1h":  {"tp": 400,  "sl": 200},
    "4h":  {"tp": 1000, "sl": 500},
    "6h":  {"tp": 1200, "sl": 600},
    "12h": {"tp": 2000, "sl": 200},
}


def _make_signal(pattern: str, direction: str, price: float, sl: float,
                 custom_tp: float, now: datetime) -> Signal:
    """Create a signal that fires on the next price tick."""
    entry_trigger = price - 1.0 if direction == "long" else price + 1.0
    return Signal(
        id=uuid.uuid4().hex[:8],
        pattern=pattern,
        direction=direction,
        tf=1,
        bar_open_time=now.isoformat(),
        entry_trigger=round(entry_trigger, 2),
        sl_wick=round(sl, 2),
        sl_body=round(sl, 2),
        created_at=now,
        expires_at=now + timedelta(minutes=10),
        custom_tp=round(custom_tp, 2),
    )


def _current_pp_session_key(now: datetime, tf: str) -> str:
    now_ist  = now.astimezone(IST)
    sessions = _PP_SESSION_STARTS.get(tf, _PP_SESSION_STARTS["4h"])
    duration = _PP_TF_HOURS.get(tf, 4)
    for h, m in sessions:
        session_start = now_ist.replace(hour=h, minute=m, second=0, microsecond=0)
        session_end   = session_start + timedelta(hours=duration)
        if session_start <= now_ist < session_end:
            return f"{now_ist.date()}_{h:02d}{m:02d}"
    return ""


def check_pingpong(sc, price: float, now: datetime) -> list[Signal]:
    vs      = sc.settings.get("vishal", {})
    tf      = vs.get("pingpong_tf", "4h")
    preset  = _PP_PRESETS.get(tf, _PP_PRESETS["4h"])
    tp_pts  = float(vs.get("pingpong_tp", preset["tp"]))
    sl_pts  = float(vs.get("pingpong_sl", preset["sl"]))

    session_key = _current_pp_session_key(now, tf)
    if not session_key:
        return []

    state = sc.vishal_state
    if state.get("pp_session_key") != session_key:
        state["pp_session_key"]  = session_key
        state["pp_session_open"] = price
        state["pp_long_fired"]   = False
        state["pp_short_fired"]  = False
        return []

    session_open = state["pp_session_open"]
    lower = session_open - sl_pts
    upper = session_open + sl_pts
    sigs: list[Signal] = []

    if not state.get("pp_long_fired") and price <= lower:
        sigs.append(_make_signal("Ping Pong", "long",  lower, lower - sl_pts, lower + tp_pts, now))
        state["pp_long_fired"] = True

    if not state.get("pp_short_fired") and price >= upper:
        sigs.append(_make_signal("Ping Pong", "short", upper, upper + sl_pts, upper - tp_pts, now))
        state["pp_short_fired"] = True

    return sigs


def check_escalator(sc, price: float, now: datetime) -> list[Signal]:
    vs         = sc.settings.get("vishal", {})
    trigger    = float(vs.get("escalator_trigger", 200))
    max_consec = int(vs.get("escalator_max_sl", 3))
    pp_tf      = vs.get("pingpong_tf", "4h")
    sl_pts     = float(vs.get("pingpong_sl", _PP_PRESETS.get(pp_tf, _PP_PRESETS["4h"])["sl"]))

    state          = sc.vishal_state
    pp_session_key = state.get("pp_session_key", "")
    pp_open        = state.get("pp_session_open", 0)

    if state.get("esc_pp_session_key") != pp_session_key and pp_session_key and pp_open:
        state["esc_pp_session_key"]  = pp_session_key
        state["esc_long_baseline"]   = pp_open + 2 * sl_pts
        state["esc_short_baseline"]  = pp_open - 2 * sl_pts
        state["esc_active"]          = False
        state["esc_consec_sl"]       = 0

    if not pp_session_key or not pp_open:
        return []
    if state.get("esc_consec_sl", 0) >= max_consec:
        return []

    sigs: list[Signal] = []

    if state.get("esc_active"):
        sig_id = state.get("esc_signal_id")
        pos    = next((p for p in sc.open_positions
                       if p.signal_id == sig_id and p.status == "open"), None)
        if pos is None:
            state["esc_consec_sl"]      = state.get("esc_consec_sl", 0) + 1
            sl_hit                      = state.get("esc_sl", 0)
            state["esc_long_baseline"]  = sl_hit
            state["esc_short_baseline"] = sl_hit
            state["esc_active"]         = False
        else:
            direction = state.get("esc_direction")
            entry     = state.get("esc_entry", price)
            if direction == "long" and price >= entry + trigger:
                state["esc_sl"]    = entry
                state["esc_entry"] = price
                pos.sl_wick        = entry
                pos.sl_body        = entry
            elif direction == "short" and price <= entry - trigger:
                state["esc_sl"]    = entry
                state["esc_entry"] = price
                pos.sl_wick        = entry
                pos.sl_body        = entry
    else:
        long_bl  = state.get("esc_long_baseline", 0)
        short_bl = state.get("esc_short_baseline", 0)
        if long_bl and price >= long_bl + trigger:
            sig = _make_signal("Escalator", "long", price, long_bl, price + 1_000_000, now)
            sigs.append(sig)
            state.update(esc_active=True, esc_signal_id=sig.id,
                         esc_direction="long", esc_entry=price, esc_sl=long_bl)
        elif short_bl and price <= short_bl - trigger:
            sig = _make_signal("Escalator", "short", price, short_bl, price - 1_000_000, now)
            sigs.append(sig)
            state.update(esc_active=True, esc_signal_id=sig.id,
                         esc_direction="short", esc_entry=price, esc_sl=short_bl)

    return sigs


def check_highwinrate(sc, price: float, now: datetime) -> list[Signal]:
    vs = sc.settings.get("vishal", {})
    target_pts = float(vs.get("hwt_target", 450))
    sl_pts     = float(vs.get("hwt_sl",     100))
    sz         = float(vs.get("hwt_sz",       0))
    dz         = float(vs.get("hwt_dz",       0))
    if not sz or not dz:
        return []

    state = sc.vishal_state
    sigs: list[Signal] = []

    if price > sz and not state.get("hwt_long_fired"):
        sigs.append(_make_signal("High Win Rate", "long",  price, price - sl_pts, price + target_pts, now))
        state["hwt_long_fired"]  = True
        state["hwt_short_fired"] = False
    elif price < dz and not state.get("hwt_short_fired"):
        sigs.append(_make_signal("High Win Rate", "short", price, price + sl_pts, price - target_pts, now))
        state["hwt_short_fired"] = True
        state["hwt_long_fired"]  = False

    return sigs


def check_chaukepechauka(sc, price: float, now: datetime) -> list[Signal]:
    vs = sc.settings.get("vishal", {})
    target_pts = float(vs.get("cpc_target", 1950))
    sz         = float(vs.get("cpc_sz",       0))
    dz         = float(vs.get("cpc_dz",       0))
    if not sz or not dz:
        return []

    state = sc.vishal_state
    tolerance  = 50.0
    sigs: list[Signal] = []

    if abs(price - dz) <= tolerance and not state.get("cpc_long_fired"):
        sigs.append(_make_signal("Chauke pe Chauka", "long",  price, dz - 100, price + target_pts, now))
        state["cpc_long_fired"]  = True
        state["cpc_short_fired"] = False
    elif abs(price - sz) <= tolerance and not state.get("cpc_short_fired"):
        sigs.append(_make_signal("Chauke pe Chauka", "short", price, sz + 100, price - target_pts, now))
        state["cpc_short_fired"] = True
        state["cpc_long_fired"]  = False

    return sigs


def check_rainharv(sc, price: float, now: datetime) -> list[Signal]:
    vs = sc.settings.get("vishal", {})
    tp_pts = float(vs.get("rain_tp", 500))
    sz     = float(vs.get("rain_sz",   0))
    dz     = float(vs.get("rain_dz",   0))
    if not sz or not dz:
        return []

    now_ist = now.astimezone(IST)
    if now_ist.weekday() != 6 or not (now_ist.hour == 22 and now_ist.minute < 30):
        return []

    state = sc.vishal_state
    if state.get("rain_fired_date") == str(now_ist.date()):
        return []

    sigs: list[Signal] = []
    if price > sz:
        sigs.append(_make_signal("Rain Harvesting", "long",  price, sz, price + tp_pts, now))
        state["rain_fired_date"] = str(now_ist.date())
    elif price < dz:
        sigs.append(_make_signal("Rain Harvesting", "short", price, dz, price - tp_pts, now))
        state["rain_fired_date"] = str(now_ist.date())

    return sigs


def check_doubleprofit(sc, price: float, now: datetime) -> list[Signal]:
    vs = sc.settings.get("vishal", {})
    sz = float(vs.get("dp_sz", 0))
    dz = float(vs.get("dp_dz", 0))
    if not sz or not dz:
        return []

    state     = sc.vishal_state
    zone_dist = abs(sz - dz)
    tolerance = min(zone_dist * 0.05, 100)
    sigs: list[Signal] = []

    if abs(price - dz) <= tolerance and not state.get("dp_long_fired"):
        sl = dz - zone_dist * 0.1
        sigs.append(_make_signal("Double Profit", "long",  price, sl, sz, now))
        state["dp_long_fired"]  = True
        state["dp_short_fired"] = False
    elif abs(price - sz) <= tolerance and not state.get("dp_short_fired"):
        sl = sz + zone_dist * 0.1
        sigs.append(_make_signal("Double Profit", "short", price, sl, dz, now))
        state["dp_short_fired"] = True
        state["dp_long_fired"]  = False

    return sigs


def _tick_vishal(sc, current_price: float, now: datetime) -> None:
    vs = sc.settings.get("vishal", {})
    if not vs:
        return
    new_sigs: list[Signal] = []
    if vs.get("pingpong_enabled"):
        new_sigs += check_pingpong(sc, current_price, now)
    if vs.get("escalator_enabled"):
        new_sigs += check_escalator(sc, current_price, now)
    if vs.get("hwt_enabled"):
        new_sigs += check_highwinrate(sc, current_price, now)
    if vs.get("cpc_enabled"):
        new_sigs += check_chaukepechauka(sc, current_price, now)
    if vs.get("rain_enabled"):
        new_sigs += check_rainharv(sc, current_price, now)
    if vs.get("dp_enabled"):
        new_sigs += check_doubleprofit(sc, current_price, now)
    sc.pending_signals.extend(new_sigs)
