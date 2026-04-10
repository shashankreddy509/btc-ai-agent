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

    TradingView resets the bar grid at midnight UTC (19:00 CDT) every day.
    Each day gets floor(1440/tf) full-length bars starting at 00:00 UTC.
    When 1440 % tf != 0, a partial "stub" bar covers the remaining minutes
    of that day and is treated as a closed bar (just like TradingView shows
    it as a real candle before the session reset).

    Strategy (all vectorised, no Python loops except the final last_n slice):
      1. Assign each candle a bar-in-day slot; stub candles (tail of each day
         that don't fill a complete bar) get slot bars_per_day.
      2. Build a global bar index per candle using (bars_per_day + 1) slots/day
         so stub-bar-D never collides with bar0-day-(D+1).
      3. Find bar boundaries with np.diff → identify complete bars.
         A bar is "complete" if it has exactly tf_minutes candles (full bar)
         OR if it is a stub bar (always closed at the day boundary).
      4. Extract + aggregate the last last_n complete bars.

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
    bars_per_day = 1440 // tf_minutes          # full bars that fit in one day
    if bars_per_day == 0:
        return None, None

    max_minute = bars_per_day * tf_minutes     # stub candles start here

    # ── 1. Assign bar-in-day; stub candles get slot bars_per_day ─────────────
    bar_in_day = np.where(
        minutes_of_day < max_minute,
        minutes_of_day // tf_minutes,
        bars_per_day,                          # stub bar slot
    )

    # ── 2. Global bar index — (bars_per_day + 1) slots/day keeps stub-day-D
    #       distinct from bar0-day-(D+1). ──────────────────────────────────────
    global_bar = unix_days * (bars_per_day + 1) + bar_in_day

    # ── 3. Find bar boundaries and sizes ─────────────────────────────────────
    diffs      = np.diff(global_bar, prepend=global_bar[0] - 1)
    boundaries = np.where(diffs != 0)[0]          # start index of each bar
    bar_ends   = np.empty(len(boundaries), dtype=np.int64)
    bar_ends[:-1] = boundaries[1:]
    bar_ends[-1]  = len(arr_1m)
    bar_sizes  = bar_ends - boundaries            # candle count per bar

    # ── 4. Keep complete bars (full-length OR stub at day boundary) ───────────
    bar_in_day_at_start = bar_in_day[boundaries]
    is_stub       = bar_in_day_at_start == bars_per_day
    is_full       = bar_sizes == tf_minutes
    complete_mask = is_full | is_stub
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
        b = arr_1m[s:e]
        ohlcv[i, 0] = b[0,  0]          # open  (first 1m)
        ohlcv[i, 1] = b[:, 1].max()     # high
        ohlcv[i, 2] = b[:, 2].min()     # low
        ohlcv[i, 3] = b[-1, 3]          # close (last 1m)
        ohlcv[i, 4] = b[:, 4].sum()     # volume
        bar_ts[i]   = ts_1m[s]          # bar open time (Unix seconds)

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
