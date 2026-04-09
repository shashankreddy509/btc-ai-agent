import numpy as np
import pandas as pd


def aggregate_tf(
    arr_1m: np.ndarray,
    ts_1m: np.ndarray,
    minutes_of_day: np.ndarray,
    unix_days: np.ndarray,
    tf_minutes: int,
    last_n: int = 10,
) -> tuple[np.ndarray, np.ndarray] | tuple[None, None]:
    """
    Aggregate 1m OHLCV into TF bars that match TradingView exactly.

    TradingView resets the bar grid at midnight UTC every day, so a 177m bar
    that would straddle midnight is dropped — each day gets floor(1440/tf)
    complete bars starting from 00:00 UTC.

    Strategy (all vectorised, no Python loops except the final last_n slice):
      1. Mark "waste" candles (tail of each day that doesn't fill a complete bar)
      2. Build a global bar index per candle: day × bars_per_day + bar_in_day
      3. Find bar boundaries with np.diff → identify complete bars (exactly tf candles)
      4. Extract + aggregate the last last_n complete bars

    Args:
        arr_1m         : shape (N, 5)  OHLCV, oldest-first
        ts_1m          : shape (N,)    Unix seconds of each candle open
        minutes_of_day : shape (N,)    minute-of-day UTC (0–1439) per candle
        unix_days      : shape (N,)    floor(ts / 86400) — Unix day index per candle
        tf_minutes     : target TF in minutes
        last_n         : number of complete bars to return

    Returns:
        (ohlcv, bar_open_times) — shape (last_n, 5) and (last_n,) Unix-seconds
        or (None, None) if not enough data.
    """
    bars_per_day = 1440 // tf_minutes          # complete bars that fit in one day
    if bars_per_day == 0:
        return None, None

    max_minute = bars_per_day * tf_minutes     # candles from here to 1439 are waste

    # ── 1. Filter out waste candles ───────────────────────────────────────────
    valid = minutes_of_day < max_minute
    arr_v   = arr_1m[valid]
    ts_v    = ts_1m[valid]
    mod_v   = minutes_of_day[valid]
    days_v  = unix_days[valid]

    if len(arr_v) < tf_minutes * last_n:
        return None, None

    # ── 2. Global bar index (monotonically non-decreasing) ────────────────────
    bar_in_day_v  = mod_v // tf_minutes
    global_bar_v  = days_v * bars_per_day + bar_in_day_v

    # ── 3. Find bar boundaries and sizes ─────────────────────────────────────
    diffs      = np.diff(global_bar_v, prepend=global_bar_v[0] - 1)
    boundaries = np.where(diffs != 0)[0]          # start index of each bar in arr_v
    bar_ends   = np.empty(len(boundaries), dtype=np.int64)
    bar_ends[:-1] = boundaries[1:]
    bar_ends[-1]  = len(arr_v)
    bar_sizes  = bar_ends - boundaries            # candle count per bar

    # ── 4. Keep only complete bars ────────────────────────────────────────────
    complete_mask = bar_sizes == tf_minutes
    n_complete    = int(complete_mask.sum())

    if n_complete < last_n:
        return None, None

    # Indices (into boundaries/bar_ends) of the last last_n complete bars
    complete_positions = np.where(complete_mask)[0][-last_n:]

    # ── 5. Aggregate each selected bar (last_n Python iterations) ────────────
    ohlcv   = np.empty((last_n, 5), dtype=np.float64)
    bar_ts  = np.empty(last_n,      dtype=np.int64)

    for i, pos in enumerate(complete_positions):
        s = int(boundaries[pos])
        e = int(bar_ends[pos])
        b = arr_v[s:e]                   # shape (tf_minutes, 5)
        ohlcv[i, 0] = b[0,  0]          # open  (first 1m)
        ohlcv[i, 1] = b[:, 1].max()     # high
        ohlcv[i, 2] = b[:, 2].min()     # low
        ohlcv[i, 3] = b[-1, 3]          # close (last 1m)
        ohlcv[i, 4] = b[:, 4].sum()     # volume
        bar_ts[i]   = ts_v[s]           # bar open time (Unix seconds)

    return ohlcv, bar_ts


def df_to_numpy(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Convert 1m DataFrame to numpy arrays.

    Returns:
        arr            : shape (N, 5)  OHLCV float64
        ts             : shape (N,)    Unix seconds int64 (candle open time)
        minutes_of_day : shape (N,)    minute-of-day UTC (0–1439)
        unix_days      : shape (N,)    Unix day index (ts // 86400)
    """
    arr  = df[["open", "high", "low", "close", "volume"]].to_numpy(dtype=np.float64)
    # Use epoch subtraction — works for both datetime64[ns, UTC] (pandas < 2.0)
    # and datetime64[ms, UTC] (pandas 2.0+). Avoids the astype("int64") precision
    # ambiguity where pandas 2.0 returns milliseconds instead of nanoseconds.
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    ts    = ((df["timestamp"] - epoch).dt.total_seconds()).to_numpy().astype(np.int64)
    minutes_of_day = ((ts % 86400) // 60).astype(np.int64)
    unix_days      = (ts // 86400).astype(np.int64)
    return arr, ts, minutes_of_day, unix_days
