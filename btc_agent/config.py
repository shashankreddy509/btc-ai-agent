import os
import re
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL   = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")

BRIEFING_TIME = os.getenv("BRIEFING_TIME", "07:30")
SCANNER_TIME = os.getenv("SCANNER_TIME", "08:00")

# Run scanner every N minutes. If set, overrides SCANNER_TIME daily schedule.
_scanner_interval = os.getenv("SCANNER_INTERVAL_MIN", "").strip()
SCANNER_INTERVAL_MIN: int | None = int(_scanner_interval) if _scanner_interval else None

DELIVERY_CHANNELS = [
    ch.strip()
    for ch in os.getenv("DELIVERY_CHANNELS", "terminal").split(",")
    if ch.strip()
]

SCANNER_TF_MIN = int(os.getenv("SCANNER_TF_MIN", "30"))
SCANNER_TF_MAX = int(os.getenv("SCANNER_TF_MAX", "1440"))

# Comma-separated list of patterns to scan for.
# Valid values: 4-Flag, Morning Star, Evening Star
# Default: all three
SCANNER_PATTERNS = [
    p.strip()
    for p in os.getenv("SCANNER_PATTERNS", "4-Flag,Morning Star,Evening Star").split(",")
    if p.strip()
]


# ── Trading scanner ───────────────────────────────────────────────────────────
TRADING_TF_MIN            = int(os.getenv("TRADING_TF_MIN", "15"))
TRADING_TF_MAX            = int(os.getenv("TRADING_TF_MAX", "90"))
TRADING_SCAN_INTERVAL_MIN = int(os.getenv("TRADING_SCAN_INTERVAL_MIN", "5"))
TRADING_PATTERNS          = [p.strip() for p in os.getenv("TRADING_PATTERNS", "4-Flag,Engulfing").split(",") if p.strip()]
TRADING_MODE              = os.getenv("TRADING_MODE", "paper")        # "paper" | "live"
TRADING_MAX_CONCURRENT    = int(os.getenv("TRADING_MAX_CONCURRENT", "1"))   # 0 = unlimited
TRADING_QTY               = int(os.getenv("TRADING_QTY", "2"))        # contracts (min 2 for partial close)
TRADING_MAX_SL            = float(os.getenv("TRADING_MAX_SL", "500"))
TRADING_MIN_TP            = float(os.getenv("TRADING_MIN_TP", "500"))
WEEKLY_ADJ                = float(os.getenv("WEEKLY_ADJ", "0.0324"))

# Coinbase Advanced Trade
COINBASE_API_KEY          = os.getenv("COINBASE_API_KEY", "")
COINBASE_API_SECRET       = os.getenv("COINBASE_API_SECRET", "")
COINBASE_PRODUCT_ID       = os.getenv("COINBASE_PRODUCT_ID", "BTC-PERP-INTX")
COINBASE_CONTRACT_SIZE    = float(os.getenv("COINBASE_CONTRACT_SIZE", "0.001"))  # BTC per contract

# DEPO parameters
DEPO_START = 126208
DEPO_STEP = 1700
DEPO_STOP = 45000

_VALID_PATTERNS = {"4-Flag", "Morning Star", "Evening Star", "Bullish Engulfing", "Bearish Engulfing"}


def _validate() -> None:
    errors = []
    if not (1 <= SCANNER_TF_MIN <= SCANNER_TF_MAX <= 1440):
        errors.append(f"Invalid TF range: {SCANNER_TF_MIN}–{SCANNER_TF_MAX} (must be 1–1440 with MIN ≤ MAX)")
    for p in SCANNER_PATTERNS:
        if p not in _VALID_PATTERNS:
            errors.append(f"Unknown pattern: {p!r} (valid: {', '.join(sorted(_VALID_PATTERNS))})")
    if not (1 <= EMAIL_SMTP_PORT <= 65535):
        errors.append(f"Invalid EMAIL_SMTP_PORT: {EMAIL_SMTP_PORT}")
    for name, val in [("BRIEFING_TIME", BRIEFING_TIME), ("SCANNER_TIME", SCANNER_TIME)]:
        if not re.match(r"^\d{2}:\d{2}$", val):
            errors.append(f"{name} must be HH:MM, got {val!r}")
    if errors:
        raise ValueError("Config errors:\n" + "\n".join(f"  • {e}" for e in errors))


_validate()
