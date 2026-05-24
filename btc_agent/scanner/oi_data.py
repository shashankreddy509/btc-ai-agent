from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

_BASE_USDT = "https://fapi.binance.com"   # USDT-margined perpetuals (OI in BTC)
_BASE_COIN = "https://dapi.binance.com"   # COIN-margined perpetuals (OI in contracts, 1 contract = $100)
_SYMBOL_USDT = "BTCUSDT"
_SYMBOL_COIN = "BTCUSD_PERP"
_BASE = _BASE_USDT  # kept for backward compat
_SYMBOL = _SYMBOL_USDT

_TF_TO_PERIOD: dict[int, str] = {
    5:  "5m",
    15: "15m",
    30: "30m",
    45: "15m",
    60: "1h",
    90: "30m",
}
_TF_AGGREGATE: dict[int, int] = {45: 3, 90: 3}


@dataclass
class OISnapshot:
    tf: int
    oi: list[float]
    ok: bool = True


@dataclass
class OISignals:
    large_oi_up: bool = False
    large_oi_down: bool = False
    bull_div: bool = False
    bear_div: bool = False
    latest_delta: float = 0.0
    p_thresh: float = 0.0
    n_thresh: float = 0.0
    ok: bool = True


def _fetch_btc_price() -> float:
    """Fetch current BTC/USDT price from Binance spot — needed to convert USDT-M OI (BTC) to USD."""
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return float(json.loads(resp.read())["price"])
    except Exception:
        return 0.0


def _fetch_raw_oi(base: str, symbol: str, period: str, limit: int, field: str = "sumOpenInterest") -> list[float]:
    """Fetch raw OI series from Binance (USDT-M or COIN-M)."""
    url = f"{base}/futures/data/openInterestHist?symbol={symbol}&period={period}&limit={limit}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw: list[dict] = json.loads(resp.read())
        if not raw or not isinstance(raw, list):
            return []
        return [float(bar[field]) for bar in raw]
    except Exception as exc:
        from rich.console import Console
        Console().print(f"[yellow][oi_data] fetch error ({base}): {exc}[/yellow]")
        return []


def _aggregate(series: list[float], agg: int) -> list[float]:
    if agg <= 1:
        return series
    trim = len(series) - (len(series) % agg)
    return [sum(series[i:i + agg]) for i in range(0, trim, agg)]


def fetch_oi_snapshot(tf: int, lookback: int = 300) -> OISnapshot:
    period = _TF_TO_PERIOD.get(tf)
    if period is None:
        supported = [t for t in _TF_TO_PERIOD if t <= tf]
        if not supported:
            return OISnapshot(tf=tf, oi=[], ok=False)
        period = _TF_TO_PERIOD[max(supported)]

    agg = _TF_AGGREGATE.get(tf, 1)
    fetch_limit = min(lookback * agg, 500)

    # Fetch current BTC price for USDT-M conversion
    btc_price = _fetch_btc_price()

    # USDT-M: OI in BTC → convert to USD millions
    raw_usdt = _fetch_raw_oi(_BASE_USDT, _SYMBOL_USDT, period, fetch_limit)
    usdt_m = _aggregate(raw_usdt, agg)
    # Each unit = 1 BTC. Convert: BTC × price / 1_000_000
    usdt_usd = [v * btc_price / 1_000_000 for v in usdt_m] if btc_price else usdt_m

    # COIN-M: OI in contracts (1 contract = $100) → USD millions
    raw_coin = _fetch_raw_oi(_BASE_COIN, _SYMBOL_COIN, period, fetch_limit)
    coin_m = _aggregate(raw_coin, agg)
    # Each unit = 1 contract = $100. Convert: contracts × 100 / 1_000_000
    coin_usd = [v * 100 / 1_000_000 for v in coin_m]

    if not usdt_usd and not coin_usd:
        return OISnapshot(tf=tf, oi=[], ok=False)

    # Align lengths and sum
    if usdt_usd and coin_usd:
        n = min(len(usdt_usd), len(coin_usd))
        combined = [usdt_usd[-(n - i)] + coin_usd[-(n - i)] for i in range(n - 1, -1, -1)]
    else:
        combined = usdt_usd or coin_usd

    return OISnapshot(tf=tf, oi=combined, ok=True)


def compute_oi_signals(
    snapshot: OISnapshot,
    closes: list[float],
    mult: float = 4.0,
    div_lookback: int = 5,
) -> OISignals:
    if not snapshot.ok or len(snapshot.oi) < 2:
        return OISignals(ok=False)

    oi = snapshot.oi
    # Align lengths
    n = min(len(oi), len(closes)) if closes else len(oi)
    oi = oi[-n:]
    closes_aligned = closes[-n:] if closes else []

    deltas = [oi[i] - oi[i - 1] for i in range(1, len(oi))]
    if not deltas:
        return OISignals(ok=False)

    last_delta = deltas[-1]

    pos_deltas = [d for d in deltas if d > 0]
    neg_deltas = [d for d in deltas if d < 0]

    p_thresh = (sum(pos_deltas) / len(pos_deltas) * mult) if pos_deltas else float("inf")
    n_thresh = (sum(neg_deltas) / len(neg_deltas) * mult) if neg_deltas else float("-inf")

    large_oi_up   = last_delta > p_thresh
    large_oi_down = last_delta < n_thresh

    bull_div = bear_div = False
    if closes_aligned and n >= div_lookback + 1:
        price_window = closes_aligned[-(div_lookback + 1):]
        oi_window    = oi[-(div_lookback + 1):]

        price_new_lo = closes_aligned[-1] <= min(price_window[:-1])
        price_new_hi = closes_aligned[-1] >= max(price_window[:-1])
        oi_not_new_lo = oi[-1] > min(oi_window[:-1])
        oi_not_new_hi = oi[-1] < max(oi_window[:-1])

        bull_div = price_new_lo and oi_not_new_lo and last_delta < 0 and not large_oi_down
        bear_div = price_new_hi and oi_not_new_hi and last_delta > 0 and not large_oi_up

    return OISignals(
        large_oi_up=large_oi_up,
        large_oi_down=large_oi_down,
        bull_div=bull_div,
        bear_div=bear_div,
        latest_delta=last_delta,
        p_thresh=p_thresh if p_thresh != float("inf") else 0.0,
        n_thresh=n_thresh if n_thresh != float("-inf") else 0.0,
        ok=True,
    )
