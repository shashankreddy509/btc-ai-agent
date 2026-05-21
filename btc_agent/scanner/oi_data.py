from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

_BASE = "https://fapi.binance.com"
_SYMBOL = "BTCUSDT"

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


def fetch_oi_snapshot(tf: int, lookback: int = 300) -> OISnapshot:
    period = _TF_TO_PERIOD.get(tf)
    if period is None:
        supported = [t for t in _TF_TO_PERIOD if t <= tf]
        if not supported:
            return OISnapshot(tf=tf, oi=[], ok=False)
        period = _TF_TO_PERIOD[max(supported)]

    agg = _TF_AGGREGATE.get(tf, 1)
    fetch_limit = min(lookback * agg, 500)

    url = (
        f"{_BASE}/futures/data/openInterestHist"
        f"?symbol={_SYMBOL}&period={period}&limit={fetch_limit}"
    )
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw: list[dict] = json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
        from rich.console import Console
        Console().print(f"[yellow][oi_data] fetch error (tf={tf}): {exc}[/yellow]")
        return OISnapshot(tf=tf, oi=[], ok=False)

    if not raw or not isinstance(raw, list):
        return OISnapshot(tf=tf, oi=[], ok=False)

    try:
        native_oi = [float(bar["sumOpenInterest"]) for bar in raw]
    except (KeyError, TypeError, ValueError) as exc:
        from rich.console import Console
        Console().print(f"[yellow][oi_data] parse error: {exc}[/yellow]")
        return OISnapshot(tf=tf, oi=[], ok=False)

    if agg > 1:
        trim = len(native_oi) - (len(native_oi) % agg)
        aggregated: list[float] = []
        for i in range(0, trim, agg):
            aggregated.append(sum(native_oi[i:i + agg]))
        oi_series = aggregated
    else:
        oi_series = native_oi

    return OISnapshot(tf=tf, oi=oi_series, ok=True)


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
