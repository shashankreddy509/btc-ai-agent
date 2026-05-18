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
    running: bool = False
    last_scan_time: Optional[datetime] = None
    current_levels: dict = field(default_factory=dict)
    last_price: float = 0.0
    settings: dict = field(default_factory=dict)
    broker: object = field(default=None, repr=False)

    @property
    def state_path(self) -> Path:
        return _DATA_DIR / f"trading_state_{self.uid[:8]}.json"


_scanners: dict[str, _Scanner] = {}
_scanners_lock = threading.Lock()


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
    creds = {
        "api_key":       sc.settings.get(f"{name}_api_key") or getattr(config, f"{name.upper()}_API_KEY", ""),
        "api_secret":    sc.settings.get(f"{name}_api_secret") or getattr(config, f"{name.upper()}_API_SECRET", ""),
        "product_id":    sc.settings.get("coinbase_product_id", config.COINBASE_PRODUCT_ID),
        "contract_size": sc.settings.get("coinbase_contract_size", config.COINBASE_CONTRACT_SIZE),
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


def _trend_bias(price: float, levels: dict) -> str:
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

def _bars_to_signal(pattern: str, direction: str, tf: int, bars: np.ndarray, bar_open_time: str) -> Signal:
    o, h, l, c = bars[-1, 0], bars[-1, 1], bars[-1, 2], bars[-1, 3]
    body_hi = max(o, c)
    body_lo = min(o, c)
    now = datetime.now(timezone.utc)
    if pattern == "4-Flag":
        flag_bars = bars[-4:]
        flag_body_his = np.maximum(flag_bars[:, 0], flag_bars[:, 3])
        flag_body_los = np.minimum(flag_bars[:, 0], flag_bars[:, 3])
        entry_trigger = float(flag_body_his.max()) if direction == "long" else float(flag_body_los.min())
    else:
        entry_trigger = body_hi if direction == "long" else body_lo
    sl_wick = l if direction == "long" else h
    sl_body = body_lo if direction == "long" else body_hi
    return Signal(
        id=uuid.uuid4().hex[:8],
        pattern=pattern, direction=direction, tf=tf,
        bar_open_time=bar_open_time,
        entry_trigger=round(entry_trigger, 2),
        sl_wick=round(sl_wick, 2), sl_body=round(sl_body, 2),
        created_at=now, expires_at=now + timedelta(minutes=tf),
    )


# ── pattern scan ──────────────────────────────────────────────────────────────

def _is_duplicate(sc: _Scanner, tf: int, pattern: str, direction: str, bar_open_time: str) -> bool:
    return any(
        s.status in ("pending", "triggered") and
        s.tf == tf and s.pattern == pattern and
        s.direction == direction and s.bar_open_time == bar_open_time
        for s in sc.pending_signals
    )


def _scan_patterns(sc: _Scanner, arr, ts_arr, minutes_of_day, unix_days) -> list[Signal]:
    new_signals: list[Signal] = []
    patterns = _active_patterns(sc)
    for tf in range(_tf_min(sc), _tf_max(sc) + 1):
        bars, bar_open_times = aggregate_tf(arr, ts_arr, minutes_of_day, unix_days, tf, last_n=5)
        if bars is None or len(bars) < 2:
            continue
        bar_open_ts = int(bar_open_times[-1])
        bar_open_time = datetime.fromtimestamp(bar_open_ts, tz=timezone.utc).isoformat()

        if "4-Flag" in patterns and len(bars) >= 4:
            if detect_4flag(bars[-4:]):
                for direction in ("long", "short"):
                    if not _is_duplicate(sc, tf, "4-Flag", direction, bar_open_time):
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
                if not _is_duplicate(sc, tf, "Engulfing", direction, bar_open_time):
                    sig = _bars_to_signal("Engulfing", direction, tf, bars, bar_open_time)
                    new_signals.append(sig)
                    console.print(
                        f"[bold cyan]Engulfing ({direction})[/bold cyan] on [green]{tf}m[/green] "
                        f"→ {direction.upper()}  trigger={sig.entry_trigger:.1f}"
                    )
    return new_signals


<<<<<<< HEAD
=======
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
            console.print(f"[dim]BSG {tf}m error: {e}[/dim]")


>>>>>>> parent of 4e3872d (fix: code quality and security hardening across 8 files)
# ── entry execution ───────────────────────────────────────────────────────────

def _execute_entry(sc: _Scanner, sig: Signal, current_price: float) -> None:
    n_open = sum(1 for p in sc.open_positions if p.status == "open")
    cap = _max_concurrent(sc)
    if cap > 0 and n_open >= cap:
        sig.status = "skipped"
        console.print(f"[yellow]Signal {sig.id} skipped — max concurrent ({cap}) reached[/yellow]")
        if _FS: _fs.update_signal_status(sig.id, "skipped")
        _save_state(sc)
        return

    entry = current_price
    sl = calc_sl(sig.sl_wick)
    sl_dist = abs(entry - sl)
    sl_cap = _max_sl(sc)
    if sl_dist > sl_cap:
        sl = round(entry - sl_cap if sig.direction == "long" else entry + sl_cap, 2)
        console.print(f"[dim yellow]Signal {sig.id} SL capped at {sl_cap:.0f} pts[/dim yellow]")
    tp, tp_reason = _calc_tp(sc, sig.direction, entry)
    qty = _trading_qty(sc)
    sig.status = "triggered"

    pos = Position(
        signal_id=sig.id, entry_price=entry, sl=sl, tp=tp, qty=qty,
        direction=sig.direction, opened_at=datetime.now(timezone.utc),
        pattern=sig.pattern, tf=sig.tf, tp_reason=tp_reason,
    )

    mode = _trading_mode(sc)
    if mode == "live":
        try:
            broker = sc.broker
            side = "BUY" if sig.direction == "long" else "SELL"
            stop_side = "SELL" if sig.direction == "long" else "BUY"
            qty_str = _qty_str(qty)
            order = broker.place_market_order(side, qty_str)
            pos.coinbase_order_id = order.get("order_id", "")
            limit_sl = round(sl * 0.995 if sig.direction == "long" else sl * 1.005, 2)
            sl_resp = broker.place_stop_limit_order(stop_side, qty_str, sl, limit_sl)
            pos.sl_order_id = sl_resp.get("order_id", "")
            console.print(
                f"[bold green]LIVE {side}[/bold green] {qty} contracts @ ~{entry:.1f}  "
                f"SL={sl:.1f}  TP={tp:.1f} [dim]({tp_reason})[/dim]"
            )
        except Exception as e:
            console.print(f"[red]Broker order failed: {e}[/red]")
            sig.status = "pending"
            return
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
        return max(pos.sl, new_sl)
    else:
        steps = max(0, int((pos.trail_anchor - current_price) / 100))
        new_sl = round(pos.entry_price - 50 - steps * 50, 2)
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
    pos.partial_pnl = round(pnl_pts * half_contracts * sc.broker.contract_size, 4)
    pos.partial_closed = True
    pos.trail_anchor = price
    old_sl = pos.sl
    new_sl = round(pos.entry_price + 50 if pos.direction == "long" else pos.entry_price - 50, 2)
    pos.sl = new_sl

    console.print(
        f"[bold cyan]PARTIAL TP {pos.direction.upper()}[/bold cyan] "
        f"@ {price:.1f}  half={half_contracts} contracts  PnL={pos.partial_pnl:+.4f}  "
        f"SL: {old_sl:.1f} → {new_sl:.1f}  (trailing begins)"
    )

    partial_result = TradeResult(
        position=pos, close_price=price, close_reason="tp_partial",
        closed_at=datetime.now(timezone.utc),
        qty_closed=half_contracts, pnl_closed=pos.partial_pnl,
    )
    sc.trade_history.append(partial_result)
    if _FS:
        _fs.save_position(_position_to_dict(pos), sc.uid)
        _fs.save_history(_result_to_dict(partial_result), f"{pos.signal_id}_partial", sc.uid)

    if _trading_mode(sc) == "live":
        try:
            broker = sc.broker
            stop_side = "SELL" if pos.direction == "long" else "BUY"
            broker.place_market_order(stop_side, _qty_str(half_contracts))
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

    if _trading_mode(sc) == "live":
        try:
            broker = sc.broker
            if pos.sl_order_id:
                try:
                    broker.cancel_order(pos.sl_order_id)
                except Exception:
                    pass
            stop_side = "SELL" if pos.direction == "long" else "BUY"
            broker.place_market_order(stop_side, _qty_str(remaining))
        except Exception as e:
            console.print(f"[red]Close order error: {e}[/red]")

    close_result = TradeResult(
        position=pos, close_price=price, close_reason=reason,
        closed_at=datetime.now(timezone.utc),
        qty_closed=remaining, pnl_closed=remain_pnl,
    )
    sc.trade_history.append(close_result)
    if _FS:
        _fs.save_position(_position_to_dict(pos), sc.uid)
        _fs.save_history(_result_to_dict(close_result), f"{pos.signal_id}_{reason}", sc.uid)


def _monitor_positions(sc: _Scanner, current_price: float) -> None:
    for pos in sc.open_positions:
        if pos.status != "open":
            continue
        if not pos.partial_closed:
            hit_tp = (pos.direction == "long"  and current_price >= pos.tp) or \
                     (pos.direction == "short" and current_price <= pos.tp)
            hit_sl = (pos.direction == "long"  and current_price <= pos.sl) or \
                     (pos.direction == "short" and current_price >= pos.sl)
            if hit_tp:
                _partial_close(sc, pos, current_price)
            elif hit_sl:
                _close_position(sc, pos, current_price, "sl")
        else:
            new_sl = _trail_sl(pos, current_price)
            if new_sl != pos.sl:
                console.print(f"[dim]Trail SL {pos.direction} {pos.sl:.1f} → {new_sl:.1f}[/dim]")
                if _trading_mode(sc) == "live":
                    _update_live_sl(sc, pos, new_sl)
                pos.sl = new_sl
            hit_sl = (pos.direction == "long"  and current_price <= pos.sl) or \
                     (pos.direction == "short" and current_price >= pos.sl)
            if hit_sl:
                _close_position(sc, pos, current_price, "sl")
    _save_state(sc)


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
            ))
            restored_hist += 1
        except Exception as e:
            console.print(f"[dim yellow]Skipping malformed history entry: {e}[/dim yellow]")

    if restored_sigs or restored_pos or restored_hist:
        console.print(
            f"[green]Restored from Firestore:[/green] "
            f"{restored_sigs} signals · {restored_pos} positions · {restored_hist} history"
        )


def _save_state(sc: _Scanner) -> None:
    sc.state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "signals":   [_signal_to_dict(s) for s in sc.pending_signals],
        "positions": [_position_to_dict(p) for p in sc.open_positions],
        "history":   [_result_to_dict(r) for r in sc.trade_history[-50:]],
        "running":   sc.running,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    sc.state_path.write_text(json.dumps(state, indent=2))


def get_state(uid: str | None = None) -> dict:
    """Return current in-memory state for the web API."""
    sc = _scanners.get(uid) if uid else None

    if sc is None:
        return {
            "signals": [], "positions": [], "history": [],
            "running": False, "current_price": 0.0, "levels": {},
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
            },
        }

    return {
        "signals":   [_signal_to_dict(s) for s in sc.pending_signals],
        "positions": [_position_to_dict(p) for p in sc.open_positions],
        "history":   [_result_to_dict(r) for r in sc.trade_history[-50:]],
        "running":       sc.running,
        "current_price": sc.last_price,
        "levels":        sc.current_levels,
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
        },
    }


# ── public API ────────────────────────────────────────────────────────────────

def stop_trading_scanner(uid: str) -> None:
    sc = _scanners.get(uid)
    if sc:
        sc.running = False


def is_any_running() -> bool:
    return any(sc.running for sc in _scanners.values())


_PRICE_TICK_S = 5


def run_trading_scanner(uid: str, user_settings: dict | None = None) -> None:
    sc = _get_or_create(uid)
    if sc.running:
        return
    if user_settings:
        sc.settings.update(user_settings)
    _load_state(sc)
    sc.running = True
    console.rule("[bold green]Trading Scanner started[/bold green]")
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

    sc.broker = _build_broker(sc)
<<<<<<< HEAD
=======
    if sc.broker and _is_live(sc):
        try:
            sc.broker_account_name = sc.broker.get_display_name()
        except Exception:
            sc.broker_account_name = ""
>>>>>>> parent of 4e3872d (fix: code quality and security hardening across 8 files)

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

            for sig in sc.pending_signals:
                if sig.status != "pending":
                    continue
                if now > sig.expires_at:
                    sig.status = "expired"
                    if _FS: _fs.update_signal_status(sig.id, "expired")
                    console.print(f"[dim]Signal {sig.id} ({sig.pattern} {sig.tf}m) expired[/dim]")
                    continue
                if sig.direction == "long"  and current_price > sig.entry_trigger:
                    _execute_entry(sc, sig, current_price)
                elif sig.direction == "short" and current_price < sig.entry_trigger:
                    _execute_entry(sc, sig, current_price)

            elapsed_min = (now - sc.last_scan_time).total_seconds() / 60 if sc.last_scan_time else 999
            if elapsed_min >= _scan_interval(sc):
                try:
                    df = fetch_1m_candles()
                    arr, ts_arr, minutes_of_day, unix_days = df_to_numpy(df)
                    sc.current_levels = compute_levels(df, weekly_adj=config.WEEKLY_ADJ)
                    bias = _trend_bias(current_price, sc.current_levels)
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
                    if new_sigs:
                        sc.pending_signals.extend(new_sigs)
                        if _FS:
                            for sig in new_sigs:
                                _fs.save_signal(_signal_to_dict(sig), sc.uid)
                    else:
                        console.print("[dim]No new patterns found[/dim]")
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
        sc.running = False
        _save_state(sc)
