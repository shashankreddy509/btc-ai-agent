import pandas as pd
import numpy as np
import requests


# ── 1. Fetch Binance USDT-M Futures OHLCV ────────────────────────────────────

def fetch_binance_perp(symbol='BTCUSDT', interval='1h', limit=200):
    """
    Fetch Binance perpetual futures OHLCV data.
    interval: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d

    """
    url = 'https://fapi.binance.com/fapi/v1/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}

    r = requests.get(url, params=params)
    r.raise_for_status()

    df = pd.DataFrame(r.json(), columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades',
        'taker_buy_base', 'taker_buy_quote', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    return df


# ── 2. Detect 4-Flag Pattern ──────────────────────────────────────────────────

def detect_4flag_pattern(df: pd.DataFrame, tolerance: float = 0.3) -> pd.DataFrame:
    """
    Detect GTI 4-Flag candlestick pattern.

    Rules:
      1. 4 consecutive alternating candles (bull-bear-bull-bear or bear-bull-bear-bull)
      2. All 4 candle body sizes are similar within tolerance (default 30%)

    Args:
        df        : DataFrame with columns open, high, low, close
        tolerance : Max allowed deviation from average body size (0.3 = 30%)

    Returns:
        df with added columns: bullish_4flag, bearish_4flag
    """
    df = df.copy()
    df['bullish_4flag'] = False
    df['bearish_4flag'] = False

    df['is_bull'] = df['close'] > df['open']
    df['body']    = (df['close'] - df['open']).abs()

    for i in range(3, len(df)):
        c = df.iloc[i-3:i+1]  # 4 candles

        directions = c['is_bull'].tolist()
        bodies     = c['body'].tolist()

        # Rule 1: Alternating candle directions
        alternating = all(directions[j] != directions[j+1] for j in range(3))
        if not alternating:
            continue

        # Rule 2: Similar body sizes within tolerance
        avg_body = np.mean(bodies)
        if avg_body == 0:
            continue

        similar = all(abs(b - avg_body) / avg_body <= tolerance for b in bodies)
        if not similar:
            continue

        # Classify: first candle determines pattern type
        # bear-bull-bear-bull → Bullish 4-Flag (expect bullish breakout)
        # bull-bear-bull-bear → Bearish 4-Flag (expect bearish breakdown)
        if directions[0] == False:
            df.at[df.index[i], 'bullish_4flag'] = True
        else:
            df.at[df.index[i], 'bearish_4flag'] = True

    df.drop(columns=['is_bull', 'body'], inplace=True)
    return df


# ── 3. Print Results ──────────────────────────────────────────────────────────

def print_signals(result: pd.DataFrame, symbol: str, interval: str):
    bull = result[result['bullish_4flag']]
    bear = result[result['bearish_4flag']]

    print("=" * 60)
    print(f"  GTI 4-Flag Pattern Detector | {symbol} | {interval}")
    print("=" * 60)
    print(f"  Total candles : {len(result)}")
    print(f"  Bullish flags : {len(bull)}")
    print(f"  Bearish flags : {len(bear)}")
    print("=" * 60)

    if not bull.empty:
        print("\n📈 Bullish 4-Flag Signals (bear-bull-bear-bull):")
        print(bull[['open', 'high', 'low', 'close']].to_string())

    if not bear.empty:
        print("\n📉 Bearish 4-Flag Signals (bull-bear-bull-bear):")
        print(bear[['open', 'high', 'low', 'close']].to_string())

    if bull.empty and bear.empty:
        print("\n  No 4-Flag signals found in this range.")

    print("\n  Latest candle:")
    print(f"  Time  : {result.index[-1]}")
    print(f"  Close : ${result['close'].iloc[-1]:,.2f}")
    print("=" * 60)


# ── 4. Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # Config
    SYMBOL    = 'BTCUSDT'
    INTERVAL  = '30m'      # change to 4h, 15m, etc.
    LIMIT     = 300       # number of candles
    TOLERANCE = 0.3       # 30% body size similarity

    # Run
    print(f"\nFetching {LIMIT} candles for {SYMBOL} ({INTERVAL})...")
    df     = fetch_binance_perp(SYMBOL, INTERVAL, LIMIT)
    result = detect_4flag_pattern(df, tolerance=TOLERANCE)
    print_signals(result, SYMBOL, INTERVAL)