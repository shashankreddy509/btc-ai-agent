"""
Debug a specific timeframe — shows bars and exactly why patterns pass/fail.
Usage:  uv run python debug_tf.py 78
"""
import sys
import numpy as np
from datetime import datetime, timezone

from btc_agent.scanner.data import fetch_1m_candles
from btc_agent.scanner.aggregator import df_to_numpy

TF      = int(sys.argv[1]) if len(sys.argv) > 1 else 78
LAST_N  = 12

# ── Fetch & convert ───────────────────────────────────────────────────────────
print(f"\nFetching 1m data…")
df = fetch_1m_candles()
arr, ts, mod, days = df_to_numpy(df)

# ── Reproduce aggregator internals verbosely ──────────────────────────────────
bars_per_day = 1440 // TF
max_minute   = bars_per_day * TF
waste_per_day = 1440 - max_minute

print(f"\n{'─'*70}")
print(f"  {TF}m TF diagnostics")
print(f"{'─'*70}")
print(f"  bars_per_day  : {bars_per_day}")
print(f"  max_minute    : {max_minute}  (waste starts at {max_minute//60:02d}:{max_minute%60:02d} UTC)")
print(f"  waste/day     : {waste_per_day} min")
print(f"  total 1m bars : {len(arr)}")

# filter waste
valid      = mod < max_minute
arr_v      = arr[valid]
ts_v       = ts[valid]
mod_v      = mod[valid]
days_v     = days[valid]

print(f"  valid candles : {len(arr_v)}  (dropped {len(arr) - len(arr_v)} waste)")

# global bar index
bar_in_day_v = mod_v // TF
global_bar_v = days_v * bars_per_day + bar_in_day_v

# boundaries
diffs      = np.diff(global_bar_v, prepend=global_bar_v[0] - 1)
boundaries = np.where(diffs != 0)[0]
bar_ends   = np.empty(len(boundaries), dtype=np.int64)
bar_ends[:-1] = boundaries[1:]
bar_ends[-1]  = len(arr_v)
bar_sizes  = bar_ends - boundaries

total_bars = len(boundaries)
complete_mask = bar_sizes == TF
n_complete    = int(complete_mask.sum())

print(f"  total bars    : {total_bars}")
print(f"  complete bars : {n_complete}  (exactly {TF} candles each)")
print(f"  incomplete    : {total_bars - n_complete}")

# Show distribution of incomplete bar sizes
incomplete_sizes = bar_sizes[~complete_mask]
if len(incomplete_sizes) > 0:
    unique, counts = np.unique(incomplete_sizes, return_counts=True)
    print(f"  incomplete bar sizes: { {int(s): int(c) for s, c in zip(unique, counts)} }")

if n_complete < LAST_N:
    print(f"\n  ❌ Not enough complete bars: need {LAST_N}, have {n_complete}")
    sys.exit(1)

print(f"\n  ✅ Enough data — extracting last {LAST_N} complete bars\n")

# Extract last LAST_N complete bars
complete_positions = np.where(complete_mask)[0][-LAST_N:]

ohlcv  = np.empty((LAST_N, 5), dtype=np.float64)
bar_ts = np.empty(LAST_N, dtype=np.int64)
for i, pos in enumerate(complete_positions):
    s = int(boundaries[pos]); e = int(bar_ends[pos])
    b = arr_v[s:e]
    ohlcv[i]  = [b[0,0], b[:,1].max(), b[:,2].min(), b[-1,3], b[:,4].sum()]
    bar_ts[i] = ts_v[s]

# ── Print bars ────────────────────────────────────────────────────────────────
print(f"{'─'*95}")
print(f"  {'i':>2}  {'Bar Open (UTC)':<20} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10}  {'Color':<5}  {'Body':>9}")
print(f"{'─'*95}")
for i in range(LAST_N):
    dt    = datetime.fromtimestamp(int(bar_ts[i]), tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
    o,h,l,c,v = ohlcv[i]
    color = 'GREEN' if c > o else ('RED' if c < o else 'DOJI ')
    body  = abs(c - o)
    print(f"  {i:>2}  {dt:<20} {o:>10.1f} {h:>10.1f} {l:>10.1f} {c:>10.1f}  {color:<5}  {body:>9.1f}")
print(f"{'─'*95}")

# ── 4-Flag sliding window ─────────────────────────────────────────────────────
print(f"\n4-Flag checks (tolerance=30%):")
print(f"{'─'*75}")
for start in range(LAST_N - 3):
    w        = ohlcv[start:start+4]
    o_a, c_a = w[:, 0], w[:, 3]
    colors   = c_a > o_a
    alt1     = [True,  False, True,  False]
    alt2     = [False, True,  False, True]
    color_ok = list(colors) in (alt1, alt2)
    bodies   = np.abs(c_a - o_a)
    avg      = bodies.mean()
    max_dev  = avg * 0.30
    devs     = np.abs(bodies - avg)
    body_ok  = bool(np.all(devs <= max_dev)) if avg > 0 else False
    result   = "✅ PASS" if (color_ok and body_ok) else "❌ FAIL"
    end_i    = start + 3
    ts_end   = datetime.fromtimestamp(int(bar_ts[end_i]), tz=timezone.utc).strftime('%H:%M UTC')
    print(f"  bars[{start:>2}–{end_i:>2}] (last bar {ts_end})  colors={'OK  ' if color_ok else 'FAIL'}  body={'OK  ' if body_ok else 'FAIL'}  → {result}")
    if not color_ok:
        print(f"         colors: {[('G' if x else 'R') for x in colors.tolist()]}  (need G-R-G-R or R-G-R-G)")
    if not body_ok and avg > 0:
        pcts = (devs / avg * 100).round(1)
        print(f"         bodies : {bodies.round(1).tolist()}")
        print(f"         avg={avg:.1f}  max_dev={max_dev:.1f}")
        print(f"         % from avg: {pcts.tolist()}  (must all be ≤30%)")
print(f"{'─'*75}")
