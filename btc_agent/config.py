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
TRADING_QTY               = max(2, int(float(os.getenv("TRADING_QTY", "2"))))  # contracts (min 2 for partial close)
TRADING_MAX_SL            = float(os.getenv("TRADING_MAX_SL", "500"))
TRADING_MIN_TP            = float(os.getenv("TRADING_MIN_TP", "500"))
TRADING_BIAS_FILTER       = os.getenv("TRADING_BIAS_FILTER", "false").lower() == "true"
BSG_ENABLED               = os.getenv("BSG_ENABLED", "false").lower() == "true"
BSG_TRADE_ENABLED         = os.getenv("BSG_TRADE_ENABLED", "false").lower() == "true"
TRADING_DAILY_PTS_TARGET  = float(os.getenv("TRADING_DAILY_PTS_TARGET", "0.0"))  # 0 = unlimited
TRADING_CME_CLOSE_SKIP    = os.getenv("TRADING_CME_CLOSE_SKIP", "false").lower() == "true"
WEEKLY_ADJ                = float(os.getenv("WEEKLY_ADJ", "0.0324"))

# Firebase owner UID — Coinbase keys stored in Firestore are tied to this UID
FIREBASE_OWNER_UID        = os.getenv("FIREBASE_OWNER_UID", "")
FIREBASE_ADMIN_EMAIL      = os.getenv("FIREBASE_ADMIN_EMAIL", "shashankreddy509@gmail.com")

# Firebase Web SDK config (client-side, not secret but kept out of source)
FIREBASE_WEB_API_KEY         = os.getenv("FIREBASE_WEB_API_KEY", "")
FIREBASE_AUTH_DOMAIN         = os.getenv("FIREBASE_AUTH_DOMAIN", "")
FIREBASE_PROJECT_ID          = os.getenv("FIREBASE_PROJECT_ID", "")
FIREBASE_STORAGE_BUCKET      = os.getenv("FIREBASE_STORAGE_BUCKET", "")
FIREBASE_MESSAGING_SENDER_ID = os.getenv("FIREBASE_MESSAGING_SENDER_ID", "")
FIREBASE_APP_ID              = os.getenv("FIREBASE_APP_ID", "")
VISHAL_ENABLED            = False

# Broker selection
TRADING_BROKER            = os.getenv("TRADING_BROKER", "coinbase")

# Coinbase Advanced Trade
COINBASE_API_KEY          = os.getenv("COINBASE_API_KEY", "")
COINBASE_API_SECRET       = os.getenv("COINBASE_API_SECRET", "")
COINBASE_PRODUCT_ID       = os.getenv("COINBASE_PRODUCT_ID", "BTC-PERP-INTX")
COINBASE_CONTRACT_SIZE    = float(os.getenv("COINBASE_CONTRACT_SIZE", "0.01"))   # BTC per contract

# Binance Futures
BINANCE_API_KEY           = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET        = os.getenv("BINANCE_API_SECRET", "")
BINANCE_CONTRACT_SIZE     = float(os.getenv("BINANCE_CONTRACT_SIZE", "0.001"))

# Bybit
BYBIT_API_KEY             = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET          = os.getenv("BYBIT_API_SECRET", "")
BYBIT_CONTRACT_SIZE       = float(os.getenv("BYBIT_CONTRACT_SIZE", "0.001"))

# Delta Exchange
DELTA_API_KEY             = os.getenv("DELTA_API_KEY", "")
DELTA_API_SECRET          = os.getenv("DELTA_API_SECRET", "")
DELTA_CONTRACT_SIZE       = float(os.getenv("DELTA_CONTRACT_SIZE", "0.001"))

# CoinDCX
COINDCX_API_KEY           = os.getenv("COINDCX_API_KEY", "")
COINDCX_API_SECRET        = os.getenv("COINDCX_API_SECRET", "")
COINDCX_CONTRACT_SIZE     = float(os.getenv("COINDCX_CONTRACT_SIZE", "0.001"))

# Pepperstone (cTrader Open API)
PEPPERSTONE_CLIENT_ID      = os.getenv("PEPPERSTONE_CLIENT_ID", "")
PEPPERSTONE_CLIENT_SECRET  = os.getenv("PEPPERSTONE_CLIENT_SECRET", "")
PEPPERSTONE_ACCOUNT_ID     = os.getenv("PEPPERSTONE_ACCOUNT_ID", "")
PEPPERSTONE_IS_LIVE        = os.getenv("PEPPERSTONE_IS_LIVE", "true")
PEPPERSTONE_CONTRACT_SIZE  = float(os.getenv("PEPPERSTONE_CONTRACT_SIZE", "0.01"))
PEPPERSTONE_REDIRECT_URI   = os.getenv("PEPPERSTONE_REDIRECT_URI", "")

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


def apply_settings(d: dict) -> None:
    """Override module-level config vars from a Firestore settings dict."""
    import sys
    mod = sys.modules[__name__]
    _str = {
        "anthropic_api_key": "ANTHROPIC_API_KEY", "anthropic_model": "ANTHROPIC_MODEL",
        "telegram_bot_token": "TELEGRAM_BOT_TOKEN", "telegram_chat_id": "TELEGRAM_CHAT_ID",
        "email_smtp_host": "EMAIL_SMTP_HOST", "email_user": "EMAIL_USER",
        "email_pass": "EMAIL_PASS", "email_to": "EMAIL_TO",
        "briefing_time": "BRIEFING_TIME", "scanner_time": "SCANNER_TIME",
        "trading_mode": "TRADING_MODE", "trading_broker": "TRADING_BROKER",
        "coinbase_api_key": "COINBASE_API_KEY", "coinbase_api_secret": "COINBASE_API_SECRET",
        "coinbase_product_id": "COINBASE_PRODUCT_ID",
        "binance_api_key": "BINANCE_API_KEY", "binance_api_secret": "BINANCE_API_SECRET",
        "bybit_api_key": "BYBIT_API_KEY", "bybit_api_secret": "BYBIT_API_SECRET",
        "delta_api_key": "DELTA_API_KEY", "delta_api_secret": "DELTA_API_SECRET",
        "coindcx_api_key": "COINDCX_API_KEY", "coindcx_api_secret": "COINDCX_API_SECRET",
        "pepperstone_client_id": "PEPPERSTONE_CLIENT_ID",
        "pepperstone_client_secret": "PEPPERSTONE_CLIENT_SECRET",
        "pepperstone_account_id": "PEPPERSTONE_ACCOUNT_ID",
        "pepperstone_is_live": "PEPPERSTONE_IS_LIVE",
    }
    _int = {
        "email_smtp_port": "EMAIL_SMTP_PORT",
        "scanner_tf_min": "SCANNER_TF_MIN", "scanner_tf_max": "SCANNER_TF_MAX",
        "scanner_interval_min": "SCANNER_INTERVAL_MIN",
        "trading_tf_min": "TRADING_TF_MIN", "trading_tf_max": "TRADING_TF_MAX",
        "trading_scan_interval_min": "TRADING_SCAN_INTERVAL_MIN",
        "trading_max_concurrent": "TRADING_MAX_CONCURRENT", "trading_qty": "TRADING_QTY",
    }
    _bool = {
        "vishal_enabled": "VISHAL_ENABLED",
        "trading_bias_filter": "TRADING_BIAS_FILTER",
        "trading_cme_close_skip": "TRADING_CME_CLOSE_SKIP",
        "bsg_enabled": "BSG_ENABLED",
        "bsg_trade_enabled": "BSG_TRADE_ENABLED",
    }
    _float = {
        "trading_max_sl": "TRADING_MAX_SL", "trading_min_tp": "TRADING_MIN_TP",
        "trading_daily_pts_target": "TRADING_DAILY_PTS_TARGET",
        "weekly_adj": "WEEKLY_ADJ", "coinbase_contract_size": "COINBASE_CONTRACT_SIZE",
        "binance_contract_size": "BINANCE_CONTRACT_SIZE", "bybit_contract_size": "BYBIT_CONTRACT_SIZE",
        "delta_contract_size": "DELTA_CONTRACT_SIZE", "coindcx_contract_size": "COINDCX_CONTRACT_SIZE",
    }
    _list = {
        "delivery_channels": "DELIVERY_CHANNELS",
        "scanner_patterns": "SCANNER_PATTERNS", "trading_patterns": "TRADING_PATTERNS",
    }
    for key, attr in _str.items():
        v = d.get(key)
        if v is not None and str(v).strip() and "****" not in str(v):
            setattr(mod, attr, str(v))
    for key, attr in _int.items():
        v = d.get(key)
        if v is not None:
            try: setattr(mod, attr, int(v))
            except (ValueError, TypeError) as e:
                print(f"[config] warning: {key}={v!r} not a valid int: {e}")
    for key, attr in _float.items():
        v = d.get(key)
        if v is not None:
            try: setattr(mod, attr, float(v))
            except (ValueError, TypeError) as e:
                print(f"[config] warning: {key}={v!r} not a valid float: {e}")
    for key, attr in _bool.items():
        v = d.get(key)
        if v is not None:
            setattr(mod, attr, (str(v).lower() == "true") if isinstance(v, str) else bool(v))
    for key, attr in _list.items():
        v = d.get(key)
        if isinstance(v, list) and v:
            setattr(mod, attr, v)
        elif isinstance(v, str) and v:
            setattr(mod, attr, [x.strip() for x in v.split(",") if x.strip()])
