"""
Trading Scanner — scans 15m–90m TFs for 4-Flag and Engulfing patterns,
monitors the next candle for a body breakout, then executes a trade on Coinbase.

Each authenticated user runs their own scanner instance with isolated state.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
from rich.console import Console

from btc_agent import config
from btc_agent.scanner.aggregator import aggregate_tf, df_to_numpy
from btc_agent.scanner.data import fetch_1m_candles, fetch_current_price
from btc_agent.scanner.levels import compute_levels
from btc_agent.scanner.patterns import detect_4flag, detect_engulfing
from btc_agent.trading.models import Position, Signal, TradeResult
from btc_agent.trading.vishal_strategies import _tick_vishal
from btc_agent.notifiers import deliver

console = Console()

_IST = timezone(timedelta(hours=5, minutes=30))
_DATA_DIR = Path(__file__).parent.parent / "data"

try:
    from btc_agent.trading import firestore_store as _fs
    _FS = True
except Exception:
    _fs = None  # type: ignore
    _FS = False


# ── per-user scanner state ────────────────────────────────────────────────────

@dataclass
class _Scanner:
    uid: str
    pending_signals: list = field(default_factory=list)
    open_positions: list = field(default_factory=list)
    trade_history: list = field(default_factory=list)
    bsg_alerts: list = field(default_factory=list)
    bsg_traded_bars: list = field(default_factory=list)
    bsg_alerted_bars: list = field(default_factory=list)
    bsg_last_bar: str | None = None
    running: bool = False
    last_scan_time: Optional[datetime] = None
    current_levels: dict = field(default_factory=dict)
    current_regime: dict = field(default_factory=dict)
    last_price: float = 0.0
    settings: dict = field(default_factory=dict)
    broker: object = field(default=None, repr=False)
    thread: object = field(default=None, repr=False)
    vishal_state: dict = field(default_factory=dict)
    current_bias: str = ""
    broker_account_name: str = ""
    user_email: str = ""
    _oi_signals_cache: object = field(default=None, repr=False)

    @property
    def state_path(self) -> Path:
        return _DATA_DIR / f"trading_state_{self.uid[:8]}.json"


_scanners: dict[str, _Scanner] = {}
_scanners_lock = threading.Lock()

_depo_lines: np.ndarray | None = None

def _get_depo_lines() -> np.ndarray:
    global _depo_lines
    if _depo_lines is None:
        from btc_agent.scanner.depo import generate_depo_lines
        _depo_lines = generate_depo_lines()
    return _depo_lines


def _get_or_create(uid: str) -> _Scanner:
    with _scanners_lock:
        if uid not in _scanners:
            _scanners[uid] = _Scanner(uid=uid)
        return _scanners[uid]


# ── settings accessors (per-user) ─────────────────────────────────────────────

def _tf_min(sc: _Scanner) -> int:
    return int(sc.settings.get("tf_min", config.TRADING_TF_MIN))

def _tf_max(sc: _Scanner) -> int:
    return int(sc.settings.get("tf_max", config.TRADING_TF_MAX))

def _scan_interval(sc: _Scanner) -> int:
    return int(sc.settings.get("scan_interval_min", config.TRADING_SCAN_INTERVAL_MIN))

def _trading_mode(sc: _Scanner) -> str:
    return sc.settings.get("mode", config.TRADING_MODE)

def _is_live(sc: _Scanner) -> bool:
    return _trading_mode(sc) == "live"

def _max_concurrent(sc: _Scanner) -> int:
    return int(sc.settings.get("max_concurrent", config.TRADING_MAX_CONCURRENT))

def _trading_qty(sc: _Scanner) -> int:
    return int(sc.settings.get("qty", config.TRADING_QTY))

def _max_sl(sc: _Scanner) -> float:
    return float(sc.settings.get("max_sl", config.TRADING_MAX_SL))

def _min_tp(sc: _Scanner) -> float:
    return float(sc.settings.get("min_tp", config.TRADING_MIN_TP))

def _active_patterns(sc: _Scanner) -> list:
    return sc.settings.get("patterns", config.TRADING_PATTERNS)


def _qty_str(contracts: int) -> str:
    return str(int(contracts))


def _build_broker(sc: _Scanner):
    """Instantiate the broker adapter for this user from their saved settings."""
    from btc_agent.trading.brokers import get_broker
    name = sc.settings.get("broker", config.TRADING_BROKER)
    default_cs = getattr(config, f"{name.upper()}_CONTRACT_SIZE", 0.001)
    creds = {
        "api_key":       sc.settings.get(f"{name}_api_key", ""),
        "api_secret":    sc.settings.get(f"{name}_api_secret", ""),
        "product_id":    sc.settings.get("coinbase_product_id", config.COINBASE_PRODUCT_ID),
        "contract_size": sc.settings.get(f"{name}_contract_size", default_cs),
        # Pepperstone-specific cTrader credentials
        "pepperstone_client_id":     sc.settings.get("pepperstone_client_id",     config.PEPPERSTONE_CLIENT_ID),
        "pepperstone_client_secret": sc.settings.get("pepperstone_client_secret", config.PEPPERSTONE_CLIENT_SECRET),
        "pepperstone_refresh_token": sc.settings.get("pepperstone_refresh_token", ""),
        "pepperstone_account_id":    sc.settings.get("pepperstone_account_id",    config.PEPPERSTONE_ACCOUNT_ID),
        "pepperstone_is_live":       sc.settings.get("pepperstone_is_live",       config.PEPPERSTONE_IS_LIVE),
    }
    return get_broker(name, creds)


# ── SL calculation ────────────────────────────────────────────────────────────

def calc_sl(sl_wick: float) -> float:
    """SL is always the wick low/high of the pattern candle."""
    return round(sl_wick, 2)


# ── TP calculation using market structure levels ──────────────────────────────

def _calc_tp(sc: _Scanner, direction: str, entry: float) -> tuple[float, str]:
    levels = sc.current_levels
    mrp        = levels.get("mrp")
    daily_poc  = levels.get("daily_poc")
    weekly_poc = levels.get("weekly_poc")
    poc_4h     = levels.get("4h_poc")

    level_pool = [(mrp, "MRP"), (daily_poc, "Daily POC"), (weekly_poc, "Weekly POC"), (poc_4h, "4H POC")]
    candidates: list[tuple[float, str]] = []
    if direction == "long":
        for price, label in level_pool:
            if price and price > entry:
                candidates.append((price, label))
        tp_price, tp_reason = min(candidates, key=lambda x: x[0]) if candidates else (None, "")
    else:
        for price, label in level_pool:
            if price and price < entry:
                candidates.append((price, label))
        tp_price, tp_reason = max(candidates, key=lambda x: x[0]) if candidates else (None, "")

    floor = _min_tp(sc)
    if tp_price is None:
        fallback = entry + floor if direction == "long" else entry - floor
        return round(fallback, 2), "fixed_500"

    dist = tp_price - entry if direction == "long" else entry - tp_price
    if dist < floor:
        tp_price = entry + floor if direction == "long" else entry - floor
        tp_reason = f"{tp_reason}(min_floor)"
    elif dist > 500:
        tp_price = entry + 500 if direction == "long" else entry - 500
        tp_reason = "500_cap"

    return round(tp_price, 2), tp_reason


def _bias_filter_enabled(sc: _Scanner) -> bool:
    return bool(sc.settings.get("bias_filter", config.TRADING_BIAS_FILTER))

def _depo_entry_filter_enabled(sc: _Scanner) -> bool:
    return bool(sc.settings.get("depo_entry_filter", config.DEPO_ENTRY_FILTER))

def _poc_entry_filter_enabled(sc: _Scanner) -> bool:
    return bool(sc.settings.get("poc_entry_filter", config.POC_ENTRY_FILTER))

def _compression_enabled(sc: _Scanner) -> bool:
    return bool(sc.settings.get("compression_enabled", config.COMPRESSION_ENABLED))

_HISTORY_CAP = 200

def _append_history(sc: "_Scanner", result) -> None:
    sc.trade_history.append(result)
    if len(sc.trade_history) > _HISTORY_CAP:
        del sc.trade_history[:-_HISTORY_CAP]


def _cme_close_skip_enabled(sc: _Scanner) -> bool:
    return bool(sc.settings.get("cme_close_skip", config.TRADING_CME_CLOSE_SKIP))

def _opposite_signal_action(sc: _Scanner) -> str:
    return sc.settings.get("opposite_signal_action", config.TRADING_OPPOSITE_SIGNAL_ACTION)

def _oi_filter_enabled(sc: _Scanner) -> bool:
    return bool(sc.settings.get("oi_filter_enabled", config.OI_FILTER_ENABLED))

def _oi_threshold_mult(sc: _Scanner) -> float:
    return float(sc.settings.get("oi_threshold_mult", config.OI_THRESHOLD_MULT))

def _oi_lookback_bars(sc: _Scanner) -> int:
    return int(sc.settings.get("oi_lookback_bars", config.OI_LOOKBACK_BARS))

def _oi_div_lookback(sc: _Scanner) -> int:
    return int(sc.settings.get("oi_div_lookback", config.OI_DIV_LOOKBACK))

def _oi_tf(sc: _Scanner) -> int:
    return int(sc.settings.get("oi_tf", config.OI_TF))


def _is_cme_closed() -> bool:
    """True during CME closure: Fri 16:00 CT → Sun 17:00 CT."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/Chicago"))
    dow = now.weekday()  # 0=Mon … 4=Fri, 5=Sat, 6=Sun
    mins = now.hour * 60 + now.minute
    return (
        (dow == 4 and mins >= 960) or   # Fri >= 16:00 CT
        dow == 5 or                      # Saturday
        (dow == 6 and mins < 1020)       # Sun < 17:00 CT
    )


def _trend_bias(price: float, levels: dict) -> str:
    # Counts how many of MRP / Daily POC / Weekly POC / 4H POC the price sits
    # above. Null levels are dropped so the threshold scales with how many are
    # available. Mirrors the frontend formula in main.js renderLevels().
    vals = [levels.get(k) for k in ("mrp", "daily_poc", "weekly_poc", "4h_poc")]
    vals = [v for v in vals if v]
    if not vals:
        return ""
    above = sum(price > v for v in vals)
    n = len(vals)
    if above == n:    return "strongly bullish"
    if above > n / 2: return "bullish"
    if above == 0:    return "strongly bearish"
    return "bearish"


# ── signal creation ───────────────────────────────────────────────────────────

def _bars_to_signal(pattern: str, direction: str, tf: int, bars: np.ndarray, bar_open_time: str, lookback: int = 3) -> Signal:
    o, h, l, c = bars[-1, 0], bars[-1, 1], bars[-1, 2], bars[-1, 3]
    body_hi = max(o, c)
    body_lo = min(o, c)
    now = datetime.now(timezone.utc)
    if pattern == "4-Flag":
        flag_bars = bars[-4:]
        flag_body_his = np.maximum(flag_bars[:, 0], flag_bars[:, 3])
        flag_body_los = np.minimum(flag_bars[:, 0], flag_bars[:, 3])
        entry_trigger = float(flag_body_his.max()) if direction == "long" else float(flag_body_los.min())
        # SL spans the full consolidation range across all 4 bars, not just the last bar
        sl_wick = float(flag_bars[:, 2].min()) if direction == "long" else float(flag_bars[:, 1].max())
        sl_body = float(flag_body_los.min()) if direction == "long" else float(flag_body_his.max())
    else:
        entry_trigger = body_hi if direction == "long" else body_lo
        sl_wick = l if direction == "long" else h
        sl_body = body_lo if direction == "long" else body_hi
    bar_dt = datetime.fromisoformat(bar_open_time.replace('Z', '')).replace(tzinfo=timezone.utc)
    expires_at = bar_dt + timedelta(minutes=(lookback + 1) * tf)
    return Signal(
        id=uuid.uuid4().hex[:8],
        pattern=pattern, direction=direction, tf=tf,
        bar_open_time=bar_open_time,
        entry_trigger=round(entry_trigger, 2),
        sl_wick=round(sl_wick, 2), sl_body=round(sl_body, 2),
        created_at=now, expires_at=expires_at,
    )


# ── pattern scan ──────────────────────────────────────────────────────────────

def _is_duplicate(sc: _Scanner, tf: int, pattern: str, direction: str, bar_open_time: str) -> bool:
    return any(
        s.status in ("pending", "triggered") and
        s.tf == tf and s.pattern == pattern and
        s.direction == direction and s.bar_open_time == bar_open_time
        for s in sc.pending_signals
    )


def _last_swing_high(highs: np.ndarray, n: int = 3):
    if len(highs) < 2 * n + 1:
        return None, None
    for i in range(len(highs) - n - 1, n - 1, -1):
        if all(highs[i] >= highs[i - j] for j in range(1, n + 1)) and \
           all(highs[i] >= highs[i + j] for j in range(1, n + 1)):
            return i, float(highs[i])
    return None, None


def _last_swing_low(lows: np.ndarray, n: int = 3):
    if len(lows) < 2 * n + 1:
        return None, None
    for i in range(len(lows) - n - 1, n - 1, -1):
        if all(lows[i] <= lows[i - j] for j in range(1, n + 1)) and \
           all(lows[i] <= lows[i + j] for j in range(1, n + 1)):
            return i, float(lows[i])
    return None, None


def _all_swing_highs(highs: np.ndarray, n: int = 3) -> list:
    result = []
    if len(highs) < 2 * n + 1:
        return result
    for i in range(len(highs) - n - 1, n - 1, -1):
        if all(highs[i] >= highs[i - j] for j in range(1, n + 1)) and \
           all(highs[i] >= highs[i + j] for j in range(1, n + 1)):
            result.append((i, float(highs[i])))
    return result


def _all_swing_lows(lows: np.ndarray, n: int = 3) -> list:
    result = []
    if len(lows) < 2 * n + 1:
        return result
    for i in range(len(lows) - n - 1, n - 1, -1):
        if all(lows[i] <= lows[i - j] for j in range(1, n + 1)) and \
           all(lows[i] <= lows[i + j] for j in range(1, n + 1)):
            result.append((i, float(lows[i])))
    return result


def _check_retracement(sc: _Scanner, bars: np.ndarray, bar_ts, tf: int, now: datetime) -> "Signal | None":
    if len(bars) < 5:
        return None
    if any(s.pattern == "Retracement" and s.tf == tf and s.status == "pending" for s in sc.pending_signals):
        return None

    SL_PTS    = 300
    MIN_SWING = 1700

    closed     = bars[:-1]
    highs_arr  = closed[:, 1]
    lows_arr   = closed[:, 2]

    sw_hi_idx = sw_hi = sw_lo_idx = sw_lo = None
    direction  = None

    # SHORT setup: anchor on most recent swing low, walk back through highs
    recent_lo_idx, recent_lo = _last_swing_low(lows_arr, n=3)
    if recent_lo_idx is not None:
        for hi_idx, hi_price in _all_swing_highs(highs_arr, n=3):
            if hi_idx < recent_lo_idx and hi_price - recent_lo >= MIN_SWING:
                sw_hi_idx, sw_hi = hi_idx, hi_price
                sw_lo_idx, sw_lo = recent_lo_idx, recent_lo
                direction = "short"
                break

    # LONG setup: anchor on most recent swing high, walk back through lows
    recent_hi_idx, recent_hi = _last_swing_high(highs_arr, n=3)
    if recent_hi_idx is not None:
        for lo_idx, lo_price in _all_swing_lows(lows_arr, n=3):
            if lo_idx < recent_hi_idx and recent_hi - lo_price >= MIN_SWING:
                if direction is None or recent_hi_idx > recent_lo_idx:
                    sw_hi_idx, sw_hi = recent_hi_idx, recent_hi
                    sw_lo_idx, sw_lo = lo_idx, lo_price
                    direction = "long"
                break

    if direction is None:
        return None

    fib_range = sw_hi - sw_lo
    last  = bars[-1]
    bar_h = float(last[1])
    bar_l = float(last[2])
    bar_c = float(last[3])
    ts    = int(bar_ts[-1]) if len(bar_ts) else int(now.timestamp())
    bar_open_iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    fib_50 = round(sw_hi - 0.500 * fib_range, 1)  # midpoint, same both directions

    if direction == "long":
        # Price pulled back DOWN from swing high — enter LONG at fib levels
        # 0.618 from low upward = shallower pullback (above midpoint)
        fib_618 = round(sw_lo + 0.618 * fib_range, 1)
        if (bar_l <= fib_618 and bar_c > fib_618) or (bar_l <= fib_50 and bar_c > fib_50):
            return Signal(
                id=uuid.uuid4().hex[:8], pattern="Retracement", direction="long",
                tf=tf, bar_open_time=bar_open_iso,
                entry_trigger=round(bar_c - 1.0, 2),
                sl_wick=round(fib_50 - SL_PTS, 2), sl_body=round(fib_50 - SL_PTS, 2),
                created_at=now, expires_at=now + timedelta(minutes=tf),
                custom_tp=round(sw_hi, 2),
                meta={"sw_hi": round(sw_hi, 1), "sw_lo": round(sw_lo, 1),
                      "fib_50": fib_50, "fib_618": fib_618},
            )
    else:
        # Price bouncing UP from swing low — enter SHORT at fib levels
        # 0.618 from high downward = deeper retracement (below midpoint)
        fib_618 = round(sw_hi - 0.618 * fib_range, 1)
        if (bar_h >= fib_50 and bar_c < fib_50) or (bar_h >= fib_618 and bar_c < fib_618):
            return Signal(
                id=uuid.uuid4().hex[:8], pattern="Retracement", direction="short",
                tf=tf, bar_open_time=bar_open_iso,
                entry_trigger=round(bar_c + 1.0, 2),
                sl_wick=round(fib_50 + SL_PTS, 2), sl_body=round(fib_50 + SL_PTS, 2),
                created_at=now, expires_at=now + timedelta(minutes=tf),
                custom_tp=round(sw_lo, 2),
                meta={"sw_hi": round(sw_hi, 1), "sw_lo": round(sw_lo, 1),
                      "fib_50": fib_50, "fib_618": fib_618},
            )
    return None


def _check_compression(sc: _Scanner, arr, ts_arr, minutes_of_day, unix_days, now: datetime) -> list[Signal]:
    """30m-first, 1H-fallback compression signal: all 3 POCs inside one candle's H-L, close breaks out."""
    d_poc  = sc.current_levels.get("daily_poc")
    w_poc  = sc.current_levels.get("weekly_poc")
    h4_poc = sc.current_levels.get("4h_poc")
    if not (d_poc and w_poc and h4_poc):
        return []

    for tf in (30, 60):
        bars, bar_ts = aggregate_tf(arr, ts_arr, minutes_of_day, unix_days, tf, last_n=3)
        if bars is None or len(bars) < 2:
            continue

        candle       = bars[-2]          # last fully closed bar
        bar_open_iso = bar_ts[-2] if hasattr(bar_ts[-2], "__str__") else str(bar_ts[-2])
        hi    = float(candle[1])
        lo    = float(candle[2])
        close = float(candle[3])

        all_in = (lo <= d_poc <= hi) and (lo <= w_poc <= hi) and (lo <= h4_poc <= hi)
        if not all_in:
            continue  # 30m failed → try 1H; 1H failed → no signal

        poc_max = max(d_poc, w_poc, h4_poc)
        poc_min = min(d_poc, w_poc, h4_poc)

        if close > poc_max:
            direction = "long"
        elif close < poc_min:
            direction = "short"
        else:
            break  # 30m qualified but closed inside cluster — don't check 1H

        if _is_duplicate(sc, tf, "Compression", direction, bar_open_iso):
            break  # already emitted for this bar — don't check 1H

        entry = round(close - 1.0 if direction == "long" else close + 1.0, 2)
        sl    = round(lo if direction == "long" else hi, 2)
        tp    = round(entry + 5100 if direction == "long" else entry - 5100, 2)

        sig = Signal(
            id=uuid.uuid4().hex[:8], pattern="Compression", direction=direction,
            tf=tf, bar_open_time=bar_open_iso,
            entry_trigger=entry,
            sl_wick=sl, sl_body=sl,
            custom_tp=tp,
            created_at=now, expires_at=now + timedelta(minutes=tf * 2),
        )
        sig.meta["compression_tf"]    = tf
        sig.meta["compression_4h_poc"] = h4_poc
        console.print(
            f"[bold magenta]Compression[/bold magenta] detected on [green]{tf}m[/green] "
            f"→ {direction.upper()}  entry={entry:.1f}  SL={sl:.1f}  TP={tp:.1f}"
        )
        return [sig]

    return []


def _check_compression_exits(sc: _Scanner, arr, ts_arr, minutes_of_day, unix_days, current_price: float) -> None:
    """Close compression positions whose same-TF candle closed on wrong side of 4H POC."""
    for pos in sc.open_positions:
        if pos.status != "open" or not pos.compression_tf or not pos.compression_4h_poc:
            continue
        bars, bar_ts = aggregate_tf(arr, ts_arr, minutes_of_day, unix_days, pos.compression_tf, last_n=3)
        if bars is None or len(bars) < 2:
            continue
        last_bar_open = str(bar_ts[-2])
        if last_bar_open == pos.compression_last_bar_time:
            continue  # already checked this bar
        pos.compression_last_bar_time = last_bar_open
        bar_close = float(bars[-2][3])
        poc = pos.compression_4h_poc
        exit_hit = (
            (pos.direction == "long"  and bar_close < poc) or
            (pos.direction == "short" and bar_close > poc)
        )
        if exit_hit:
            console.print(
                f"[magenta]Compression POC exit: {pos.direction} closed {bar_close:.1f} "
                f"{'<' if pos.direction == 'long' else '>'} 4H POC {poc:.1f}[/magenta]"
            )
            _close_position(sc, pos, current_price, "compression_poc_exit")


def _scan_patterns(sc: _Scanner, arr, ts_arr, minutes_of_day, unix_days) -> list[Signal]:
    new_signals: list[Signal] = []
    patterns = _active_patterns(sc)
    lookback = _lookback_candles(sc)
    for tf in range(_tf_min(sc), _tf_max(sc) + 1):
        bars, bar_open_times = aggregate_tf(arr, ts_arr, minutes_of_day, unix_days, tf, last_n=max(lookback + 1, 4))
        if bars is None or len(bars) < 2:
            continue
        bar_open_ts = int(bar_open_times[-1])
        bar_open_time = datetime.fromtimestamp(bar_open_ts, tz=timezone.utc).isoformat()

        if "4-Flag" in patterns and len(bars) >= 4:
            window = bars[-4:]
            if detect_4flag(window):
                for direction in ("long", "short"):
                    if not _is_duplicate(sc, tf, "4-Flag", direction, bar_open_time):
                        sig = _bars_to_signal("4-Flag", direction, tf, window, bar_open_time, lookback)
                        sig.meta["bar_high"] = float(window[:, 1].max())
                        sig.meta["bar_low"]  = float(window[:, 2].min())
                        from btc_agent.scanner.depo import check_depo
                        depo_hit = check_depo(window, _get_depo_lines())
                        if depo_hit:
                            sig.meta["depo_line"] = depo_hit
                        new_signals.append(sig)
                        console.print(
                            f"[bold yellow]4-Flag[/bold yellow] detected on [green]{tf}m[/green] "
                            f"→ {direction.upper()}  trigger={sig.entry_trigger:.1f}"
                            + (f"  [magenta]DEPO@{depo_hit:.0f}[/magenta]" if depo_hit else "")
                        )

        if "Engulfing" in patterns and len(bars) >= 2:
            found, eng_dir = detect_engulfing(bars[-2:])
            if found:
                direction = "long" if eng_dir == "bullish" else "short"
                if not _is_duplicate(sc, tf, "Engulfing", direction, bar_open_time):
                    sig = _bars_to_signal("Engulfing", direction, tf, bars, bar_open_time, lookback)
                    sig.meta["bar_high"] = float(bars[-2:, 1].max())
                    sig.meta["bar_low"]  = float(bars[-2:, 2].min())
                    from btc_agent.scanner.depo import check_depo
                    depo_hit = check_depo(bars[-2:], _get_depo_lines())
                    if depo_hit:
                        sig.meta["depo_line"] = depo_hit
                    new_signals.append(sig)
                    console.print(
                        f"[bold cyan]Engulfing ({direction})[/bold cyan] on [green]{tf}m[/green] "
                        f"→ {direction.upper()}  trigger={sig.entry_trigger:.1f}"
                        + (f"  [magenta]DEPO@{depo_hit:.0f}[/magenta]" if depo_hit else "")
                    )

    if "Retracement" in patterns:
        ret_now = datetime.now(timezone.utc)
        bars, bar_ts = aggregate_tf(arr, ts_arr, minutes_of_day, unix_days, 30, last_n=101)
        if bars is not None:
            sig = _check_retracement(sc, bars, bar_ts, 30, ret_now)
            if sig:
                new_signals.append(sig)
                console.print(
                    f"[bold magenta]Retracement ({sig.direction})[/bold magenta] on "
                    f"[green]30m[/green]  trigger={sig.entry_trigger:.1f}  "
                    f"SH={sig.meta['sw_hi']:.0f}  SL={sig.meta['sw_lo']:.0f}"
                )

    return new_signals


# ── Buy Sell Guide (Dual SuperTrend, alert-only) ──────────────────────────────

_BSG_TF = 15


def _supertrend(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray,
                period: int, mult: float):
    n = len(closes)
    prev_close = np.empty(n)
    prev_close[0] = closes[0]
    prev_close[1:] = closes[:-1]
    tr = np.maximum(highs - lows,
         np.maximum(np.abs(highs - prev_close), np.abs(lows - prev_close)))
    atr = np.zeros(n)
    atr[0] = tr[0]
    for i in range(1, n):                              # Wilder RMA
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    lb = closes - mult * atr
    ub = closes + mult * atr
    trail = np.zeros(n)
    bull = np.zeros(n, dtype=bool)
    trail[0] = lb[0]
    bull[0] = True
    for i in range(1, n):
        if bull[i - 1]:
            trail[i] = max(trail[i - 1], lb[i]) if closes[i] > trail[i - 1] else ub[i]
        else:
            trail[i] = min(trail[i - 1], ub[i]) if closes[i] < trail[i - 1] else lb[i]
        bull[i] = closes[i] > trail[i]
    return trail, bull


def _bsg_enabled(sc: _Scanner) -> bool:
    return bool(sc.settings.get("bsg_enabled", getattr(config, "BSG_ENABLED", False)))


def _bsg_trade_enabled(sc: _Scanner) -> bool:
    return bool(sc.settings.get("bsg_trade_enabled", getattr(config, "BSG_TRADE_ENABLED", False)))


def _tick_bsg(sc: _Scanner, arr, ts_arr, minutes_of_day, unix_days) -> None:
    if not _bsg_enabled(sc):
        return
    for tf in (_BSG_TF,):
        try:
            bars, bar_open_times = aggregate_tf(arr, ts_arr, minutes_of_day, unix_days, tf, last_n=200)
            if bars is None or len(bars) < 4:
                continue
            c = bars[:, 3].astype(float)
            h = bars[:, 1].astype(float)
            l = bars[:, 2].astype(float)
            buy_trail, buy_bull  = _supertrend(c, h, l, 50, 1.0)
            sell_trail, sell_bull = _supertrend(c, h, l,  3, 1.0)
            n = len(c)
            # Scan all completed bars (exclude last which may be in-progress)
            # Populate dashboard alerts for all historical bars
            for i in range(1, n - 1):
                buy_sig  = bool(sell_bull[i] and not sell_bull[i - 1])
                sell_sig = bool(not sell_bull[i] and sell_bull[i - 1])
                if not (buy_sig or sell_sig):
                    continue
                if sell_sig and buy_bull[i]:
                    continue
                bar_time  = datetime.fromtimestamp(int(bar_open_times[i]), tz=timezone.utc).isoformat()
                direction = "long" if buy_sig else "short"
                if any(a["bar_time"] == bar_time and a["direction"] == direction
                       and a["tf"] == tf for a in sc.bsg_alerts):
                    continue
                sc.bsg_alerts.append({
                    "direction": direction, "bar_time": bar_time,
                    "tf": tf, "price": float(c[i]),
                })
            sc.bsg_alerts = sc.bsg_alerts[-20:]

            # Deliver notification exactly once per new signal on the latest completed bar
            i_sig = n - 2
            buy_sig_now  = bool(sell_bull[i_sig] and not sell_bull[i_sig - 1])
            sell_sig_now = bool(not sell_bull[i_sig] and sell_bull[i_sig - 1])
            if sell_sig_now and buy_bull[i_sig]:
                sell_sig_now = False
            if buy_sig_now or sell_sig_now:
                direction  = "long" if buy_sig_now else "short"
                bar_time   = datetime.fromtimestamp(int(bar_open_times[i_sig]), tz=timezone.utc).isoformat()
                already_delivered = (direction, bar_time, tf) in sc.bsg_alerted_bars
                if not already_delivered:
                    sl_val     = float(buy_trail[i_sig])
                    price      = float(c[i_sig])
                    alert_name = "BSG_BUY" if direction == "long" else "BSG_SELL"
                    emoji      = "🟢" if direction == "long" else "🔴"
                    title      = f"{emoji} {alert_name}"
                    msg        = (
                        f"Symbol: BTCUSDT\n"
                        f"Timeframe: 15m\n"
                        f"Action: {'BUY' if direction == 'long' else 'SELL'}\n"
                        f"Price: ${price:,.2f}\n"
                        f"Trail Stop: ${sl_val:,.2f}\n\n"
                        f"Alert: {alert_name}"
                    )
                    sc.bsg_alerted_bars.append((direction, bar_time, tf))
                    sc.bsg_alerted_bars = sc.bsg_alerted_bars[-50:]
                    console.print(f"[bold magenta]{title}[/bold magenta] @ {price:.1f}  SL={sl_val:.1f}")
                    threading.Thread(target=deliver, args=(title, msg), daemon=True).start()

            # ── Trading entries on latest completed bar (15m only) ────────────
            if tf == 15 and _bsg_trade_enabled(sc):
                i_last = n - 2
                # Raw crossovers — closing an existing position needs no slow trail filter
                raw_buy  = bool(sell_bull[i_last] and not sell_bull[i_last - 1])
                raw_sell = bool(not sell_bull[i_last] and sell_bull[i_last - 1])
                # Filtered signals — opening a new Short requires slow trail also bearish
                buy_sig_now  = raw_buy
                sell_sig_now = raw_sell and not buy_bull[i_last]

                # Close existing opposite BSG position on any raw crossover
                if raw_buy or raw_sell:
                    close_dir = "short" if raw_buy else "long"
                    for _pos in list(sc.open_positions):
                        if _pos.status == "open" and _pos.pattern == "BSG" and _pos.direction == close_dir:
                            entry_px_now = sc.last_price or float(c[i_last])
                            console.print(f"[magenta]BSG opposite signal — closing {close_dir} position[/magenta]")
                            _close_position(sc, _pos, entry_px_now, "tp")

                # Open new position only on filtered signals
                if buy_sig_now or sell_sig_now:
                    direction = "long" if buy_sig_now else "short"
                    bar_time  = datetime.fromtimestamp(int(bar_open_times[i_last]), tz=timezone.utc).isoformat()
                    already_signalled = (
                        any(
                            s.pattern == "BSG" and s.direction == direction and s.bar_open_time == bar_time
                            for s in sc.pending_signals
                        ) or (direction, bar_time, tf) in sc.bsg_traded_bars
                    )
                    if not already_signalled:
                        now_utc = datetime.now(timezone.utc)
                        bar_dt = datetime.fromtimestamp(int(bar_open_times[i_last]), tz=timezone.utc)
                        bar_close_dt = bar_dt + timedelta(minutes=tf)
                        if now_utc - bar_close_dt > timedelta(minutes=tf):
                            sc.bsg_traded_bars.append((direction, bar_time, tf))
                            sc.bsg_traded_bars = sc.bsg_traded_bars[-50:]
                            console.print(
                                f"[yellow]BSG {direction} signal stale "
                                f"({int((now_utc - bar_close_dt).total_seconds() // 60)}m old), skipping[/yellow]"
                            )
                            continue
                        entry_px = sc.last_price or float(c[i_last])
                        # Use slow trail (buy_trail) as SL for both directions — kept constant at entry
                        sl_price = float(buy_trail[i_last])
                        sl_dist  = abs(entry_px - sl_price)
                        if sl_dist < 100:
                            sl_price = (entry_px - 150) if direction == "long" else (entry_px + 150)
                        sig = Signal(
                            id=uuid.uuid4().hex[:8],
                            pattern="BSG", direction=direction, tf=tf,
                            bar_open_time=bar_time,
                            entry_trigger=round(entry_px * (0.9999 if direction == "long" else 1.0001), 2),
                            sl_wick=round(sl_price, 2),
                            sl_body=round(sl_price, 2),
                            created_at=now_utc,
                            expires_at=now_utc + timedelta(minutes=tf),
                        )
                        if _bias_filter_enabled(sc) and sc.current_bias:
                            allowed = "long" if "bullish" in sc.current_bias else "short"
                            if direction != allowed:
                                console.print(
                                    f"[yellow]BSG {direction} skipped — bias {sc.current_bias} requires {allowed}[/yellow]"
                                )
                                continue
                        sc.pending_signals.append(sig)
                        sc.bsg_traded_bars.append((direction, bar_time, tf))
                        sc.bsg_traded_bars = sc.bsg_traded_bars[-50:]
                        console.print(
                            f"[bold magenta]BSG TRADE {direction.upper()}[/bold magenta] "
                            f"@ ~{entry_px:.1f}  SL={sl_price:.1f}  dist={abs(entry_px - sl_price):.1f}"
                        )
                        _execute_entry(sc, sig, entry_px)
        except Exception as e:
            console.print(f"[red]BSG {tf}m error: {e}[/red]")
            console.print_exception(max_frames=5)


# ── entry execution ───────────────────────────────────────────────────────────

def _today_pts(sc: _Scanner) -> float:
    today = datetime.now(timezone.utc).date()
    total = 0.0
    for r in sc.trade_history:
        if r.closed_at and r.closed_at.date() == today:
            pts = (r.close_price - r.position.entry_price
                   if r.position.direction == "long"
                   else r.position.entry_price - r.close_price)
            total += pts
    return total


def _sl_pts_lost(r) -> float:
    """Points lost on an SL close. Positive = real loss. Zero/negative = breakeven or better."""
    if r.position.direction == "long":
        return r.position.entry_price - r.close_price
    return r.close_price - r.position.entry_price


def _today_sl_count(sc: _Scanner) -> int:
    today = datetime.now(timezone.utc).date()
    return sum(
        1 for r in sc.trade_history
        if r.closed_at and r.closed_at.date() == today
        and r.close_reason == "sl"
        and _sl_pts_lost(r) > 0
    )


def _today_sl_pts(sc: _Scanner) -> float:
    today = datetime.now(timezone.utc).date()
    return sum(
        _sl_pts_lost(r) for r in sc.trade_history
        if r.closed_at and r.closed_at.date() == today
        and r.close_reason == "sl"
        and _sl_pts_lost(r) > 0
    )


def _execute_entry(sc: _Scanner, sig: Signal, current_price: float) -> None:
    if _cme_close_skip_enabled(sc) and _is_cme_closed():
        console.print(f"[yellow]Signal {sig.id} skipped — CME closed (Fri 16:00–Sun 17:00 CT)[/yellow]")
        return

    opp_pos = [p for p in sc.open_positions if p.status == "open" and p.direction != sig.direction]
    if opp_pos:
        if _opposite_signal_action(sc) == "flip":
            for opp in opp_pos:
                console.print(f"[cyan]Flip: closing opposite {opp.direction} {opp.tf}m before {sig.direction} entry[/cyan]")
                _close_position(sc, opp, current_price, "opposite_signal")
        else:
            sig.status = "skipped"
            console.print(f"[yellow]Signal {sig.id} skipped — opposite direction position open (action=skip)[/yellow]")
            if _FS: _fs.update_signal_status(sig.id, "skipped")
            _save_state(sc)
            return

    same_dir = [p for p in sc.open_positions
                if p.status == "open" and p.tf == sig.tf and p.direction == sig.direction]
    if same_dir:
        sig.status = "skipped"
        console.print(f"[yellow]Signal {sig.id} skipped — {sig.direction} position already open on {sig.tf}m[/yellow]")
        if _FS: _fs.update_signal_status(sig.id, "skipped")
        _save_state(sc)
        return

    n_open = sum(1 for p in sc.open_positions if p.status == "open")
    cap = _max_concurrent(sc)
    if cap > 0 and n_open >= cap:
        sig.status = "skipped"
        console.print(f"[yellow]Signal {sig.id} skipped — max concurrent ({cap}) reached[/yellow]")
        if _FS: _fs.update_signal_status(sig.id, "skipped")
        _save_state(sc)
        return

    daily_target = float(sc.settings.get("daily_pts_target") or 0) or config.TRADING_DAILY_PTS_TARGET
    if daily_target > 0:
        today_pts = _today_pts(sc)
        if today_pts >= daily_target:
            sig.status = "skipped"
            console.print(f"[yellow]Signal {sig.id} skipped — daily {today_pts:.0f}pts ≥ target {daily_target:.0f}pts[/yellow]")
            if _FS: _fs.update_signal_status(sig.id, "skipped")
            _save_state(sc)
            return

    daily_sl_pts = float(sc.settings.get("daily_sl_pts") or 0) or config.TRADING_DAILY_SL_PTS
    if daily_sl_pts > 0:
        sl_pts_lost = _today_sl_pts(sc)
        if sl_pts_lost >= daily_sl_pts:
            sig.status = "skipped"
            console.print(f"[yellow]Signal {sig.id} skipped — daily SL loss {sl_pts_lost:.0f}pts ≥ limit {daily_sl_pts:.0f}pts[/yellow]")
            if _FS: _fs.update_signal_status(sig.id, "skipped")
            _save_state(sc)
            return

    daily_sl_limit = int(sc.settings.get("daily_sl_limit") or 0) or config.TRADING_DAILY_SL_LIMIT
    if daily_sl_limit > 0:
        sl_count = _today_sl_count(sc)
        if sl_count >= daily_sl_limit:
            sig.status = "skipped"
            console.print(f"[yellow]Signal {sig.id} skipped — daily SL count {sl_count} ≥ limit {daily_sl_limit}[/yellow]")
            if _FS: _fs.update_signal_status(sig.id, "skipped")
            _save_state(sc)
            return

    entry = current_price
    sl = calc_sl(sig.sl_wick)
    sl_dist = abs(entry - sl)
    is_bsg = sig.pattern == "BSG"
    if not is_bsg:
        sl_cap = _max_sl(sc)
        if sl_dist > sl_cap:
            console.print(f"[yellow]Signal {sig.id} skipped — SL {sl_dist:.0f}pts > {sl_cap:.0f}pt limit[/yellow]")
            sig.status = "skipped"
            if _FS: _fs.update_signal_status(sig.id, "skipped")
            _save_state(sc)
            return
    if is_bsg:
        tp = 9_999_999.0 if sig.direction == "long" else 1.0
        tp_reason = "opposite_signal"
    elif sig.custom_tp > 0:
        tp, tp_reason = sig.custom_tp, sig.pattern
    else:
        tp, tp_reason = _calc_tp(sc, sig.direction, entry)

    depo_line = (sig.meta or {}).get("depo_line")
    depo_tp1 = depo_tp2 = None
    if depo_line and not is_bsg:
        from btc_agent.scanner.depo import next_depo_level
        depo_tp1 = round(entry + 950 if sig.direction == "long" else entry - 950, 2)
        depo_tp2 = next_depo_level(_get_depo_lines(), depo_line, sig.direction)
        if depo_tp2:
            tp = round(depo_tp2, 2)
            tp_reason = f"DEPO@{depo_line:.0f}"
            console.print(f"[magenta]DEPO trade: TP1={depo_tp1:.1f}  TP2(DEPO)={depo_tp2:.1f}[/magenta]")

    qty = _trading_qty(sc)
    sig.status = "triggered"

    pos = Position(
        signal_id=sig.id, entry_price=entry, sl=sl, tp=tp, qty=qty,
        direction=sig.direction, opened_at=datetime.now(timezone.utc),
        pattern=sig.pattern, tf=sig.tf, tp_reason=tp_reason,
    )
    pos.depo_line = depo_line
    pos.depo_tp1 = depo_tp1
    pos.depo_tp2 = depo_tp2

    if sig.pattern == "Compression":
        pos.compression_tf        = (sig.meta or {}).get("compression_tf")
        pos.compression_4h_poc    = (sig.meta or {}).get("compression_4h_poc")
        pos.compression_last_bar_time = sig.bar_open_time

    mode = _trading_mode(sc)
    if _is_live(sc):
        broker = sc.broker
        side = "BUY" if sig.direction == "long" else "SELL"
        stop_side = "SELL" if sig.direction == "long" else "BUY"
        qty_str = _qty_str(qty)
        # Entry order — abort entirely if this fails (no position created)
        try:
            order = broker.place_market_order(side, qty_str)
            pos.coinbase_order_id = order.get("order_id", "")
        except Exception as e:
            console.print(f"[red]Broker order failed: {e}[/red]")
            sig.status = "pending"
            return
        # SL order — warn but still track the position so concurrent count is correct
        try:
            limit_sl = round(sl * 0.995 if sig.direction == "long" else sl * 1.005, 2)
            sl_resp = broker.place_stop_limit_order(stop_side, qty_str, sl, limit_sl)
            pos.sl_order_id = sl_resp.get("order_id", "")
        except Exception as e:
            console.print(f"[yellow]SL order failed — position tracked without SL: {e}[/yellow]")
        # TP order — BSG uses no broker TP (exits on opposite signal only)
        if not is_bsg:
            tp_qty = int(qty) // 2 if sig.tf >= 30 else int(qty)
            try:
                limit_tp = round(tp * 0.995 if sig.direction == "long" else tp * 1.005, 2)
                tp_resp = broker.place_take_profit_order(stop_side, _qty_str(tp_qty), tp, limit_tp)
                pos.tp_order_id = tp_resp.get("order_id", "")
            except Exception as e:
                console.print(f"[yellow]TP order failed — will monitor in memory: {e}[/yellow]")
        console.print(
            f"[bold green]LIVE {side}[/bold green] {qty} contracts @ ~{entry:.1f}  "
            f"SL={sl:.1f}  TP={tp:.1f} [dim]({tp_reason})[/dim]"
        )
    else:
        console.print(
            f"[bold green]PAPER {sig.direction.upper()}[/bold green] "
            f"{qty} BTC @ {entry:.1f}  SL={sl:.1f}  TP={tp:.1f} [dim]({tp_reason})[/dim]  "
            f"[dim]({sig.pattern} {sig.tf}m)[/dim]"
        )

    sc.open_positions.append(pos)
    if _FS:
        _fs.update_signal_status(sig.id, "triggered")
        _fs.save_position(_position_to_dict(pos), sc.uid)
    _save_state(sc)
    _notify_trade(sc,
        f"{'✅ LIVE' if _is_live(sc) else '📋 PAPER'} {sig.direction.upper()} opened\n"
        f"Pattern: {sig.pattern} {sig.tf}m\n"
        f"Entry: {entry:.1f}  SL: {sl:.1f}  TP: {tp:.1f}"
    )


# ── position monitoring ───────────────────────────────────────────────────────

def _trail_offset(sc: "_Scanner") -> int:
    return max(1, int(sc.settings.get("trail_offset", 50)))

def _lookback_candles(sc: "_Scanner") -> int:
    return max(1, int(sc.settings.get("lookback_candles", 3)))

def _entry_mode(sc: "_Scanner") -> str:
    return sc.settings.get("entry_mode", "immediate")


def _trail_sl(pos: Position, current_price: float, offset: int = 50) -> float:
    """
    Compute the new trailing SL price after partial TP.
    SL = entry ± offset + floor((price - anchor) / 100) × offset.
    Only ever moves in the trade's favour (ratchets, never reverses).
    """
    if pos.trail_anchor is None:
        return pos.sl
    if pos.direction == "long":
        steps = max(0, int((current_price - pos.trail_anchor) / 100))
        new_sl = round(pos.entry_price + offset + steps * offset, 2)
        return max(pos.sl, new_sl)
    else:
        steps = max(0, int((pos.trail_anchor - current_price) / 100))
        new_sl = round(pos.entry_price - offset - steps * offset, 2)
        return min(pos.sl, new_sl)


def _update_live_sl(sc: _Scanner, pos: Position, new_sl: float) -> None:
    try:
        broker = sc.broker
        remaining = int(pos.qty) // 2 if pos.partial_closed else int(pos.qty)
        stop_side = "SELL" if pos.direction == "long" else "BUY"
        if pos.sl_order_id:
            try:
                broker.cancel_order(pos.sl_order_id)
            except Exception as ce:
                console.print(f"[dim]SL cancel warning: {ce}[/dim]")
        limit_sl = round(new_sl * 0.995 if pos.direction == "long" else new_sl * 1.005, 2)
        resp = broker.place_stop_limit_order(stop_side, _qty_str(remaining), new_sl, limit_sl)
        pos.sl_order_id = resp.get("order_id", "")
    except Exception as e:
        console.print(f"[red]SL order update error: {e}[/red]")


def _partial_close(sc: _Scanner, pos: Position, price: float) -> None:
    half_contracts = int(pos.qty) // 2
    pnl_pts = price - pos.entry_price if pos.direction == "long" else pos.entry_price - price
    contract_size = sc.broker.contract_size if sc.broker else config.COINBASE_CONTRACT_SIZE
    pos.partial_pnl = round(pnl_pts * half_contracts * contract_size, 4)
    pos.partial_closed = True
    pos.trail_anchor = price
    old_sl  = pos.sl
    offset  = _trail_offset(sc)
    new_sl  = round(pos.entry_price + offset if pos.direction == "long" else pos.entry_price - offset, 2)
    pos.sl  = new_sl

    console.print(
        f"[bold cyan]PARTIAL TP {pos.direction.upper()}[/bold cyan] "
        f"@ {price:.1f}  half={half_contracts} contracts  PnL={pos.partial_pnl:+.4f}  "
        f"SL: {old_sl:.1f} → {new_sl:.1f}  (trailing begins, offset={offset}pts)"
    )

    partial_result = TradeResult(
        position=pos, close_price=price, close_reason="tp_partial",
        closed_at=datetime.now(timezone.utc),
        qty_closed=half_contracts, pnl_closed=pos.partial_pnl,
        mode=_trading_mode(sc),
    )
    _append_history(sc, partial_result)
    if _FS:
        _fs.save_position(_position_to_dict(pos), sc.uid)
        _fs.save_history(_result_to_dict(partial_result), f"{pos.signal_id}_partial", sc.uid)

    if _is_live(sc):
        try:
            broker = sc.broker
            stop_side = "SELL" if pos.direction == "long" else "BUY"
            if not pos.tp_order_id:
                # TP order not placed (or failed) — close half at market
                broker.place_market_order(stop_side, _qty_str(half_contracts))
            if pos.tp_order_id:
                # TP order already filled broker-side — cancel it (cleanup)
                try:
                    broker.cancel_order(pos.tp_order_id)
                except Exception:
                    pass
                pos.tp_order_id = None
            if pos.sl_order_id:
                try:
                    broker.cancel_order(pos.sl_order_id)
                except Exception as ce:
                    console.print(f"[dim]SL cancel warning: {ce}[/dim]")
            limit_sl = round(new_sl * 0.995 if pos.direction == "long" else new_sl * 1.005, 2)
            resp = broker.place_stop_limit_order(stop_side, _qty_str(half_contracts), new_sl, limit_sl)
            pos.sl_order_id = resp.get("order_id", "")
        except Exception as e:
            console.print(f"[red]Partial close order error: {e}[/red]")


def _notify_trade(sc: _Scanner, message: str) -> None:
    chat_id = sc.settings.get("telegram_chat_id", "")
    if chat_id:
        from btc_agent.notifiers import send_trade_alert
        import threading as _t
        _t.Thread(target=send_trade_alert, args=(chat_id, message), daemon=True).start()


def _close_position(sc: _Scanner, pos: Position, price: float, reason: str) -> None:
    remaining = int(pos.qty) // 2 if pos.partial_closed else int(pos.qty)
    pnl_pts = price - pos.entry_price if pos.direction == "long" else pos.entry_price - price
    remain_pnl = round(pnl_pts * remaining * sc.broker.contract_size, 4)
    pos.pnl = round(pos.partial_pnl + remain_pnl, 4)
    pos.status = f"closed_{reason}"

    color = "green" if reason == "tp" else "red"
    partial_note = f"  partial={pos.partial_pnl:+.4f}  remain={remain_pnl:+.4f}" if pos.partial_closed else ""
    console.print(
        f"[{color}]CLOSE {pos.direction.upper()} ({reason.upper()})[/{color}] "
        f"@ {price:.1f}  {remaining} contracts{partial_note}  Total={pos.pnl:+.4f}"
    )

    if _is_live(sc):
        try:
            broker = sc.broker
            if pos.sl_order_id:
                try:
                    broker.cancel_order(pos.sl_order_id)
                except Exception:
                    pass
            if pos.tp_order_id:
                try:
                    broker.cancel_order(pos.tp_order_id)
                except Exception:
                    pass
                pos.tp_order_id = None
            stop_side = "SELL" if pos.direction == "long" else "BUY"
            broker.place_market_order(stop_side, _qty_str(remaining))
        except Exception as e:
            console.print(f"[red]Close order error: {e}[/red]")

    close_result = TradeResult(
        position=pos, close_price=price, close_reason=reason,
        closed_at=datetime.now(timezone.utc),
        qty_closed=remaining, pnl_closed=remain_pnl,
        mode=_trading_mode(sc),
    )
    _append_history(sc, close_result)
    if _FS:
        _fs.save_position(_position_to_dict(pos), sc.uid)
        _fs.save_history(_result_to_dict(close_result), f"{pos.signal_id}_{reason}", sc.uid)

    emoji = "🎯" if reason == "tp" else "🛑" if reason == "sl" else "🔄"
    _notify_trade(sc,
        f"{emoji} {pos.direction.upper()} closed ({reason.upper()})\n"
        f"Entry: {pos.entry_price:.1f}  Exit: {price:.1f}\n"
        f"PnL: {pos.pnl:+.4f}"
    )

    # Reset the signal to pending so it can re-enter if price comes back within the entry window
    now_utc = datetime.now(timezone.utc)
    for sig in sc.pending_signals:
        if sig.id == pos.signal_id and sig.status == "triggered" and now_utc < sig.expires_at:
            sig.status = "pending"
            if _FS:
                _fs.update_signal_status(sig.id, "pending")
            break


def _monitor_positions(sc: _Scanner, current_price: float) -> None:
    offset = _trail_offset(sc)
    _oi_cache = sc._oi_signals_cache
    if _oi_filter_enabled(sc) and _oi_cache is not None and _oi_cache.ok:
        for _pos in sc.open_positions:
            if _pos.status != "open":
                continue
            if _pos.direction == "long" and _oi_cache.bear_div:
                _new_sl = round(_pos.entry_price + 50, 2)
                if _new_sl > _pos.sl:
                    console.print(f"[yellow]OI bear_div: LONG SL {_pos.sl:.1f} → {_new_sl:.1f}[/yellow]")
                    _pos.sl = _new_sl
                    if _is_live(sc):
                        _update_live_sl(sc, _pos, _new_sl)
            elif _pos.direction == "short" and _oi_cache.bull_div:
                _new_sl = round(_pos.entry_price - 50, 2)
                if _new_sl < _pos.sl:
                    console.print(f"[yellow]OI bull_div: SHORT SL {_pos.sl:.1f} → {_new_sl:.1f}[/yellow]")
                    _pos.sl = _new_sl
                    if _is_live(sc):
                        _update_live_sl(sc, _pos, _new_sl)
    for pos in sc.open_positions:
        if pos.status != "open":
            continue

        # ── DEPO position management ──────────────────────────────────────────
        if pos.depo_line:
            # Stage 1: 500pts in favor → SL to entry ± 100 (breakeven+)
            if not pos.depo_be_done:
                pts_favor = (current_price - pos.entry_price if pos.direction == "long"
                             else pos.entry_price - current_price)
                if pts_favor >= 500:
                    be_sl = round(pos.entry_price + 100 if pos.direction == "long"
                                  else pos.entry_price - 100, 2)
                    if (pos.direction == "long" and be_sl > pos.sl) or \
                       (pos.direction == "short" and be_sl < pos.sl):
                        pos.sl = be_sl
                        pos.depo_be_done = True
                        console.print(f"[cyan]DEPO BE SL {pos.direction} → {be_sl:.1f}[/cyan]")
                        if _is_live(sc):
                            _update_live_sl(sc, pos, be_sl)

            # Stage 2: TP1 at 950pts → 50% partial, SL fixed at entry ± 500
            if pos.depo_tp1 and not pos.partial_closed:
                tp1_hit = (pos.direction == "long"  and current_price >= pos.depo_tp1) or \
                          (pos.direction == "short" and current_price <= pos.depo_tp1)
                if tp1_hit:
                    _partial_close(sc, pos, current_price)
                    fixed_sl = round(pos.entry_price + 500 if pos.direction == "long"
                                     else pos.entry_price - 500, 2)
                    pos.sl = fixed_sl
                    pos.trail_anchor = None  # disable trail — SL stays fixed
                    console.print(f"[cyan]DEPO TP1 partial @ {current_price:.1f}, SL fixed → {fixed_sl:.1f}[/cyan]")
                    if _is_live(sc):
                        _update_live_sl(sc, pos, fixed_sl)
                    continue

            # SL check for all DEPO trades
            hit_sl = (pos.direction == "long"  and current_price <= pos.sl) or \
                     (pos.direction == "short" and current_price >= pos.sl)
            if hit_sl:
                _close_position(sc, pos, current_price, "sl")
                continue

            # After TP1: fixed SL, wait for next DEPO (pos.tp = depo_tp2)
            if pos.partial_closed:
                hit_tp2 = (pos.direction == "long"  and current_price >= pos.tp) or \
                          (pos.direction == "short" and current_price <= pos.tp)
                if hit_tp2:
                    _close_position(sc, pos, current_price, "tp")
            continue  # skip regular logic for all DEPO positions

        # ── Regular (non-DEPO) monitor logic ─────────────────────────────────
        if not pos.partial_closed:
            hit_tp = (pos.direction == "long"  and current_price >= pos.tp) or \
                     (pos.direction == "short" and current_price <= pos.tp)
            hit_sl = (pos.direction == "long"  and current_price <= pos.sl) or \
                     (pos.direction == "short" and current_price >= pos.sl)
            if hit_tp:
                if pos.tf < 30 or pos.pattern == "BSG":
                    _close_position(sc, pos, current_price, "tp")
                else:
                    _partial_close(sc, pos, current_price)
            elif hit_sl:
                _close_position(sc, pos, current_price, "sl")
        else:
            new_sl = _trail_sl(pos, current_price, offset)
            if new_sl != pos.sl:
                console.print(f"[dim]Trail SL {pos.direction} {pos.sl:.1f} → {new_sl:.1f}[/dim]")
                if _is_live(sc):
                    _update_live_sl(sc, pos, new_sl)
                pos.sl = new_sl
            hit_sl = (pos.direction == "long"  and current_price <= pos.sl) or \
                     (pos.direction == "short" and current_price >= pos.sl)
            if hit_sl:
                _close_position(sc, pos, current_price, "sl")
    _save_state(sc)


# ── state persistence ─────────────────────────────────────────────────────────

def _signal_to_dict(s: Signal, max_sl: float = 500.0, bias_note: str = "") -> dict:
    sl_dist = abs(s.entry_trigger - s.sl_wick)
    if sl_dist > max_sl:
        note = f"SL {sl_dist:.0f}pts > {max_sl:.0f}pt limit — avoiding entry"
    else:
        note = bias_note
    return {
        "id": s.id, "pattern": s.pattern, "direction": s.direction,
        "tf": s.tf, "bar_open_time": s.bar_open_time,
        "entry_trigger": s.entry_trigger,
        "sl_wick": s.sl_wick, "sl_body": s.sl_body,
        "created_at": s.created_at.isoformat(),
        "expires_at": s.expires_at.isoformat(),
        "status": s.status,
        "meta": s.meta,
        "note": note,
    }


def _position_to_dict(p: Position) -> dict:
    remaining_qty = int(p.qty) // 2 if p.partial_closed else int(p.qty)
    return {
        "signal_id": p.signal_id, "entry_price": p.entry_price,
        "sl": p.sl, "tp": p.tp, "qty": p.qty, "direction": p.direction,
        "opened_at": p.opened_at.isoformat(),
        "pattern": p.pattern, "tf": p.tf,
        "status": p.status, "pnl": p.pnl,
        "coinbase_order_id": p.coinbase_order_id,
        "tp_reason": p.tp_reason,
        "partial_closed": p.partial_closed,
        "trail_anchor": p.trail_anchor,
        "partial_pnl": p.partial_pnl,
        "remaining_qty": remaining_qty,
        "contract_size": config.COINBASE_CONTRACT_SIZE,
        "sl_order_id": p.sl_order_id,
        "tp_order_id": p.tp_order_id,
        "depo_line":   p.depo_line,
        "depo_tp1":    p.depo_tp1,
        "depo_tp2":    p.depo_tp2,
        "depo_be_done": p.depo_be_done,
        "compression_tf":             p.compression_tf,
        "compression_4h_poc":         p.compression_4h_poc,
        "compression_last_bar_time":  p.compression_last_bar_time,
    }


def _result_to_dict(r: TradeResult) -> dict:
    return {
        "position":    _position_to_dict(r.position),
        "close_price": r.close_price,
        "close_reason": r.close_reason,
        "closed_at":   r.closed_at.isoformat(),
        "qty_closed":  r.qty_closed,
        "pnl_closed":  r.pnl_closed,
        "mode":        r.mode,
    }


def _dict_to_position(d: dict) -> Position:
    return Position(
        signal_id=d["signal_id"], entry_price=d["entry_price"],
        sl=d["sl"], tp=d["tp"], qty=d["qty"], direction=d["direction"],
        opened_at=datetime.fromisoformat(d["opened_at"]),
        pattern=d.get("pattern", ""), tf=d.get("tf", 0),
        status=d["status"], pnl=d.get("pnl"),
        coinbase_order_id=d.get("coinbase_order_id"),
        tp_reason=d.get("tp_reason", ""),
        partial_closed=d.get("partial_closed", False),
        trail_anchor=d.get("trail_anchor"),
        partial_pnl=d.get("partial_pnl", 0.0),
        sl_order_id=d.get("sl_order_id"),
        tp_order_id=d.get("tp_order_id"),
        depo_line=d.get("depo_line"),
        depo_tp1=d.get("depo_tp1"),
        depo_tp2=d.get("depo_tp2"),
        depo_be_done=d.get("depo_be_done", False),
        compression_tf=d.get("compression_tf"),
        compression_4h_poc=d.get("compression_4h_poc"),
        compression_last_bar_time=d.get("compression_last_bar_time"),
    )


def _load_state(sc: _Scanner) -> None:
    """Restore in-memory state from Firestore on scanner startup."""
    if not _FS:
        return
    state = _fs.load_state(sc.uid)
    if not state:
        return

    now = datetime.now(timezone.utc)
    restored_sigs, restored_pos, restored_hist = 0, 0, 0

    for d in state.get("signals", []):
        try:
            expires_at = datetime.fromisoformat(d["expires_at"])
            if expires_at < now:
                continue
            sc.pending_signals.append(Signal(
                id=d["id"], pattern=d["pattern"], direction=d["direction"],
                tf=d["tf"], bar_open_time=d["bar_open_time"],
                entry_trigger=d["entry_trigger"],
                sl_wick=d["sl_wick"], sl_body=d["sl_body"],
                created_at=datetime.fromisoformat(d["created_at"]),
                expires_at=expires_at, status=d["status"],
            ))
            restored_sigs += 1
        except Exception as e:
            console.print(f"[dim yellow]Skipping malformed signal: {e}[/dim yellow]")

    for d in state.get("positions", []):
        try:
            sc.open_positions.append(_dict_to_position(d))
            restored_pos += 1
        except Exception as e:
            console.print(f"[dim yellow]Skipping malformed position: {e}[/dim yellow]")

    for d in state.get("history", []):
        try:
            sc.trade_history.append(TradeResult(
                position=_dict_to_position(d["position"]),
                close_price=d["close_price"],
                close_reason=d["close_reason"],
                closed_at=datetime.fromisoformat(d["closed_at"]),
                qty_closed=d.get("qty_closed", 0.0),
                pnl_closed=d.get("pnl_closed", 0.0),
                mode=d.get("mode", "paper"),
            ))
            restored_hist += 1
        except Exception as e:
            console.print(f"[dim yellow]Skipping malformed history entry: {e}[/dim yellow]")

    if restored_sigs or restored_pos or restored_hist:
        console.print(
            f"[green]Restored from Firestore:[/green] "
            f"{restored_sigs} signals · {restored_pos} positions · {restored_hist} history"
        )


def _save_state(sc: _Scanner, wait: bool = False) -> None:
    sc.state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "signals":   [_signal_to_dict(s, _max_sl(sc)) for s in sc.pending_signals],
        "positions": [_position_to_dict(p) for p in sc.open_positions],
        "history":   [_result_to_dict(r) for r in sc.trade_history[-50:]],
        "running":   sc.running,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    def _write():
        try:
            sc.state_path.write_text(json.dumps(state, indent=2))
        except Exception as e:
            console.print(f"[yellow]State save failed: {e}[/yellow]")
    t = threading.Thread(target=_write, daemon=True)
    t.start()
    if wait:
        t.join(timeout=5)


def get_state(uid: str | None = None) -> dict:
    """Return current in-memory state for the web API."""
    sc = _scanners.get(uid) if uid else None

    if sc is not None and sc.running and sc.thread is not None and not sc.thread.is_alive():
        console.print(f"[yellow]Watchdog: scanner thread for {uid[:8]} is dead — resetting state[/yellow]")
        sc.running = False
        sc.thread = None
        if _FS:
            _fs.save_user_prefs(uid, {"scanner_running": False})

    if sc is None:
        return {
            "signals": [], "positions": [], "history": [],
            "running": False, "current_price": 0.0, "levels": {},
            "current_regime": {},
            "settings": {
                "mode":              config.TRADING_MODE,
                "tf_min":            config.TRADING_TF_MIN,
                "tf_max":            config.TRADING_TF_MAX,
                "scan_interval_min": config.TRADING_SCAN_INTERVAL_MIN,
                "qty":               config.TRADING_QTY,
                "max_sl":            config.TRADING_MAX_SL,
                "min_tp":            config.TRADING_MIN_TP,
                "max_concurrent":    config.TRADING_MAX_CONCURRENT,
                "patterns":          config.TRADING_PATTERNS,
                "depo_entry_filter":   config.DEPO_ENTRY_FILTER,
                "poc_entry_filter":    config.POC_ENTRY_FILTER,
                "compression_enabled": config.COMPRESSION_ENABLED,
            },
        }

    def _bias_note(s: Signal) -> str:
        if not _bias_filter_enabled(sc) or not sc.current_bias:
            return ""
        allowed = "long" if "bullish" in sc.current_bias else "short"
        return f"Bias {sc.current_bias} — entry skipped" if s.direction != allowed else ""

    return {
        "signals":   [_signal_to_dict(s, _max_sl(sc), _bias_note(s)) for s in sc.pending_signals],
        "positions": [_position_to_dict(p) for p in sc.open_positions],
        "history":   [_result_to_dict(r) for r in sc.trade_history[-50:]],
        "running":       sc.running,
        "current_price": sc.last_price,
        "current_bias":        sc.current_bias,
        "broker_account_name": sc.broker_account_name,
        "levels":              sc.current_levels,
        "current_regime":      sc.current_regime,
        "bsg_alerts":          sc.bsg_alerts[-2:],
        "settings": {
            "mode":              _trading_mode(sc),
            "tf_min":            _tf_min(sc),
            "tf_max":            _tf_max(sc),
            "scan_interval_min": _scan_interval(sc),
            "qty":               _trading_qty(sc),
            "max_sl":            _max_sl(sc),
            "min_tp":            _min_tp(sc),
            "max_concurrent":    _max_concurrent(sc),
            "patterns":          _active_patterns(sc),
            "bias_filter":       _bias_filter_enabled(sc),
            "trail_offset":      _trail_offset(sc),
            "lookback_candles":  _lookback_candles(sc),
            "entry_mode":        _entry_mode(sc),
            "broker_nickname":   sc.settings.get("broker_nickname", ""),
            "bsg_enabled":       _bsg_enabled(sc),
            "bsg_trade_enabled": _bsg_trade_enabled(sc),
            "cme_close_skip":           _cme_close_skip_enabled(sc),
            "daily_pts_target":         float(sc.settings.get("daily_pts_target") or 0) or config.TRADING_DAILY_PTS_TARGET,
            "daily_sl_pts":             float(sc.settings.get("daily_sl_pts") or 0) or config.TRADING_DAILY_SL_PTS,
            "daily_sl_limit":           int(sc.settings.get("daily_sl_limit") or 0) or config.TRADING_DAILY_SL_LIMIT,
            "opposite_signal_action":   _opposite_signal_action(sc),
            "oi_filter_enabled":        _oi_filter_enabled(sc),
            "oi_threshold_mult":        _oi_threshold_mult(sc),
            "oi_lookback_bars":         _oi_lookback_bars(sc),
            "oi_div_lookback":          _oi_div_lookback(sc),
            "oi_tf":                    _oi_tf(sc),
            "depo_entry_filter":        _depo_entry_filter_enabled(sc),
            "poc_entry_filter":         _poc_entry_filter_enabled(sc),
            "compression_enabled":      _compression_enabled(sc),
        },
    }


# ── public API ────────────────────────────────────────────────────────────────

def _clear_on_stop(sc: _Scanner) -> None:
    """Move all open positions to history as 'stopped_by_user'. No PnL calculated."""
    now = datetime.now(timezone.utc)
    price = sc.last_price or 0.0
    for pos in list(sc.open_positions):
        if pos.status != "open":
            continue
        pos.status = "closed_stopped_by_user"
        close_result = TradeResult(
            position=pos, close_price=price, close_reason="stopped_by_user",
            closed_at=now, qty_closed=int(pos.qty), pnl_closed=0.0,
            mode=_trading_mode(sc),
        )
        _append_history(sc, close_result)
        if _FS:
            _fs.save_position(_position_to_dict(pos), sc.uid)
            _fs.save_history(_result_to_dict(close_result), f"{pos.signal_id}_stopped", sc.uid)
        console.print(f"[yellow]Position {pos.signal_id[:8]} moved to history (stopped_by_user)[/yellow]")
    sc.open_positions.clear()
    sc.pending_signals.clear()


def stop_trading_scanner(uid: str) -> None:
    sc = _scanners.get(uid)
    if sc:
        _clear_on_stop(sc)
        sc.running = False
        if _FS:
            _fs.save_user_prefs(uid, {"scanner_running": False})


def is_any_running() -> bool:
    with _scanners_lock:
        return any(sc.running for sc in _scanners.values())


def get_any_price() -> float | None:
    with _scanners_lock:
        return next((sc.last_price for sc in _scanners.values() if sc.last_price), None)


_PRICE_TICK_S = 2


def run_trading_scanner(uid: str, user_settings: dict | None = None, email: str = "") -> None:
    sc = _get_or_create(uid)  # acquires+releases lock internally
    with _scanners_lock:       # re-acquire for atomic check-and-set
        if sc.running:
            return
        sc.running = True
        sc.thread = threading.current_thread()
    try:
        if email:
            sc.user_email = email
        if user_settings:
            sc.settings.update(user_settings)
        sc.trade_history.clear()
        sc.pending_signals.clear()
        sc.open_positions.clear()
        _load_state(sc)
    except Exception as e:
        sc.running = False
        console.print(f"[red]Scanner setup failed: {e}[/red]")
        return
    if _FS:
        _fs.save_user_prefs(uid, {"scanner_running": True})
    console.rule("[bold green]Trading Scanner started[/bold green]")
    if sc.user_email:
        console.print(f"[dim]----------{sc.user_email}----------[/dim]")
    mode = _trading_mode(sc)
    qty = _trading_qty(sc)
    console.print(
        f"Mode=[bold]{mode.upper()}[/bold]  TF={_tf_min(sc)}–{_tf_max(sc)}m  "
        f"ScanInterval={_scan_interval(sc)}min  PriceTick={_PRICE_TICK_S}s  "
        f"Qty={qty} contracts  MaxSL={_max_sl(sc)}  MinTP={_min_tp(sc)}  "
        f"MaxConcurrent={_max_concurrent(sc)}"
    )
    if qty < 2:
        console.print("[yellow]Warning: qty < 2 — partial close requires at least 2 contracts[/yellow]")

    try:
        sc.broker = _build_broker(sc)
    except Exception as e:
        console.print(f"[red]Broker init failed: {e}[/red]")
        sc.running = False
        return
    if sc.broker and _is_live(sc):
        try:
            sc.broker_account_name = sc.broker.get_display_name()
        except Exception:
            sc.broker_account_name = ""

    try:
        from btc_agent.scanner.markov_regime import refresh_regime_blocking
        _r = refresh_regime_blocking()
        if _r and not _r.get("error"):
            sc.current_regime = _r
    except Exception as _re:
        console.print(f"[dim yellow]Regime init skipped: {_re}[/dim yellow]")

    arr = ts_arr = minutes_of_day = unix_days = None
    last_state_save = datetime.now(timezone.utc)

    try:
        while sc.running:
            tick_start = datetime.now(timezone.utc)
            now = tick_start

            try:
                current_price = fetch_current_price()
                sc.last_price = current_price
            except Exception as e:
                console.print(f"[red]Price tick error: {e}[/red]")
                time.sleep(_PRICE_TICK_S)
                continue

            _monitor_positions(sc, current_price)
            _tick_vishal(sc, current_price, now)

            # Prune dead signals and closed positions so lists never grow unboundedly
            sc.pending_signals = [s for s in sc.pending_signals if s.status == "pending"]
            sc.open_positions  = [p for p in sc.open_positions  if p.status == "open"]

            emode = _entry_mode(sc)
            for sig in sc.pending_signals:
                if sig.status != "pending":
                    continue
                if emode == "candle_close":
                    bar_dt = datetime.fromisoformat(sig.bar_open_time.replace('Z', ''))
                    if bar_dt.tzinfo is None:
                        bar_dt = bar_dt.replace(tzinfo=timezone.utc)
                    effective_expiry = bar_dt + timedelta(minutes=(_lookback_candles(sc) + 1) * sig.tf)
                    if datetime.now(timezone.utc) > effective_expiry:
                        sig.status = "expired"
                        if _FS: _fs.update_signal_status(sig.id, "expired")
                        console.print(f"[dim]Signal {sig.id} ({sig.pattern} {sig.tf}m) expired[/dim]")
                        continue
                else:
                    if now > sig.expires_at:
                        sig.status = "expired"
                        if _FS: _fs.update_signal_status(sig.id, "expired")
                        console.print(f"[dim]Signal {sig.id} ({sig.pattern} {sig.tf}m) expired[/dim]")
                        continue

                if _bias_filter_enabled(sc) and sc.current_bias:
                    allowed = "long" if "bullish" in sc.current_bias else "short"
                    if sig.direction != allowed:
                        continue  # bias mismatch — keep signal pending, skip entry

                if emode == "immediate":
                    if sig.direction == "long"  and current_price > sig.entry_trigger:
                        _execute_entry(sc, sig, current_price)
                    elif sig.direction == "short" and current_price < sig.entry_trigger:
                        _execute_entry(sc, sig, current_price)
                else:  # candle_close
                    bar_dt = datetime.fromisoformat(sig.bar_open_time.replace('Z', ''))
                    if bar_dt.tzinfo is None:
                        bar_dt = bar_dt.replace(tzinfo=timezone.utc)
                    candle_close_dt = bar_dt + timedelta(minutes=(_lookback_candles(sc) + 1) * sig.tf)
                    if datetime.now(timezone.utc) >= candle_close_dt:
                        if sig.direction == "long"  and current_price > sig.entry_trigger:
                            _execute_entry(sc, sig, current_price)
                        elif sig.direction == "short" and current_price < sig.entry_trigger:
                            _execute_entry(sc, sig, current_price)

            # BSG: fire once per 15m bar close, independent of scan_interval
            _bsg_bar_ts = (int(now.timestamp()) // (_BSG_TF * 60) - 1) * _BSG_TF * 60
            _bsg_bar_iso = datetime.fromtimestamp(_bsg_bar_ts, tz=timezone.utc).isoformat()
            if _bsg_bar_iso != sc.bsg_last_bar and (_bsg_enabled(sc) or _bsg_trade_enabled(sc)):
                try:
                    _df_bsg = fetch_1m_candles()
                    _ba, _bt, _bm, _bu = df_to_numpy(_df_bsg)
                    _tick_bsg(sc, _ba, _bt, _bm, _bu)
                    sc.bsg_last_bar = _bsg_bar_iso
                except Exception as e:
                    console.print(f"[red]BSG bar tick error: {e}[/red]")

            elapsed_min = (now - sc.last_scan_time).total_seconds() / 60 if sc.last_scan_time else 999
            if elapsed_min >= _scan_interval(sc):
                try:
                    df = fetch_1m_candles()
                    arr, ts_arr, minutes_of_day, unix_days = df_to_numpy(df)
                    sc.current_levels = compute_levels(df, weekly_adj=config.WEEKLY_ADJ)
                    _dl = _get_depo_lines()
                    _above = _dl[_dl > current_price]
                    _below = _dl[_dl < current_price]
                    sc.current_levels["depo_upper"] = float(_above.min()) if len(_above) else None
                    sc.current_levels["depo_lower"] = float(_below.max()) if len(_below) else None
                    bias = _trend_bias(current_price, sc.current_levels)
                    sc.current_bias = bias
                    mrp_str  = f"{sc.current_levels['mrp']:.1f}"       if sc.current_levels.get("mrp")       else "—"
                    dpoc_str = f"{sc.current_levels['daily_poc']:.1f}"  if sc.current_levels.get("daily_poc")  else "—"
                    wpoc_str = f"{sc.current_levels['weekly_poc']:.1f}" if sc.current_levels.get("weekly_poc") else "—"
                    console.print(
                        f"[dim]Levels — MRP={mrp_str}  DailyPOC={dpoc_str}  "
                        f"WeeklyPOC={wpoc_str}  Trend: {bias}[/dim]"
                    )
                    console.print(
                        f"[cyan]Scanning {_tf_min(sc)}–{_tf_max(sc)}m "
                        f"({', '.join(_active_patterns(sc))})…[/cyan]"
                    )
                    new_sigs = _scan_patterns(sc, arr, ts_arr, minutes_of_day, unix_days)
                    if _compression_enabled(sc):
                        new_sigs += _check_compression(sc, arr, ts_arr, minutes_of_day, unix_days, now)
                    if new_sigs and _bias_filter_enabled(sc):
                        allowed = "long" if "bullish" in bias else "short"
                        filtered = [s for s in new_sigs if s.direction != allowed]
                        for s in filtered:
                            console.print(f"[dim]Bias filter dropped {s.direction} {s.pattern} ({bias})[/dim]")
                        new_sigs = [s for s in new_sigs if s.direction == allowed]
                    depo_on = _depo_entry_filter_enabled(sc)
                    poc_on  = _poc_entry_filter_enabled(sc)
                    if new_sigs and (depo_on or poc_on):
                        d_poc  = sc.current_levels.get("daily_poc")
                        w_poc  = sc.current_levels.get("weekly_poc")
                        h4_poc = sc.current_levels.get("4h_poc")
                        def _passes(s) -> bool:
                            if s.pattern == "Compression":
                                return True  # already requires all 3 POCs — exempt from DEPO/POC filter
                            lo, hi = s.meta.get("bar_low", 0), s.meta.get("bar_high", float("inf"))
                            has_depo = depo_on and s.meta.get("depo_line") is not None
                            has_poc  = poc_on and bool(
                                d_poc and w_poc and h4_poc
                                and lo <= d_poc  <= hi
                                and lo <= w_poc  <= hi
                                and lo <= h4_poc <= hi
                            )
                            return has_depo or has_poc
                        pre = len(new_sigs)
                        new_sigs = [s for s in new_sigs if _passes(s)]
                        dropped = pre - len(new_sigs)
                        if dropped:
                            active = [n for n, f in [("DEPO", depo_on), ("POC", poc_on)] if f]
                            console.print(f"[dim]{' or '.join(active)} entry filter dropped {dropped} signal(s)[/dim]")
                    if _oi_filter_enabled(sc):
                        try:
                            from btc_agent.scanner.oi_data import fetch_oi_snapshot, compute_oi_signals
                            _snap = fetch_oi_snapshot(_oi_tf(sc), lookback=_oi_lookback_bars(sc))
                            _oi_bars, _ = aggregate_tf(arr, ts_arr, minutes_of_day, unix_days,
                                                       _oi_tf(sc), last_n=_oi_lookback_bars(sc))
                            _closes = [float(b[3]) for b in _oi_bars] if (_oi_bars is not None and len(_oi_bars)) else []
                            _oi_sigs = compute_oi_signals(_snap, _closes,
                                                          mult=_oi_threshold_mult(sc),
                                                          div_lookback=_oi_div_lookback(sc))
                            sc._oi_signals_cache = _oi_sigs
                            if new_sigs and _oi_sigs.ok and not (_oi_sigs.large_oi_up or _oi_sigs.large_oi_down):
                                for s in new_sigs:
                                    s.meta["skip_reason"] = "oi_no_confirm"
                                console.print(f"[dim]OI filter: no large spike — dropped {len(new_sigs)} signal(s)[/dim]")
                                new_sigs = []
                        except Exception as _oi_e:
                            console.print(f"[yellow]OI filter skipped: {_oi_e}[/yellow]")
                    if new_sigs:
                        sc.pending_signals.extend(new_sigs)
                        if _FS:
                            for sig in new_sigs:
                                _fs.save_signal(_signal_to_dict(sig), sc.uid)
                    _tick_bsg(sc, arr, ts_arr, minutes_of_day, unix_days)
                    _check_compression_exits(sc, arr, ts_arr, minutes_of_day, unix_days, current_price)
                    sc.last_scan_time = now
                except Exception as e:
                    console.print(f"[red]Pattern scan error: {e}[/red]")

            if (datetime.now(timezone.utc) - last_state_save).total_seconds() >= 60:
                _save_state(sc)
                last_state_save = datetime.now(timezone.utc)

            elapsed_s = (datetime.now(timezone.utc) - tick_start).total_seconds()
            time.sleep(max(0, _PRICE_TICK_S - elapsed_s))

    except KeyboardInterrupt:
        console.print("\n[yellow]Trading scanner stopped.[/yellow]")
    finally:
        _clear_on_stop(sc)
        sc.running = False
        _save_state(sc, wait=True)
        if _FS:
            _fs.save_user_prefs(uid, {"scanner_running": False})
        with _scanners_lock:
            _scanners.pop(uid, None)
