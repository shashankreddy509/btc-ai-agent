"""
Pattern detection functions.
Each accepts bars: np.ndarray of shape (N, 5) — [open, high, low, close, volume], oldest first.
Returns True if the pattern is found in the last N candles.
"""

import numpy as np

# Minimum body size as a fraction of price (filters out doji-noise on candle 1/3)
_MIN_BODY_PCT = 0.003
# Star body must be less than this fraction of the first candle's body
_STAR_BODY_RATIO = 0.30
# 4-flag: max allowed deviation of each candle's body from the average body size (matches Pine Script default 30%)
_FLAG_BODY_TOLERANCE_PCT = 0.30
# Morning/Evening star: candle 3 must close beyond this fraction into candle 1's body
_STAR_PENETRATION = 0.50


def detect_4flag(bars: np.ndarray, tolerance_pct: float = _FLAG_BODY_TOLERANCE_PCT) -> bool:
    """
    4 Flags Whale Pattern — matches the Pine Script logic exactly:

    1. Alternating candle colors: (G-R-G-R) or (R-G-R-G), oldest → newest
    2. All 4 body sizes are similar: each body must be within `tolerance_pct`
       (default 30%) of the average body size across the 4 candles.

    Pine Script reference:
        avg = (b0 + b1 + b2 + b3) / 4
        maxDev = avg * (tolerancePct / 100)
        all bodies within maxDev of avg
    """
    if len(bars) < 4:
        return False
    b = bars[-4:]
    opens  = b[:, 0]
    closes = b[:, 3]

    # 1. Alternating colors (True = green/bullish)
    colors = closes > opens          # strict: doji excluded
    alt1 = [True,  False, True,  False]
    alt2 = [False, True,  False, True]
    if list(colors) not in (alt1, alt2):
        return False

    # 2. Body sizes all similar — exact Pine Script formula
    bodies  = np.abs(closes - opens)  # shape (4,)
    avg     = bodies.mean()
    if avg == 0:
        return False
    max_dev = avg * tolerance_pct
    return bool(np.all(np.abs(bodies - avg) <= max_dev))


def detect_morning_star(bars: np.ndarray) -> bool:
    """
    Bullish 3-candle reversal:
      Bar 0: large bearish candle
      Bar 1: small star body (< 30% of bar 0 body)
      Bar 2: large bullish candle closing > 50% into bar 0's body
    """
    if len(bars) < 3:
        return False
    b = bars[-3:]
    o0, c0 = b[0, 0], b[0, 3]
    o1, c1 = b[1, 0], b[1, 3]
    o2, c2 = b[2, 0], b[2, 3]

    body0 = abs(c0 - o0)
    body1 = abs(c1 - o1)

    # Candle 0: bearish with meaningful body
    if c0 >= o0:
        return False
    if o0 == 0 or body0 / o0 < _MIN_BODY_PCT:
        return False

    # Candle 1: small star
    if body1 >= _STAR_BODY_RATIO * body0:
        return False

    # Candle 2: bullish
    if c2 <= o2:
        return False

    # Candle 2 must close above _STAR_PENETRATION into candle 0's body
    # Candle 0 is bearish: body top = o0, body bottom = c0
    midpoint = c0 + (o0 - c0) * _STAR_PENETRATION
    return c2 >= midpoint


def detect_evening_star(bars: np.ndarray) -> bool:
    """
    Bearish 3-candle reversal:
      Bar 0: large bullish candle
      Bar 1: small star body (< 30% of bar 0 body)
      Bar 2: large bearish candle closing > 50% into bar 0's body
    """
    if len(bars) < 3:
        return False
    b = bars[-3:]
    o0, c0 = b[0, 0], b[0, 3]
    o1, c1 = b[1, 0], b[1, 3]
    o2, c2 = b[2, 0], b[2, 3]

    body0 = abs(c0 - o0)
    body1 = abs(c1 - o1)

    # Candle 0: bullish with meaningful body
    if c0 <= o0:
        return False
    if o0 == 0 or body0 / o0 < _MIN_BODY_PCT:
        return False

    # Candle 1: small star
    if body1 >= _STAR_BODY_RATIO * body0:
        return False

    # Candle 2: bearish
    if c2 >= o2:
        return False

    # Candle 2 must close below _STAR_PENETRATION into candle 0's body
    # Candle 0 is bullish: body bottom = o0, body top = c0
    midpoint = c0 - (c0 - o0) * _STAR_PENETRATION
    return c2 <= midpoint


def detect_engulfing(bars: np.ndarray) -> tuple[bool, str]:
    """
    Bullish engulfing: bars[-2] is bearish, bars[-1] is bullish and fully engulfs bars[-2] body.
    Bearish engulfing: bars[-2] is bullish, bars[-1] is bearish and fully engulfs bars[-2] body.
    Returns (detected, direction)  — direction is 'bullish' | 'bearish' | ''.
    """
    if len(bars) < 2:
        return False, ""
    o1, c1 = bars[-2, 0], bars[-2, 3]   # previous candle
    o2, c2 = bars[-1, 0], bars[-1, 3]   # current candle
    body1_hi, body1_lo = max(o1, c1), min(o1, c1)
    body2_hi, body2_lo = max(o2, c2), min(o2, c2)
    if o1 == 0 or (body1_hi - body1_lo) / o1 < _MIN_BODY_PCT:
        return False, ""
    if o2 == 0 or (body2_hi - body2_lo) / o2 < _MIN_BODY_PCT:
        return False, ""
    if c1 < o1 and c2 > o2 and body2_hi >= body1_hi and body2_lo <= body1_lo:
        return True, "bullish"
    if c1 > o1 and c2 < o2 and body2_hi >= body1_hi and body2_lo <= body1_lo:
        return True, "bearish"
    return False, ""


PATTERNS = {
    "4-Flag":       detect_4flag,
    "Morning Star": detect_morning_star,
    "Evening Star": detect_evening_star,
}
