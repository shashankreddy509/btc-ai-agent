"""
Trading Scanner — scans 15m–90m TFs for 4-Flag and Engulfing patterns,
monitors the next candle for a body breakout, then executes a trade on Coinbase.

Entry logic:
  - Pattern found on candle X (current bar)
  - Next candle: if price > body_high(X) → long entry
                 if price < body_low(X)  → short entry
  - SL priority: wick → body → hard cap (TRADING_MAX_SL pts)
  - TP: entry ± TRADING_MIN_TP

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
from btc_agent.scanner.data import fetch_1m_candles
from btc_agent.scanner.patterns import detect_4flag, detect_engulfing
from btc_agent.trading.models import Position, Signal, TradeResult

console = Console()

_IST = timezone(timedelta(hours=5, minutes=30))
_STATE_PATH = Path(__file__).parent.parent / "data" / "trading_state.json"
_SETTINGS_PATH = Path(__file__).parent.parent / "data" / "trading_settings.json"

# ── module-level state (shared with web API) ──────────────────────────────────
pending_signals: list[Signal] = []
open_positions:  list[Position] = []
trade_history:   list[TradeResult] = []
_running = False
_last_scan_time: datetime | None = None


# ── settings (hot-reloadable from JSON) ──────────────────────────────────────

def _load_settings() -> dict:
    """Load runtime overrides from trading_settings.json (falls back to config)."""
    if _SETTINGS_PATH.exists():
        try:
            return json.loads(_SETTINGS_PATH.read_text())
        except Exception:
            pass
    return {}


def _get(key: str, default):
    """Read setting: JSON file overrides .env/config."""
    return _load_settings().get(key, default)


def tf_min()            -> int:   return int(_get("tf_min",   config.TRADING_TF_MIN))
def tf_max()            -> int:   return int(_get("tf_max",   config.TRADING_TF_MAX))
def scan_interval()     -> int:   return int(_get("scan_interval_min", config.TRADING_SCAN_INTERVAL_MIN))
def trading_mode()      -> str:   return _get("mode",         config.TRADING_MODE)
def max_concurrent()    -> int:   return int(_get("max_concurrent",    config.TRADING_MAX_CONCURRENT))
def trading_qty()       -> float: return float(_get("qty",    config.TRADING_QTY))
def max_sl()            -> float: return float(_get("max_sl", config.TRADING_MAX_SL))
def min_tp()            -> float: return float(_get("min_tp", config.TRADING_MIN_TP))
def active_patterns()   -> list:  return _get("patterns",     config.TRADING_PATTERNS)


# ── SL calculation ────────────────────────────────────────────────────────────

def calc_sl(direction: str, sl_wick: float, sl_body: float, entry: float) -> float:
    """
    Priority: wick → body → hard cap (max_sl() points).
    Long:  sl is below entry; Short: sl is above entry.
    """
    cap = max_sl()
    if direction == "long":
        sl = sl_wick
        if entry - sl > cap:
            sl = sl_body
        if entry - sl > cap:
            sl = entry - cap
    else:
        sl = sl_wick
        if sl - entry > cap:
            sl = sl_body
        if sl - entry > cap:
            sl = entry + cap
    return round(sl, 2)


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
    if direction == "long":
        entry_trigger = body_hi
        sl_wick = l           # wick low
        sl_body = body_lo     # body low
    else:
        entry_trigger = body_lo
        sl_wick = h           # wick high
        sl_body = body_hi     # body high
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
                last = bars[-1]
                o, c = last[0], last[3]
                direction = "long" if c >= o else "short"
                sig = _bars_to_signal("4-Flag", direction, tf, bars, bar_open_time)
                new_signals.append(sig)
                console.print(
                    f"[bold yellow]4-Flag[/bold yellow] detected on [green]{tf}m[/green] "
                    f"→ {direction.upper()}  trigger={sig.entry_trigger:.1f}"
                )

        if "Engulfing" in patterns and len(bars) >= 2:
            found, direction = detect_engulfing(bars[-2:])
            if found:
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
        _save_state()
        return

    entry = current_price
    sl = calc_sl(sig.direction, sig.sl_wick, sig.sl_body, entry)
    tp = round(entry + min_tp(), 2) if sig.direction == "long" else round(entry - min_tp(), 2)
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
            qty_str = f"{qty:.8f}".rstrip("0").rstrip(".")
            order = place_market_order(side, qty_str)
            pos.coinbase_order_id = order.get("order_id", "")
            # SL limit = 0.5% beyond stop to ensure fill
            limit_sl = round(sl * 0.995 if sig.direction == "long" else sl * 1.005, 2)
            place_stop_limit_order(stop_side, qty_str, sl, limit_sl)
            console.print(f"[bold green]LIVE {side}[/bold green] {qty} BTC @ ~{entry:.1f}  SL={sl:.1f}  TP={tp:.1f}")
        except Exception as e:
            console.print(f"[red]Coinbase order failed: {e}[/red]")
            sig.status = "pending"   # revert so we can retry
            return
    else:
        console.print(
            f"[bold green]PAPER {sig.direction.upper()}[/bold green] "
            f"{qty} BTC @ {entry:.1f}  SL={sl:.1f}  TP={tp:.1f}  "
            f"[dim]({sig.pattern} {sig.tf}m)[/dim]"
        )

    open_positions.append(pos)
    _save_state()


# ── position monitoring (paper mode) ─────────────────────────────────────────

def _monitor_positions(current_price: float) -> None:
    """Close paper positions that hit SL or TP."""
    for pos in open_positions:
        if pos.status != "open":
            continue
        if trading_mode() != "paper":
            continue   # live positions managed by Coinbase

        hit_tp = (pos.direction == "long"  and current_price >= pos.tp) or \
                 (pos.direction == "short" and current_price <= pos.tp)
        hit_sl = (pos.direction == "long"  and current_price <= pos.sl) or \
                 (pos.direction == "short" and current_price >= pos.sl)

        if hit_tp or hit_sl:
            reason = "tp" if hit_tp else "sl"
            pnl_pts = (current_price - pos.entry_price) if pos.direction == "long" \
                      else (pos.entry_price - current_price)
            pos.pnl = round(pnl_pts * pos.qty, 4)
            pos.status = f"closed_{reason}"
            result = TradeResult(
                position=pos,
                close_price=current_price,
                close_reason=reason,
                closed_at=datetime.now(timezone.utc),
            )
            trade_history.append(result)
            color = "green" if reason == "tp" else "red"
            console.print(
                f"[{color}]PAPER CLOSE {pos.direction.upper()} ({reason.upper()})[/{color}] "
                f"@ {current_price:.1f}  PnL pts={pnl_pts:+.1f}  USD={pos.pnl:+.4f}"
            )
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
    return {
        "signal_id": p.signal_id, "entry_price": p.entry_price,
        "sl": p.sl, "tp": p.tp, "qty": p.qty, "direction": p.direction,
        "opened_at": p.opened_at.isoformat(),
        "pattern": p.pattern, "tf": p.tf,
        "status": p.status, "pnl": p.pnl,
        "coinbase_order_id": p.coinbase_order_id,
    }


def _result_to_dict(r: TradeResult) -> dict:
    return {
        "position": _position_to_dict(r.position),
        "close_price": r.close_price,
        "close_reason": r.close_reason,
        "closed_at": r.closed_at.isoformat(),
    }


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
        "running":   _running,
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


def run_trading_scanner() -> None:
    global _running, _last_scan_time
    _running = True
    console.rule("[bold green]Trading Scanner started[/bold green]")
    mode = trading_mode()
    console.print(
        f"Mode=[bold]{mode.upper()}[/bold]  TF={tf_min()}–{tf_max()}m  "
        f"ScanInterval={scan_interval()}min  Qty={trading_qty()}  "
        f"MaxSL={max_sl()}  MinTP={min_tp()}  MaxConcurrent={max_concurrent()}"
    )

    try:
        while _running:
            loop_start = datetime.now(timezone.utc)

            # ── fetch latest 1m candles ───────────────────────────────────────
            try:
                df = fetch_1m_candles()
                arr, ts_arr, minutes_of_day, unix_days = df_to_numpy(df)
                current_price = float(arr[-1, 3])   # last 1m close
            except Exception as e:
                console.print(f"[red]Data fetch error: {e}[/red]")
                time.sleep(60)
                continue

            # ── monitor open positions ────────────────────────────────────────
            _monitor_positions(current_price)

            # ── check pending signals for entry trigger ───────────────────────
            now = datetime.now(timezone.utc)
            for sig in pending_signals:
                if sig.status != "pending":
                    continue
                if now > sig.expires_at:
                    sig.status = "expired"
                    console.print(f"[dim]Signal {sig.id} ({sig.pattern} {sig.tf}m) expired[/dim]")
                    continue
                if sig.direction == "long"  and current_price > sig.entry_trigger:
                    _execute_entry(sig, current_price)
                elif sig.direction == "short" and current_price < sig.entry_trigger:
                    _execute_entry(sig, current_price)

            # ── pattern scan (every scan_interval() minutes) ──────────────────
            elapsed = (now - _last_scan_time).total_seconds() / 60 if _last_scan_time else 999
            if elapsed >= scan_interval():
                console.print(
                    f"[cyan]Scanning {tf_min()}–{tf_max()}m "
                    f"({', '.join(active_patterns())})…[/cyan]"
                )
                new_sigs = _scan_patterns(arr, ts_arr, minutes_of_day, unix_days)
                if new_sigs:
                    pending_signals.extend(new_sigs)
                else:
                    console.print("[dim]No new patterns found[/dim]")
                _last_scan_time = now

            _save_state()

            # ── sleep until next minute ───────────────────────────────────────
            elapsed_s = (datetime.now(timezone.utc) - loop_start).total_seconds()
            sleep_s = max(0, 60 - elapsed_s)
            time.sleep(sleep_s)

    except KeyboardInterrupt:
        console.print("\n[yellow]Trading scanner stopped.[/yellow]")
    finally:
        _running = False
        _save_state()
