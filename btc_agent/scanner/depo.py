import numpy as np
from btc_agent import config


def generate_depo_lines() -> np.ndarray:
    """
    Generate DEPO price levels starting from DEPO_START, subtracting DEPO_STEP
    each time until the level would fall below DEPO_STOP.

    Default: 126208 → 46308 in steps of 1700 (48 levels).
    """
    levels = []
    current = float(config.DEPO_START)
    while current >= config.DEPO_STOP:
        levels.append(current)
        current -= config.DEPO_STEP
    return np.array(levels, dtype=np.float64)


def check_depo(bars: np.ndarray, depo_lines: np.ndarray) -> float | None:
    """
    Return the first (highest) DEPO line that any candle in `bars` brackets.
    A candle brackets a DEPO line when: candle_low <= depo <= candle_high.
    No tolerance applied — exact crossing only.

    bars: shape (N, 5) — [open, high, low, close, volume]
    depo_lines: shape (M,) — descending price levels
    """
    lows  = bars[:, 2]  # shape (N,)
    highs = bars[:, 1]  # shape (N,)

    # Broadcast: (N, 1) vs (M,) → (N, M) boolean matrix
    hit_matrix = (lows[:, None] <= depo_lines) & (depo_lines <= highs[:, None])

    # Which DEPO lines are touched by at least one candle?
    hit_cols = np.any(hit_matrix, axis=0)  # shape (M,)
    if not np.any(hit_cols):
        return None

    # Return the highest level (first in descending list) that was hit
    return float(depo_lines[np.argmax(hit_cols)])


def next_depo_level(depo_lines: np.ndarray, touched_level: float, direction: str) -> float | None:
    """Return the adjacent DEPO level in the trade direction from the touched level."""
    if direction == "long":
        candidates = depo_lines[depo_lines > touched_level]
        return float(candidates.min()) if len(candidates) else None
    else:
        candidates = depo_lines[depo_lines < touched_level]
        return float(candidates.max()) if len(candidates) else None
