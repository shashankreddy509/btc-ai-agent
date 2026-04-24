"""
Trading Scanner — scans 15m–90m TFs for 4-Flag and Engulfing patterns,
monitors the next candle for a body breakout, then executes a trade on Coinbase.

Entry logic:
  - Pattern found on candle X (current bar)
  - Next candle: if price > body_high(X) → long entry
                 if price < body_low(X)  → short entry
  - SL priority: wick → body → hard cap (TRADING_MAX_SL pts)
  - TP: nearest level (MRP / Daily POC / Weekly POC) in trade direction,
        with TRADING_MIN_TP floor fallback

Signal expires after 1 TF period (e.g. 30m pattern → signal live for 30 min).
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
from rich.console import Console

from btc_agent import config
from btc_agent.scanner.aggregator import aggregate_tf, df_to_numpy
from btc_agent.scanner.data import fetch_1m_candles, fetch_current_price
from btc_agent.scanner.levels import compute_levels
from btc_agent.scanner.patterns import detect_4flag, detect_engulfing
from btc_agent.trading.models import Position, Signal, TradeResult

console = Console()

_IST = timezone(timedelta(hours=5, minutes=30))
_STATE_PATH = Path(__file__).parent.parent / "data" / "trading_state.json"
_SETTINGS_PATH = Path(__file__).parent.parent / "data" / "trading_settings.json"

try:
    from btc_agent.trading import firestore_store as _fs
    _FS = True
except Exception:
    _fs = None  # type: ignore
    _FS = False

# ── module-level state (shared with web API) ──────────────────────────────────
pending_signals: list[Signal] = []
open_positions:  list[Position] = []
trade_history:   list[TradeResult] = []
_running = False
_last_scan_time: datetime | None = None
_current_levels: dict = {}
_last_price: float = 0.0


# ── settings (hot-reloadable from JSON) ──────────────────────────────────────

_settings_cache: dict = {}
_settings_mtime: float = 0.0


def _load_settings() -> dict:
    """Load runtime overrides from trading_settings.json, cached by mtime."""
    global _settings_cache, _settings_mtime
    if _SETTINGS_PATH.exists():
        try:
            mtime = _SETTINGS_PATH.stat().st_mtime
            if mtime != _settings_mtime:
                _settings_cache = json.loads(_SETTINGS_PATH.read_text())
                _settings_mtime = mtime
        except Exception:
            pass
    return _settings_cache


def _get(key: str, default):
    """Read setting: JSON file overrides .env/config."""
    return _load_settings().get(key, default)


def tf_min()            -> int:   return int(_get("tf_min",   config.TRADING_TF_MIN))
def tf_max()            -> int:   return int(_get("tf_max",   config.TRADING_TF_MAX))
def scan_interval()     -> int:   return int(_get("scan_interval_min", config.TRADING_SCAN_INTERVAL_MIN))
def trading_mode()      -> str:   return _get("mode",         config.TRADING_MODE)
def max_concurrent()    -> int:   return int(_get("max_concurrent",    config.TRADING_MAX_CONCURRENT))
def trading_qty()       -> int:   return int(_get("qty",      config.TRADING_QTY))
def max_sl()            -> float: return float(_get("max_sl", config.TRADING_MAX_SL))
def min_tp()            -> float: return float(_get("min_tp", config.TRADING_MIN_TP))
def active_patterns()   -> list:  return _get("patterns",     config.TRADING_PATTERNS)


def _qty_str(contracts: int) -> str:
    """Format integer contract count for Coinbase base_size field."""
    return str(int(contracts))


# ── SL calculation ────────────────────────────────────────────────────────────

def calc_sl(sl_wick: float) -> float:
    """SL is always the wick low/high of the pattern candle."""
    return round(sl_wick, 2)


# ── TP calculation using market structure levels ──────────────────────────────

def _calc_tp(direction: str, entry: float, levels: dict) -> tuple[float, str]:
    """
    Return (tp_price, tp_reason).
    Picks the nearest level (MRP / Daily POC / Weekly POC) in the trade direction.
    Enforces min_tp() floor; falls back to fixed 500 pts when no levels are ahead.
    """
    mrp        = levels.get("mrp")
    daily_poc  = levels.get("daily_poc")
    weekly_poc = levels.get("weekly_poc")

    candidates: list[tuple[float, str]] = []
    if direction == "long":
        for price, label in [(mrp, "MRP"), (daily_poc, "Daily POC"), (weekly_poc, "Weekly POC")]:
            if price and price > entry:
                candidates.append((price, label))
        tp_price, tp_reason = min(candidates, key=lambda x: x[0]) if candidates else (None, "")
    else:
        for price, label in [(mrp, "MRP"), (daily_poc, "Daily POC"), (weekly_poc, "Weekly POC")]:
            if price and price < entry:
                candidates.append((price, label))
        tp_price, tp_reason = max(candidates, key=lambda x: x[0]) if candidates else (None, "")

    if tp_price is None:
        fallback = entry + min_tp() if direction == "long" else entry - min_tp()
        return round(fallback, 2), "fixed_500"

    dist = tp_price - entry if direction == "long" else entry - tp_price
    if dist < min_tp():
        tp_price = entry + min_tp() if direction == "long" else entry - min_tp()
        tp_reason = f"{tp_reason}(min_floor)"
    elif dist > 500:
        tp_price = entry + 500 if direction == "long" else entry - 500
        tp_reason = "500_cap"

    return round(tp_price, 2), tp_reason


def _trend_bias(price: float, levels: dict) -> str:
    """Return a qualitative trend bias based on price vs all three levels."""
    above = sum([
        price > (levels.get("mrp") or 0),
        price > (levels.get("daily_poc") or 0),
        price > (levels.get("weekly_poc") or 0),
    ])
    if above == 3: return "strongly bullish"
    if above == 2: return "bullish"
    if above == 1: return "bearish"
    return "strongly bearish"


# ── signal creation ───────────────────────────────────────────────────────────

def _bars_to_signal(
    pattern: str,
    direction: str,
    tf: int,
    bars: np.ndarray,
    bar_open_time: str,
) -> Signal:
    """Extract price levels from the last bar and build a Signal."""
    o, h, l, c = bars[-1, 0], bars[-1, 1], bars[-1, 2], bars[-1, 3]
    body_hi = max(o, c)
    body_lo = min(o, c)
    now = datetime.now(timezone.utc)
    if pattern == "4-Flag":
        # Trigger = highest body_hi (long) or lowest body_lo (short) across all 4 flag candles
        flag_bars = bars[-4:]
        flag_body_his = np.maximum(flag_bars[:, 0], flag_bars[:, 3])
        flag_body_los = np.minimum(flag_bars[:, 0], flag_bars[:, 3])
        if direction == "long":
            entry_trigger = float(flag_body_his.max())
        else:
            entry_trigger = float(flag_body_los.min())
    else:
        # Engulfing: breakout above/below the body of the engulfing candle
        if direction == "long":
            entry_trigger = body_hi
        else:
            entry_trigger = body_lo
    if direction == "long":
        sl_wick = l
        sl_body = body_lo
    else:
        sl_wick = h
        sl_body = body_hi
    return Signal(
        id=uuid.uuid4().hex[:8],
        pattern=pattern,
        direction=direction,
        tf=tf,
        bar_open_time=bar_open_time,
        entry_trigger=round(entry_trigger, 2),
        sl_wick=round(sl_wick, 2),
        sl_body=round(sl_body, 2),
        created_at=now,
        expires_at=now + timedelta(minutes=tf),
    )


# ── pattern scan ──────────────────────────────────────────────────────────────

def _is_duplicate(tf: int, pattern: str, direction: str, bar_open_time: str) -> bool:
    """Return True if a non-expired signal for this exact bar already exists."""
    return any(
        s.status in ("pending", "triggered") and
        s.tf == tf and
        s.pattern == pattern and
        s.direction == direction and
        s.bar_open_time == bar_open_time
        for s in pending_signals
    )


def _scan_patterns(arr, ts_arr, minutes_of_day, unix_days) -> list[Signal]:
    """Scan all configured TFs and return new Signals for current-bar patterns."""
    new_signals: list[Signal] = []
    patterns = active_patterns()

    for tf in range(tf_min(), tf_max() + 1):
        bars, bar_open_times = aggregate_tf(
            arr, ts_arr, minutes_of_day, unix_days, tf, last_n=5
        )
        if bars is None or len(bars) < 2:
            continue

        bar_open_ts = int(bar_open_times[-1])
        bar_open_time = datetime.fromtimestamp(bar_open_ts, tz=timezone.utc).isoformat()

        if "4-Flag" in patterns and len(bars) >= 4:
            if detect_4flag(bars[-4:]):
                for direction in ("long", "short"):
                    if not _is_duplicate(tf, "4-Flag", direction, bar_open_time):
                        sig = _bars_to_signal("4-Flag", direction, tf, bars, bar_open_time)
                        new_signals.append(sig)
                        console.print(
                            f"[bold yellow]4-Flag[/bold yellow] detected on [green]{tf}m[/green] "
                            f"→ {direction.upper()}  trigger={sig.entry_trigger:.1f}"
                        )

        if "Engulfing" in patterns and len(bars) >= 2:
            found, eng_dir = detect_engulfing(bars[-2:])
            if found:
                direction = "long" if eng_dir == "bullish" else "short"
                if not _is_duplicate(tf, "Engulfing", direction, bar_open_time):
                    sig = _bars_to_signal("Engulfing", direction, tf, bars, bar_open_time)
                    new_signals.append(sig)
                    console.print(
                        f"[bold cyan]Engulfing ({direction})[/bold cyan] on [green]{tf}m[/green] "
                        f"→ {direction.upper()}  trigger={sig.entry_trigger:.1f}"
                    )

    return new_signals


# ── entry execution ───────────────────────────────────────────────────────────

def _execute_entry(sig: Signal, current_price: float) -> None:
    """Calculate SL/TP and open a position (paper or live)."""
    n_open = sum(1 for p in open_positions if p.status == "open")
    cap = max_concurrent()
    if cap > 0 and n_open >= cap:
        sig.status = "skipped"
        console.print(
            f"[yellow]Signal {sig.id} skipped — max concurrent ({cap}) reached[/yellow]"
        )
        if _FS: _fs.update_signal_status(sig.id, "skipped")
        _save_state()
        return

    entry = current_price
    sl = calc_sl(sig.sl_wick)
    sl_dist = abs(entry - sl)
    cap = max_sl()
    if sl_dist > cap:
        # Cap SL at max_sl from entry rather than rejecting — keeps the trade alive
        sl = round(entry - cap if sig.direction == "long" else entry + cap, 2)
        console.print(
            f"[dim yellow]Signal {sig.id} SL capped at {cap:.0f} pts (wick was {sl_dist:.0f} pts away)[/dim yellow]"
        )
    tp, tp_reason = _calc_tp(sig.direction, entry, _current_levels)
    qty = trading_qty()
    sig.status = "triggered"

    pos = Position(
        signal_id=sig.id,
        entry_price=entry,
        sl=sl,
        tp=tp,
        qty=qty,
        direction=sig.direction,
        opened_at=datetime.now(timezone.utc),
        pattern=sig.pattern,
        tf=sig.tf,
        tp_reason=tp_reason,
    )

    mode = trading_mode()
    if mode == "live":
        try:
            from btc_agent.trading.executor import (
                place_market_order,
                place_stop_limit_order,
            )
            side = "BUY" if sig.direction == "long" else "SELL"
            stop_side = "SELL" if sig.direction == "long" else "BUY"
            qty_str = _qty_str(qty)
            order = place_market_order(side, qty_str)
            pos.coinbase_order_id = order.get("order_id", "")
            # SL limit = 0.5% beyond stop to ensure fill
            limit_sl = round(sl * 0.995 if sig.direction == "long" else sl * 1.005, 2)
            sl_resp = place_stop_limit_order(stop_side, qty_str, sl, limit_sl)
            pos.sl_order_id = sl_resp.get("order_id", "")
            console.print(f"[bold green]LIVE {side}[/bold green] {qty} BTC @ ~{entry:.1f}  SL={sl:.1f}  TP={tp:.1f} [dim]({tp_reason})[/dim]")
        except Exception as e:
            console.print(f"[red]Coinbase order failed: {e}[/red]")
            sig.status = "pending"   # revert so we can retry
            return
    else:
        console.print(
            f"[bold green]PAPER {sig.direction.upper()}[/bold green] "
            f"{qty} BTC @ {entry:.1f}  SL={sl:.1f}  TP={tp:.1f} [dim]({tp_reason})[/dim]  "
            f"[dim]({sig.pattern} {sig.tf}m)[/dim]"
        )

    open_positions.append(pos)
    if _FS:
        _fs.update_signal_status(sig.id, "triggered")
        _fs.save_position(_position_to_dict(pos))
    _save_state()


# ── position monitoring ───────────────────────────────────────────────────────

def _trail_sl(pos: Position, current_price: float) -> float:
    """
    Compute the new trailing SL price after partial TP.
    SL = entry ± 50 + floor((price - anchor) / 100) × 50.
    Only ever moves in the trade's favour (ratchets, never reverses).
    """
    if pos.trail_anchor is None:
        return pos.sl
    if pos.direction == "long":
        steps = max(0, int((current_price - pos.trail_anchor) / 100))
        new_sl = round(pos.entry_price + 50 + steps * 50, 2)
        return max(pos.sl, new_sl)    # only ratchet up
    else:
        steps = max(0, int((pos.trail_anchor - current_price) / 100))
        new_sl = round(pos.entry_price - 50 - steps * 50, 2)
        return min(pos.sl, new_sl)    # only ratchet down


def _update_live_sl(pos: Position, new_sl: float) -> None:
    """Cancel the old Coinbase SL order and place a new one at the updated price."""
    try:
        from btc_agent.trading.executor import cancel_order, place_stop_limit_order
        remaining = int(pos.qty) // 2 if pos.partial_closed else int(pos.qty)
        qty_str   = _qty_str(remaining)
        stop_side = "SELL" if pos.direction == "long" else "BUY"
        if pos.sl_order_id:
            try:
                cancel_order(pos.sl_order_id)
            except Exception as ce:
                console.print(f"[dim]SL cancel warning: {ce}[/dim]")
        limit_sl = round(new_sl * 0.995 if pos.direction == "long" else new_sl * 1.005, 2)
        resp = place_stop_limit_order(stop_side, qty_str, new_sl, limit_sl)
        pos.sl_order_id = resp.get("order_id", "")
    except Exception as e:
        console.print(f"[red]SL order update error: {e}[/red]")


def _partial_close(pos: Position, price: float) -> None:
    """
    Sell half qty at TP1, move SL to entry ± 50, begin trailing.
    Works for both paper and live modes.
    """
    half_contracts = int(pos.qty) // 2
    pnl_pts        = price - pos.entry_price if pos.direction == "long" else pos.entry_price - price
    pos.partial_pnl   = round(pnl_pts * half_contracts * config.COINBASE_CONTRACT_SIZE, 4)
    pos.partial_closed = True
    pos.trail_anchor   = price
    old_sl = pos.sl
    new_sl = round(pos.entry_price + 50 if pos.direction == "long" else pos.entry_price - 50, 2)
    pos.sl = new_sl

    console.print(
        f"[bold cyan]PARTIAL TP {pos.direction.upper()}[/bold cyan] "
        f"@ {price:.1f}  half={half_contracts} contracts  PnL={pos.partial_pnl:+.4f}  "
        f"SL: {old_sl:.1f} → {new_sl:.1f}  (trailing begins)"
    )

    _partial_result = TradeResult(
        position=pos,
        close_price=price,
        close_reason="tp_partial",
        closed_at=datetime.now(timezone.utc),
        qty_closed=half_contracts,
        pnl_closed=pos.partial_pnl,
    )
    trade_history.append(_partial_result)
    if _FS:
        _fs.save_position(_position_to_dict(pos))
        _fs.save_history(_result_to_dict(_partial_result), f"{pos.signal_id}_partial")

    if trading_mode() == "live":
        try:
            from btc_agent.trading.executor import (
                cancel_order, place_market_order, place_stop_limit_order,
            )
            stop_side = "SELL" if pos.direction == "long" else "BUY"
            qty_str   = _qty_str(half_contracts)
            place_market_order(stop_side, qty_str)
            if pos.sl_order_id:
                try:
                    cancel_order(pos.sl_order_id)
                except Exception as ce:
                    console.print(f"[dim]SL cancel warning: {ce}[/dim]")
            limit_sl  = round(new_sl * 0.995 if pos.direction == "long" else new_sl * 1.005, 2)
            sl_qty    = _qty_str(half_contracts)
            resp = place_stop_limit_order(stop_side, sl_qty, new_sl, limit_sl)
            pos.sl_order_id = resp.get("order_id", "")
        except Exception as e:
            console.print(f"[red]Partial close order error: {e}[/red]")


def _close_position(pos: Position, price: float, reason: str) -> None:
    """Close the remaining contracts, compute total PnL, and record a TradeResult."""
    remaining  = int(pos.qty) // 2 if pos.partial_closed else int(pos.qty)
    pnl_pts    = price - pos.entry_price if pos.direction == "long" else pos.entry_price - price
    remain_pnl = round(pnl_pts * remaining * config.COINBASE_CONTRACT_SIZE, 4)
    pos.pnl    = round(pos.partial_pnl + remain_pnl, 4)
    pos.status = f"closed_{reason}"

    color = "green" if reason == "tp" else "red"
    partial_note = f"  partial={pos.partial_pnl:+.4f}  remain={remain_pnl:+.4f}" \
                   if pos.partial_closed else ""
    console.print(
        f"[{color}]CLOSE {pos.direction.upper()} ({reason.upper()})[/{color}] "
        f"@ {price:.1f}  {remaining} contracts{partial_note}  Total={pos.pnl:+.4f}"
    )

    if trading_mode() == "live":
        try:
            from btc_agent.trading.executor import cancel_order, place_market_order
            if pos.sl_order_id:
                try:
                    cancel_order(pos.sl_order_id)
                except Exception:
                    pass  # may already be filled by Coinbase
            stop_side = "SELL" if pos.direction == "long" else "BUY"
            qty_str   = _qty_str(remaining)
            place_market_order(stop_side, qty_str)
        except Exception as e:
            console.print(f"[red]Close order error: {e}[/red]")

    _close_result = TradeResult(
        position=pos,
        close_price=price,
        close_reason=reason,
        closed_at=datetime.now(timezone.utc),
        qty_closed=remaining,
        pnl_closed=remain_pnl,
    )
    trade_history.append(_close_result)
    if _FS:
        _fs.save_position(_position_to_dict(pos))
        _fs.save_history(_result_to_dict(_close_result), f"{pos.signal_id}_{reason}")


def _monitor_positions(current_price: float) -> None:
    """
    Phase 1 (not partial_closed): watch for TP1 → partial close, or SL → full close.
    Phase 2 (partial_closed):     ratchet trailing SL, watch for SL → close remaining.
    """
    for pos in open_positions:
        if pos.status != "open":
            continue

        if not pos.partial_closed:
            hit_tp = (pos.direction == "long"  and current_price >= pos.tp) or \
                     (pos.direction == "short" and current_price <= pos.tp)
            hit_sl = (pos.direction == "long"  and current_price <= pos.sl) or \
                     (pos.direction == "short" and current_price >= pos.sl)

            if hit_tp:
                _partial_close(pos, current_price)
            elif hit_sl:
                _close_position(pos, current_price, "sl")
        else:
            # update trailing SL
            new_sl = _trail_sl(pos, current_price)
            if new_sl != pos.sl:
                console.print(f"[dim]Trail SL {pos.direction} {pos.sl:.1f} → {new_sl:.1f}[/dim]")
                if trading_mode() == "live":
                    _update_live_sl(pos, new_sl)
                pos.sl = new_sl

            hit_sl = (pos.direction == "long"  and current_price <= pos.sl) or \
                     (pos.direction == "short" and current_price >= pos.sl)
            if hit_sl:
                _close_position(pos, current_price, "sl")

    _save_state()


# ── state persistence ─────────────────────────────────────────────────────────

def _signal_to_dict(s: Signal) -> dict:
    return {
        "id": s.id, "pattern": s.pattern, "direction": s.direction,
        "tf": s.tf, "bar_open_time": s.bar_open_time,
        "entry_trigger": s.entry_trigger,
        "sl_wick": s.sl_wick, "sl_body": s.sl_body,
        "created_at": s.created_at.isoformat(),
        "expires_at": s.expires_at.isoformat(),
        "status": s.status,
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
    }


def _result_to_dict(r: TradeResult) -> dict:
    return {
        "position":    _position_to_dict(r.position),
        "close_price": r.close_price,
        "close_reason": r.close_reason,
        "closed_at":   r.closed_at.isoformat(),
        "qty_closed":  r.qty_closed,
        "pnl_closed":  r.pnl_closed,
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
    )


def _load_state() -> None:
    """Restore in-memory state from Firestore on scanner startup."""
    global pending_signals, open_positions, trade_history
    if not _FS:
        return
    state = _fs.load_state()
    if not state:
        return

    now = datetime.now(timezone.utc)
    restored_sigs, restored_pos, restored_hist = 0, 0, 0

    for d in state.get("signals", []):
        try:
            expires_at = datetime.fromisoformat(d["expires_at"])
            if expires_at < now:
                continue
            pending_signals.append(Signal(
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
            open_positions.append(_dict_to_position(d))
            restored_pos += 1
        except Exception as e:
            console.print(f"[dim yellow]Skipping malformed position: {e}[/dim yellow]")

    for d in state.get("history", []):
        try:
            trade_history.append(TradeResult(
                position=_dict_to_position(d["position"]),
                close_price=d["close_price"],
                close_reason=d["close_reason"],
                closed_at=datetime.fromisoformat(d["closed_at"]),
                qty_closed=d.get("qty_closed", 0.0),
                pnl_closed=d.get("pnl_closed", 0.0),
            ))
            restored_hist += 1
        except Exception as e:
            console.print(f"[dim yellow]Skipping malformed history entry: {e}[/dim yellow]")

    console.print(
        f"[green]Restored from Firestore:[/green] "
        f"{restored_sigs} signals · {restored_pos} positions · {restored_hist} history"
    )

    # Load app-level and user-level settings from Firestore
    from btc_agent import config as _cfg
    from btc_agent.trading.firestore_store import load_app_settings, load_user_prefs
    app_data = load_app_settings()
    if app_data:
        _cfg.apply_settings(app_data)
        console.print("[green]App settings loaded from Firestore[/green]")
    if _cfg.FIREBASE_OWNER_UID:
        user_data = load_user_prefs(_cfg.FIREBASE_OWNER_UID)
        if user_data:
            _cfg.apply_settings(user_data)
            console.print("[green]User settings (Coinbase keys) loaded from Firestore[/green]")
        else:
            console.print("[dim yellow]No user settings in Firestore — using .env values[/dim yellow]")


def _save_state() -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "signals":   [_signal_to_dict(s) for s in pending_signals],
        "positions": [_position_to_dict(p) for p in open_positions],
        "history":   [_result_to_dict(r) for r in trade_history[-50:]],
        "running":   _running,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _STATE_PATH.write_text(json.dumps(state, indent=2))


def get_state() -> dict:
    """Return current in-memory state for the web API."""
    return {
        "signals":   [_signal_to_dict(s) for s in pending_signals],
        "positions": [_position_to_dict(p) for p in open_positions],
        "history":   [_result_to_dict(r) for r in trade_history[-50:]],
        "running":       _running,
        "current_price": _last_price,
        "levels":        _current_levels,
        "settings": {
            "mode":              trading_mode(),
            "tf_min":            tf_min(),
            "tf_max":            tf_max(),
            "scan_interval_min": scan_interval(),
            "qty":               trading_qty(),
            "max_sl":            max_sl(),
            "min_tp":            min_tp(),
            "max_concurrent":    max_concurrent(),
            "patterns":          active_patterns(),
        },
    }


# ── main loop ─────────────────────────────────────────────────────────────────

def stop_trading_scanner() -> None:
    global _running
    _running = False


_PRICE_TICK_S = 5  # fast price refresh interval for entries and position monitoring


def run_trading_scanner() -> None:
    global _running, _last_scan_time, _current_levels, _last_price
    _last_state_save = datetime.now(timezone.utc)
    _load_state()
    _running = True
    console.rule("[bold green]Trading Scanner started[/bold green]")
    mode = trading_mode()
    qty = trading_qty()
    console.print(
        f"Mode=[bold]{mode.upper()}[/bold]  TF={tf_min()}–{tf_max()}m  "
        f"ScanInterval={scan_interval()}min  PriceTick={_PRICE_TICK_S}s  "
        f"Qty={qty} contracts ({qty * config.COINBASE_CONTRACT_SIZE:.4f} BTC each side)  "
        f"MaxSL={max_sl()}  MinTP={min_tp()}  MaxConcurrent={max_concurrent()}"
    )
    if qty < 2:
        console.print(
            "[yellow]Warning: TRADING_QTY < 2 — partial close requires at least 2 contracts[/yellow]"
        )

    arr = ts_arr = minutes_of_day = unix_days = None

    try:
        while _running:
            tick_start = datetime.now(timezone.utc)
            now = tick_start

            # ── fast price tick ───────────────────────────────────────────────
            try:
                current_price = fetch_current_price()
                _last_price = current_price
            except Exception as e:
                console.print(f"[red]Price tick error: {e}[/red]")
                time.sleep(_PRICE_TICK_S)
                continue

            # ── monitor open positions ────────────────────────────────────────
            _monitor_positions(current_price)

            # ── check pending signals for entry trigger ───────────────────────
            for sig in pending_signals:
                if sig.status != "pending":
                    continue
                if now > sig.expires_at:
                    sig.status = "expired"
                    if _FS:
                        _fs.update_signal_status(sig.id, "expired")
                    console.print(f"[dim]Signal {sig.id} ({sig.pattern} {sig.tf}m) expired[/dim]")
                    continue
                if sig.direction == "long"  and current_price > sig.entry_trigger:
                    _execute_entry(sig, current_price)
                elif sig.direction == "short" and current_price < sig.entry_trigger:
                    _execute_entry(sig, current_price)

            # ── pattern scan (every scan_interval() minutes) ──────────────────
            elapsed_min = (now - _last_scan_time).total_seconds() / 60 if _last_scan_time else 999
            if elapsed_min >= scan_interval():
                try:
                    df = fetch_1m_candles()
                    arr, ts_arr, minutes_of_day, unix_days = df_to_numpy(df)
                    _current_levels = compute_levels(df, weekly_adj=config.WEEKLY_ADJ)
                    bias = _trend_bias(current_price, _current_levels)
                    mrp_str  = f"{_current_levels['mrp']:.1f}"      if _current_levels.get("mrp")       else "—"
                    dpoc_str = f"{_current_levels['daily_poc']:.1f}" if _current_levels.get("daily_poc") else "—"
                    wpoc_str = f"{_current_levels['weekly_poc']:.1f}" if _current_levels.get("weekly_poc") else "—"
                    console.print(
                        f"[dim]Levels — MRP={mrp_str}  DailyPOC={dpoc_str}  "
                        f"WeeklyPOC={wpoc_str}  Trend: {bias}[/dim]"
                    )
                    console.print(
                        f"[cyan]Scanning {tf_min()}–{tf_max()}m "
                        f"({', '.join(active_patterns())})…[/cyan]"
                    )
                    new_sigs = _scan_patterns(arr, ts_arr, minutes_of_day, unix_days)
                    if new_sigs:
                        pending_signals.extend(new_sigs)
                        if _FS:
                            for sig in new_sigs:
                                _fs.save_signal(_signal_to_dict(sig))
                    else:
                        console.print("[dim]No new patterns found[/dim]")
                    _last_scan_time = now
                except Exception as e:
                    console.print(f"[red]Pattern scan error: {e}[/red]")

            if (datetime.now(timezone.utc) - _last_state_save).total_seconds() >= 60:
                _save_state()
                _last_state_save = datetime.now(timezone.utc)

            # ── sleep until next 5-second tick ───────────────────────────────
            elapsed_s = (datetime.now(timezone.utc) - tick_start).total_seconds()
            time.sleep(max(0, _PRICE_TICK_S - elapsed_s))

    except KeyboardInterrupt:
        console.print("\n[yellow]Trading scanner stopped.[/yellow]")
    finally:
        _running = False
        _save_state()
