"""Daily Markov regime computation for BTC-USD.

App-level singleton (not per-user). Fetches 60 days of daily BTC-USD data,
labels each day Bull/Bear/Sideways via 20-day rolling return, builds a 3×3
transition matrix, and reports the current regime + conviction score.

Writes each day's prediction to Firestore regime_log/{YYYY-MM-DD} and fills
in the actual regime the next morning for forward-testing validation.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from rich.console import Console

console = Console()

_cache: dict | None = None
_cache_date: str = ""
_cache_lock = threading.Lock()
_last_attempt: float = 0.0
_RETRY_GAP = 300.0  # 5 minutes between retries on failure

_STATES = ["Bear", "Sideways", "Bull"]
_WINDOW = 20
_THRESHOLD = 0.02


def _fetch_close() -> pd.Series:
    import yfinance as yf
    df = yf.download("BTC-USD", period="60d", interval="1d",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df["Close"].dropna()


def _label(close: pd.Series) -> pd.Series:
    rolling = close.pct_change(_WINDOW)
    labels = pd.Series(1, index=close.index, dtype=int)
    labels[rolling > _THRESHOLD] = 2
    labels[rolling < -_THRESHOLD] = 0
    return labels.dropna()


def _transition_matrix(labels: pd.Series) -> np.ndarray:
    counts = np.zeros((3, 3), dtype=float)
    arr = labels.to_numpy()
    for i in range(len(arr) - 1):
        counts[arr[i], arr[i + 1]] += 1
    row_sums = counts.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    return counts / row_sums


def _compute_regime() -> dict:
    """Fetch data, compute regime, validate yesterday, write to Firestore."""
    close = _fetch_close()
    if len(close) < _WINDOW + 2:
        raise ValueError(f"insufficient data: {len(close)} rows")

    labels = _label(close)
    P = _transition_matrix(labels)
    current_state = int(labels.iloc[-1])
    conviction = float(P[current_state, 2] - P[current_state, 0])

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = {
        "date": today_str,
        "regime": _STATES[current_state],
        "conviction": round(conviction, 4),
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }

    # Fill in yesterday's actual regime
    try:
        _validate_yesterday(labels, today_str)
    except Exception as e:
        console.print(f"[dim yellow]Regime: yesterday validation skipped: {e}[/dim yellow]")

    # Write today's prediction
    try:
        from btc_agent.trading import firestore_store as _fs
        _fs.save_regime_prediction(today_str, {
            "date": today_str,
            "predicted_regime": result["regime"],
            "conviction": result["conviction"],
            "computed_at": result["computed_at"],
            "actual_regime": None,
            "correct": None,
        })
    except Exception as e:
        console.print(f"[dim yellow]Regime: Firestore write skipped: {e}[/dim yellow]")

    return result


def _validate_yesterday(labels: pd.Series, today_str: str) -> None:
    """Compute yesterday's actual regime label and update Firestore."""
    from btc_agent.trading import firestore_store as _fs

    yesterday = (datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).__class__.fromisoformat(today_str.replace("Z", "+00:00")
    ) if False else datetime.now(timezone.utc))

    # Derive yesterday's date string from the second-to-last label's index
    if len(labels) < 2:
        return
    yesterday_ts = labels.index[-2]
    yesterday_str = pd.Timestamp(yesterday_ts).strftime("%Y-%m-%d")
    actual_state = int(labels.iloc[-2])
    actual_regime = _STATES[actual_state]

    # We need the predicted regime for yesterday to know if it was correct
    try:
        db_result = _fs.get_regime_prediction(yesterday_str)
        if db_result and db_result.get("actual_regime") is None:
            predicted = db_result.get("predicted_regime", "")
            correct = predicted == actual_regime
            _fs.update_regime_actual(yesterday_str, actual_regime, correct)
    except Exception as e:
        console.print(f"[dim yellow]Regime: could not read yesterday's prediction: {e}[/dim yellow]")


def _run_refresh() -> None:
    """Background thread target — compute and cache regime."""
    global _cache, _cache_date, _last_attempt
    _last_attempt = time.monotonic()
    try:
        result = _compute_regime()
        with _cache_lock:
            _cache = result
            _cache_date = result["date"]
        console.print(
            f"[dim]Regime — {result['regime']} "
            f"(conviction={result['conviction']:+.2f})[/dim]"
        )
    except Exception as e:
        console.print(f"[yellow]Regime computation failed: {e}[/yellow]")
        with _cache_lock:
            if _cache is None:
                _cache = {"error": str(e)}


def get_regime() -> dict | None:
    """Return cached regime. Thread-safe, no I/O."""
    with _cache_lock:
        return dict(_cache) if _cache else None


def refresh_regime_blocking() -> dict | None:
    """Synchronous refresh — called once at scanner startup."""
    global _cache, _cache_date, _last_attempt
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _cache_lock:
        if _cache_date == today_str and _cache and not _cache.get("error"):
            return dict(_cache)
    _last_attempt = time.monotonic()
    try:
        result = _compute_regime()
        with _cache_lock:
            _cache = result
            _cache_date = result["date"]
        return result
    except Exception as e:
        console.print(f"[yellow]Regime init failed: {e}[/yellow]")
        with _cache_lock:
            if _cache is None:
                _cache = {"error": str(e)}
        return None


def refresh_regime_if_stale() -> None:
    """Non-blocking daily refresh — called inside the scan-interval block."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _cache_lock:
        already_done = (_cache_date == today_str and _cache and not _cache.get("error"))
        too_soon = (time.monotonic() - _last_attempt) < _RETRY_GAP
    if already_done or too_soon:
        return
    t = threading.Thread(target=_run_refresh, daemon=True, name="regime-refresh")
    t.start()
