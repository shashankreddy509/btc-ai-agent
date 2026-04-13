"""
Open Interest display — aggregates 1H OI candles across 6 exchanges, matching
the Pine Script "Open Interest Suite [Aggregated]" by Leviathan Capital.

Display modes (matches Pine Script "Display" input):
  Open Interest       — aggregated OI value (USD or COIN)
  Open Interest Delta — change in OI per bar  (default)
  OID x rVOL          — OI delta × relative volume (delta × vol/sma20vol)
  Open Interest RSI   — RSI of the OI close series

Sources (all 6, matching Pine Script defaults):
  Binance USDT-M  Binance COIN-M  Binance BUSD-M
  BitMEX USD.P    BitMEX USDT.P   Kraken USD.P

Failures silently contribute 0 — identical to nz(...,0) in Pine Script.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

import ccxt
import numpy as np
from rich.console import Console
from rich.table import Table

from btc_agent import config

console = Console()

_IST = timezone(timedelta(hours=5, minutes=30))

_VALID_MODES = {"Open Interest", "Open Interest Delta", "OID x rVOL", "Open Interest RSI"}

# (display_name, ccxt_factory, symbol, oi_in_usd)
#
# oi_in_usd=False → linear contract: openInterestAmount is in BTC  → use directly
#                   (matches Pine Script: nz(oid1,0) added as-is)
# oi_in_usd=True  → inverse contract: openInterestValue is in USD  → divide by price to get BTC
#                   (matches Pine Script: nz(oid,0)/close)
_OI_SOURCES: list[tuple[str, object, str, bool]] = [
    ("Binance USDT-M", lambda: ccxt.binanceusdm({"enableRateLimit": True}),   "BTC/USDT:USDT", False),  # linear
    ("Binance COIN-M", lambda: ccxt.binancecoinm({"enableRateLimit": True}),  "BTC/USD:BTC",   True),   # inverse
    ("Binance BUSD-M", lambda: ccxt.binanceusdm({"enableRateLimit": True}),   "BTC/BUSD:BUSD", False),  # linear
    ("BitMEX USD.P",   lambda: ccxt.bitmex({"enableRateLimit": True}),        "BTC/USD:BTC",   True),   # inverse ← was False (bug)
    ("BitMEX USDT.P",  lambda: ccxt.bitmex({"enableRateLimit": True}),        "BTC/USDT:USDT", False),  # linear  ← was True  (bug)
    ("Kraken USD.P",   lambda: ccxt.krakenfutures({"enableRateLimit": True}), "BTC/USD:USD",   True),   # inverse
]

def _fetch_limit() -> int:
    """Bars to fetch: enough for SMA-300 threshold + RSI warmup + display candles."""
    return max(config.OI_CANDLES + 305, config.OI_CANDLES + config.OI_RSI_LEN + 20)


# ── helpers ───────────────────────────────────────────────────────────────────

def _ts_to_ist(ts_utc: int) -> str:
    dt = datetime.fromtimestamp(ts_utc, tz=timezone.utc).astimezone(_IST)
    return dt.strftime("%d-%b-%Y %H:%M")


def _fmt_delta(v: float) -> str:
    """Format an OI delta as '+$320M' / '-$410M' / '+$1.50B' (USD) or '+840 BTC' (COIN)."""
    sign = "+" if v >= 0 else "-"
    av = abs(v)
    if config.OI_QUOTED_IN == "COIN":
        return f"{sign}{av:,.0f} BTC"
    if av >= 1e9:
        return f"{sign}${av/1e9:.2f}B"
    return f"{sign}${av/1e6:.0f}M"


def _fmt_value(v: float, mode: str, btc_price: float) -> str:
    """Format a display value according to mode and OI_QUOTED_IN."""
    if mode == "Open Interest":
        if config.OI_QUOTED_IN == "COIN":
            return f"{v:,.2f} BTC"
        return f"${v/1e9:.3f}B" if abs(v) >= 1e9 else f"${v/1e6:.1f}M"
    if mode in ("Open Interest Delta", "OID x rVOL"):
        return _fmt_delta(v)
    if mode == "Open Interest RSI":
        return f"{v:.1f}"
    return str(v)


def _rsi(series: np.ndarray, period: int) -> np.ndarray:
    """Wilder RSI — same algorithm as Pine Script ta.rsi()."""
    delta = np.diff(series)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    # Wilder smoothing (RMA)
    avg_gain = np.zeros_like(gains)
    avg_loss = np.zeros_like(losses)
    avg_gain[period - 1] = gains[:period].mean()
    avg_loss[period - 1] = losses[:period].mean()
    for i in range(period, len(gains)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.where(avg_loss == 0, np.inf, avg_gain / avg_loss)
    rsi = np.where(avg_loss == 0, 100.0, 100.0 - 100.0 / (1.0 + rs))
    # Prepend NaN for the first bar (no diff entry)
    return np.concatenate([[np.nan], rsi])


# ── data fetching ─────────────────────────────────────────────────────────────

def _fetch_source(name: str, factory, symbol: str, oi_in_usd: bool,
                  btc_price: float) -> tuple[list[int], np.ndarray] | None:
    """
    Fetch OI history for one source.  Returns (timestamps_utc_sec, oi_btc_array)
    oldest-first — values are always in BTC, matching Pine Script's normalisation:
      linear  (oi_in_usd=False): openInterestAmount is BTC → use as-is
      inverse (oi_in_usd=True):  openInterestValue  is USD → divide by price
    """
    try:
        ex = factory()
        ex.load_markets()
        rows = ex.fetch_open_interest_history(symbol, config.OI_TF, limit=_fetch_limit())
        if not rows:
            return None
        rows = sorted(rows, key=lambda r: r["timestamp"])   # ensure oldest-first
        timestamps = [int(r["timestamp"] / 1000) for r in rows]
        values: list[float] = []
        for r in rows:
            if oi_in_usd:
                # inverse: value is USD notional → convert to BTC
                raw = float(r.get("openInterestValue") or r.get("openInterestAmount", 0))
                btc = raw / btc_price if btc_price > 0 else 0.0
            else:
                # linear: amount is already in BTC
                btc = float(r.get("openInterestAmount") or r.get("openInterestValue", 0))
            values.append(btc)
        return timestamps, np.array(values, dtype=np.float64)
    except (ccxt.NotSupported, ccxt.BadSymbol):
        return None
    except (ccxt.ExchangeNotAvailable, ccxt.NetworkError) as e:
        code = "451" if "451" in str(e) else "403" if "403" in str(e) else "net"
        console.print(f"[dim]OI {name}: geo-blocked ({code}), skipping[/dim]")
        return None
    except Exception as e:
        console.print(f"[dim]OI {name}: {type(e).__name__} — skipping[/dim]")
        return None


def _fetch_1h_volume(btc_price: float) -> np.ndarray | None:
    """Fetch 1H OHLCV from Binance (or Bybit fallback) for rVOL calculation."""
    candidates = [
        ("Binance", lambda: ccxt.binanceusdm({"enableRateLimit": True}), "BTC/USDT:USDT"),
        ("Bybit",   lambda: ccxt.bybit({"enableRateLimit": True}),        "BTC/USDT:USDT"),
    ]
    for name, factory, symbol in candidates:
        try:
            ex = factory()
            ex.load_markets()
            rows = ex.fetch_ohlcv(symbol, config.OI_TF, limit=_fetch_limit() + 20)
            if rows:
                return np.array([r[5] for r in rows], dtype=np.float64)   # index 5 = volume
        except Exception:
            continue
    return None


def _aggregate_oi(btc_price: float) -> tuple[list[int], np.ndarray, list[str]] | tuple[None, None, list[str]]:
    """
    Fetch OI from all sources, aggregate, return (timestamps, agg_oi_btc, source_names).
    All values are in BTC — multiply by btc_price for USD display.
    timestamps are Unix seconds, oldest-first.
    Sources are aligned on actual timestamps (intersection), not by array length.
    """
    results: list[tuple[list[int], np.ndarray]] = []
    succeeded: list[str] = []
    for name, factory, symbol, oi_in_usd in _OI_SOURCES:
        r = _fetch_source(name, factory, symbol, oi_in_usd, btc_price)
        if r is not None:
            results.append(r)
            succeeded.append(name)
        time.sleep(0.1)

    if not results:
        return None, None, []

    # Intersect timestamps across all sources so bar i always means the same UTC second
    common = set(results[0][0])
    for ts, _ in results[1:]:
        common &= set(ts)
    common_ts = sorted(common)   # oldest-first

    agg = np.zeros(len(common_ts), dtype=np.float64)
    for ts_list, arr in results:
        ts_to_val = dict(zip(ts_list, arr))
        for i, t in enumerate(common_ts):
            agg[i] += ts_to_val.get(t, 0.0)

    return common_ts, agg, succeeded


# ── display ───────────────────────────────────────────────────────────────────

def run_oi_display(btc_price: float | None = None) -> None:
    """
    Fetch and display the last 4 × 1H aggregated OI candles.
    Display mode, thresholds, and quoted currency are read from config.
    """
    mode = config.OI_DISPLAY_MODE
    if mode not in _VALID_MODES:
        console.print(f"[red]Unknown OI_DISPLAY_MODE {mode!r}. "
                      f"Valid: {', '.join(sorted(_VALID_MODES))}[/red]")
        return

    tf      = config.OI_TF
    candles = config.OI_CANDLES
    console.rule(f"[bold cyan]Open Interest — {mode} ({tf.upper()}, last {candles} bars)[/bold cyan]")

    # ── get BTC price ─────────────────────────────────────────────────────────
    if btc_price is None:
        try:
            from btc_agent.scanner.data import _get_exchange
            ex, sym = _get_exchange()
            ticker = ex.fetch_ticker(sym)
            btc_price = float(ticker["last"])
            console.print(f"[green]BTC price: ${btc_price:,.1f}[/green]")
        except Exception as e:
            console.print(f"[red]Could not fetch BTC price: {e}[/red]")
            return

    # ── aggregate OI ──────────────────────────────────────────────────────────
    timestamps, agg, sources_ok = _aggregate_oi(btc_price)
    n_total = len(_OI_SOURCES)
    n_ok = len(sources_ok)
    if n_ok == 0:
        console.print("[red]All OI sources failed — nothing to display.[/red]")
        return
    skipped = n_total - n_ok
    skip_note = f"  ({skipped} geo-blocked or unavailable)" if skipped else ""
    console.print(f"[dim]Sources: {n_ok}/{n_total} — {', '.join(sources_ok)}{skip_note}[/dim]")
    if agg is None or len(agg) < candles + 1:
        console.print("[red]Not enough OI data to display.[/red]")
        return

    n = len(agg)

    # ── convert aggregated BTC series to display units ────────────────────────
    # agg is in BTC; multiply by price for USD display, keep as-is for COIN
    display_agg = agg if config.OI_QUOTED_IN == "COIN" else agg * btc_price

    # ── compute display series ────────────────────────────────────────────────
    if mode == "Open Interest":
        series = display_agg.copy()

    elif mode == "Open Interest Delta":
        series = np.concatenate([[np.nan], np.diff(display_agg)])

    elif mode == "OID x rVOL":
        delta = np.concatenate([[np.nan], np.diff(display_agg)])
        vol = _fetch_1h_volume(btc_price)
        if vol is not None and len(vol) >= 20:
            vol = vol[-n:]
            if len(vol) < n:
                vol = np.pad(vol, (n - len(vol), 0), constant_values=np.nan)
            rvol = np.array([
                vol[i] / np.nanmean(vol[max(0, i - 19):i + 1]) if i >= 19 else np.nan
                for i in range(n)
            ])
            series = delta * rvol
        else:
            console.print("[yellow]rVOL: volume data unavailable — showing plain OI Delta[/yellow]")
            series = delta

    elif mode == "Open Interest RSI":
        series = _rsi(display_agg, config.OI_RSI_LEN)

    # ── compute thresholds (SMA-300 × mult) for delta-based modes ────────────
    p_thresh = n_thresh = None
    if config.OI_SHOW_THRESHOLDS and mode in ("Open Interest Delta", "OID x rVOL"):
        deltas = np.diff(display_agg)
        pos_d = deltas[deltas > 0][-300:]
        neg_d = deltas[deltas < 0][-300:]
        if len(pos_d) > 0:
            p_thresh = float(np.mean(pos_d)) * config.OI_THRESHOLD_MULT
        if len(neg_d) > 0:
            n_thresh = float(np.mean(neg_d)) * config.OI_THRESHOLD_MULT

    # ── build table ───────────────────────────────────────────────────────────
    show_thresh = (config.OI_SHOW_THRESHOLDS
                   and mode in ("Open Interest Delta", "OID x rVOL")
                   and (p_thresh is not None or n_thresh is not None))

    table = Table(
        title=f"Aggregated OI — {mode}  [{tf.upper()}]  (quoted in {config.OI_QUOTED_IN}  |  thresh ×{config.OI_THRESHOLD_MULT})",
        border_style="cyan",
    )
    table.add_column("Bar Open (IST)", style="cyan")
    table.add_column(mode, justify="right", style="bold white")
    if mode == "Open Interest RSI":
        table.add_column("Level", justify="center")
    if show_thresh:
        table.add_column("Thresh ↑", justify="right", style="green")
        table.add_column("Thresh ↓", justify="right", style="red")
        table.add_column("Signal", justify="center")

    # last N candles
    idx_range = range(max(0, n - candles), n)
    for i in idx_range:
        ts_str = _ts_to_ist(timestamps[i])
        val    = series[i]

        if np.isnan(val):
            val_str = "[dim]n/a[/dim]"
            row_style = None
        else:
            val_str = _fmt_value(val, mode, btc_price)

        row: list[str] = [ts_str, val_str]

        if mode == "Open Interest RSI" and not np.isnan(val):
            if val >= 70:
                level = "[bold red]Overbought[/bold red]"
            elif val <= 30:
                level = "[bold green]Oversold[/bold green]"
            else:
                level = "[dim]Neutral[/dim]"
            row.append(level)

        if show_thresh and not np.isnan(val):
            thresh_up_str = _fmt_delta(p_thresh) if p_thresh else "—"
            thresh_dn_str = _fmt_delta(n_thresh) if n_thresh else "—"

            large_up = p_thresh is not None and val > p_thresh
            large_dw = n_thresh is not None and val < n_thresh

            if large_up:
                signal = "[bold green]⚡ Large OI ↑[/bold green]"
                val_str = f"[bold green]{val_str}[/bold green]"
                row[1] = val_str
            elif large_dw:
                signal = "[bold red]⚡ Large OI ↓[/bold red]"
                val_str = f"[bold red]{val_str}[/bold red]"
                row[1] = val_str
            else:
                signal = "[dim]—[/dim]"

            row.extend([thresh_up_str, thresh_dn_str, signal])

        elif show_thresh and np.isnan(val):
            row.extend(["—", "—", "—"])

        table.add_row(*row)

    console.print(table)

    # ── RSI reference lines ───────────────────────────────────────────────────
    if mode == "Open Interest RSI":
        console.print("[dim]Reference: 70 = overbought  |  50 = mid  |  30 = oversold[/dim]")
