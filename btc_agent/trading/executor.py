"""
Coinbase Advanced Trade REST client.

Docs: https://docs.cdp.coinbase.com/advanced-trade/reference/
Auth: HMAC-SHA256 (api_key + secret)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import urllib.request
import urllib.error

from btc_agent import config

_BASE = "https://api.coinbase.com"


# ── auth ──────────────────────────────────────────────────────────────────────

def _sign(method: str, path: str, body: str = "") -> dict[str, str]:
    ts = str(int(time.time()))
    message = ts + method.upper() + path + body
    sig = hmac.new(
        config.COINBASE_API_SECRET.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "CB-ACCESS-KEY":       config.COINBASE_API_KEY,
        "CB-ACCESS-TIMESTAMP": ts,
        "CB-ACCESS-SIGN":      sig,
        "Content-Type":        "application/json",
    }


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload)
    headers = _sign("POST", path, body)
    req = urllib.request.Request(
        _BASE + path,
        data=body.encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Coinbase {path} → HTTP {e.code}: {e.read().decode()}") from e


# ── orders ────────────────────────────────────────────────────────────────────

def place_market_order(
    side: str,            # "BUY" | "SELL"
    base_size: str,       # BTC quantity as string e.g. "0.001"
    product_id: str | None = None,
) -> dict[str, Any]:
    """Place an immediate market order (IOC)."""
    pid = product_id or config.COINBASE_PRODUCT_ID
    payload = {
        "client_order_id": uuid.uuid4().hex[:16],
        "product_id": pid,
        "side": side,
        "order_configuration": {
            "market_market_ioc": {
                "base_size": base_size,
            }
        },
    }
    return _post("/api/v3/brokerage/orders", payload)


def place_stop_limit_order(
    side: str,            # "BUY" (stop for short) | "SELL" (stop for long)
    base_size: str,
    stop_price: float,
    limit_price: float,
    product_id: str | None = None,
) -> dict[str, Any]:
    """Place a GTC stop-limit order for stop-loss."""
    pid = product_id or config.COINBASE_PRODUCT_ID
    # stop_direction: STOP_DIRECTION_STOP_DOWN for longs (sell when price falls)
    #                 STOP_DIRECTION_STOP_UP   for shorts (buy when price rises)
    stop_dir = "STOP_DIRECTION_STOP_DOWN" if side == "SELL" else "STOP_DIRECTION_STOP_UP"
    payload = {
        "client_order_id": uuid.uuid4().hex[:16],
        "product_id": pid,
        "side": side,
        "order_configuration": {
            "stop_limit_stop_limit_gtc": {
                "base_size":       base_size,
                "limit_price":     f"{limit_price:.2f}",
                "stop_price":      f"{stop_price:.2f}",
                "stop_direction":  stop_dir,
            }
        },
    }
    return _post("/api/v3/brokerage/orders", payload)


def place_take_profit_order(
    side: str,
    base_size: str,
    stop_price: float,
    limit_price: float,
    product_id: str | None = None,
) -> dict[str, Any]:
    """Place a GTC take-profit limit order."""
    pid = product_id or config.COINBASE_PRODUCT_ID
    stop_dir = "STOP_DIRECTION_STOP_UP" if side == "SELL" else "STOP_DIRECTION_STOP_DOWN"
    payload = {
        "client_order_id": uuid.uuid4().hex[:16],
        "product_id": pid,
        "side": side,
        "order_configuration": {
            "stop_limit_stop_limit_gtc": {
                "base_size":      base_size,
                "limit_price":    f"{limit_price:.2f}",
                "stop_price":     f"{stop_price:.2f}",
                "stop_direction": stop_dir,
            }
        },
    }
    return _post("/api/v3/brokerage/orders", payload)
