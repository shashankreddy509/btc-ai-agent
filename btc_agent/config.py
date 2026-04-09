import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

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

# DEPO parameters
DEPO_START = 126208
DEPO_STEP = 1700
DEPO_STOP = 45000
