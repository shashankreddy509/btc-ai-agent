"""Multi-ticker Markov regime engine.

Computes Bull/Bear/Sideways regime + conviction for a configurable set of
tickers. Runs daily at 7 AM CST (13:00 UTC) via scheduler, stores predictions
to Firestore ticker_regime_log, validates previous day's actual regime.

Data window: 2 years per ticker (~2 min total for all defaults).
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from rich.console import Console

console = Console()

DEFAULT_US: list[tuple[str, str]] = [
    ("SPY",     "US"),
    ("QQQ",     "US"),
    ("AAPL",    "US"),
    ("MSFT",    "US"),
    ("NVDA",    "US"),
    ("TSLA",    "US"),
    ("GOOGL",   "US"),
    ("AMZN",    "US"),
    ("BTC-USD", "US"),
]

DEFAULT_IN: list[tuple[str, str]] = [
    ("^NSEI",        "IN"),
    ("^BSESN",       "IN"),
    ("RELIANCE.NS",  "IN"),
    ("TCS.NS",       "IN"),
    ("INFY.NS",      "IN"),
    ("HDFCBANK.NS",  "IN"),
]

_PERIOD    = "2y"
_WINDOW    = 20
_THRESHOLD = 0.02
_STATES    = ["Bear", "Sideways", "Bull"]

_cache: dict[str, dict] = {}
_cache_date: str = ""
_cache_lock = threading.Lock()


def _safe_ticker_id(ticker: str) -> str:
    """Make ticker safe for Firestore document IDs."""
    return ticker.replace("^", "X").replace(".", "_").replace("/", "-")


def _fetch_close(ticker: str) -> pd.Series:
    import yfinance as yf
    df = yf.download(ticker, period=_PERIOD, interval="1d",
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


def _stationary(P: np.ndarray) -> list[float]:
    eigvals, eigvecs = np.linalg.eig(P.T)
    idx = int(np.argmin(np.abs(eigvals - 1.0)))
    vec = np.real(eigvecs[:, idx])
    vec = np.abs(vec)
    vec = vec / vec.sum()
    return [round(float(v), 4) for v in vec]


def compute_regime(ticker: str, market: str = "US") -> dict:
    """Fetch 2y data, compute regime + conviction + stationary distribution."""
    close = _fetch_close(ticker)
    if len(close) < _WINDOW + 2:
        raise ValueError(f"insufficient data: {len(close)} rows")

    labels = _label(close)
    P = _transition_matrix(labels)
    current_state = int(labels.iloc[-1])
    conviction = float(P[current_state, 2] - P[current_state, 0])
    stat = _stationary(P)

    return {
        "ticker":      ticker,
        "market":      market,
        "date":        datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "regime":      _STATES[current_state],
        "conviction":  round(conviction, 4),
        "stationary":  stat,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "error":       None,
        "_labels":     labels,   # internal — not stored to Firestore
        "_close":      close,    # internal
    }


def _validate_yesterday(ticker: str, labels: pd.Series, today_str: str) -> None:
    from btc_agent.trading import firestore_store as _fs
    from datetime import timedelta

    if len(labels) < 1:
        return
    # yesterday = calendar day before today_str (that's the prediction doc to validate)
    yesterday_str = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    # actual = last label in series (most recent market close = yesterday's data)
    actual_state = int(labels.iloc[-1])
    actual_regime = _STATES[actual_state]

    try:
        doc = _fs.get_ticker_regime_prediction(ticker, yesterday_str)
        if doc and doc.get("actual_regime") is None:
            predicted = doc.get("predicted_regime", "")
            correct = predicted == actual_regime
            _fs.update_ticker_regime_actual(ticker, yesterday_str, actual_regime, correct)
    except Exception as e:
        console.print(f"[dim yellow]Markov: yesterday validation failed for {ticker}: {e}[/dim yellow]")


def _get_custom_tickers() -> list[tuple[str, str]]:
    try:
        from btc_agent.trading.firestore_store import load_app_settings
        settings = load_app_settings() or {}
        custom = settings.get("markov_custom_tickers", [])
        if isinstance(custom, str):
            custom = [t.strip() for t in custom.split(",") if t.strip()]
        return [(t, "custom") for t in custom if t]
    except Exception:
        return []


def refresh_all_tickers() -> dict[str, dict]:
    """Run regime computation for all tickers. Called by scheduler at 13:00 UTC."""
    from btc_agent.trading import firestore_store as _fs

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_tickers = DEFAULT_US + DEFAULT_IN + _get_custom_tickers()
    results: dict[str, dict] = {}

    console.print(f"[cyan]Markov refresh — {len(all_tickers)} tickers[/cyan]")
    for ticker, market in all_tickers:
        try:
            r = compute_regime(ticker, market)
            labels = r.pop("_labels")
            r.pop("_close")

            results[ticker] = r

            _fs.save_ticker_regime_prediction(ticker, market, today_str, {
                "ticker":           ticker,
                "market":           market,
                "date":             today_str,
                "predicted_regime": r["regime"],
                "conviction":       r["conviction"],
                "stationary":       r["stationary"],
                "computed_at":      r["computed_at"],
                "actual_regime":    None,
                "correct":          None,
            })

            _validate_yesterday(ticker, labels, today_str)
            console.print(f"[dim]  {ticker:<15} {r['regime']:<9} {r['conviction']:+.2f}[/dim]")
        except Exception as e:
            console.print(f"[yellow]  {ticker}: failed — {e}[/yellow]")
            results[ticker] = {"ticker": ticker, "market": market, "error": str(e)}

    with _cache_lock:
        _cache.update(results)
        global _cache_date
        _cache_date = today_str

    console.print(f"[green]Markov refresh done — {today_str}[/green]")
    return results


def get_all_regimes() -> dict[str, dict]:
    """Return copy of in-memory cache. Thread-safe, no I/O."""
    with _cache_lock:
        return {k: dict(v) for k, v in _cache.items()}


def get_ticker_regime(ticker: str) -> dict | None:
    with _cache_lock:
        r = _cache.get(ticker)
        return dict(r) if r else None
