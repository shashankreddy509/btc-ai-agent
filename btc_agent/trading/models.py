"""
Data models for the trading scanner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Signal:
    id: str                   # short uuid
    pattern: str              # "4-Flag" | "Engulfing"
    direction: str            # "long" | "short"
    tf: int                   # timeframe in minutes
    bar_open_time: str        # ISO UTC of pattern candle open
    entry_trigger: float      # body_high (long) or body_low (short) — cross to enter
    sl_wick: float            # wick_low (long) or wick_high (short)
    sl_body: float            # body_low (long) or body_high (short) — fallback SL
    created_at: datetime
    expires_at: datetime      # created_at + tf minutes (signal valid for 1 bar)
    status: str = "pending"   # "pending" | "triggered" | "expired" | "skipped"
    custom_tp: float = 0.0    # 0 = use market structure TP; > 0 = fixed TP price (Vishal strategies)
    meta: dict = field(default_factory=dict)  # extra display data (e.g. Retracement fib levels)


@dataclass
class Position:
    signal_id: str
    entry_price: float
    sl: float
    tp: float
    qty: float
    direction: str            # "long" | "short"
    opened_at: datetime
    pattern: str = ""         # "4-Flag" | "Engulfing"
    tf: int = 0               # timeframe in minutes
    status: str = "open"      # "open" | "closed_tp" | "closed_sl" | "closed_manual"
    pnl: float | None = None
    coinbase_order_id: str | None = None
    tp_reason: str = ""          # "MRP" | "Daily POC" | "Weekly POC" | "fixed_500" | …
    partial_closed: bool = False # True after TP1 hit and half qty sold
    trail_anchor: float | None = None  # price at which partial TP was hit (trailing reference)
    partial_pnl: float = 0.0     # PnL banked from the partial close
    sl_order_id: str | None = None     # Coinbase SL order ID (cancel/replace on trail)


@dataclass
class TradeResult:
    position: Position
    close_price: float
    close_reason: str         # "tp_partial" | "tp" | "sl" | "manual"
    closed_at: datetime
    qty_closed: float = 0.0   # how much BTC was closed in this event
    pnl_closed: float = 0.0   # PnL for this specific close event (USD)
