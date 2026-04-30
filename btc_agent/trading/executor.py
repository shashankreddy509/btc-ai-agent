"""
Coinbase Advanced Trade REST client.

Docs: https://docs.cdp.coinbase.com/advanced-trade/reference/
Auth: CDP API keys — ES256 JWT Bearer token
"""
from __future__ import annotations

import base64
import json
import re
import time
import uuid
from typing import Any

import urllib.request
import urllib.error

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from btc_agent import config

_BASE = "https://api.coinbase.com"


# ── auth ──────────────────────────────────────────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _normalize_pem(raw: str) -> str:
    """Reconstruct a well-formed PEM from a .env-stored string.

    Handles three storage formats:
    - Literal \\n (dotenv kept backslash-n as-is)
    - Actual newlines (quoted value or scp'd file)
    - n chars (dotenv stripped backslash from \\n, leaving just 'n')
    """
    import base64 as _b64
    raw = raw.strip().strip("\"'")
    if "\\n" in raw:
        raw = raw.replace("\\n", "\n")

    hm = re.search(r"-----BEGIN [^-]+-----", raw)
    fm = re.search(r"-----END [^-]+-----",   raw)
    if not hm or not fm:
        return raw

    header = hm.group()
    footer = fm.group()
    body   = re.sub(r"\s", "", raw[hm.end():fm.start()])

    def _try_decode(b: str) -> bool:
        try:
            _b64.b64decode(b + "=" * (-len(b) % 4))
            return True
        except Exception:
            return False

    if not _try_decode(body) and body.startswith("n"):
        cleaned, i = "", 1
        while i < len(body):
            cleaned += body[i:i+64]
            i += 64
            if i < len(body) and body[i] == "n":
                i += 1
        body = cleaned

    wrapped = "\n".join(body[i:i+64] for i in range(0, len(body), 64))
    return f"{header}\n{wrapped}\n{footer}\n"


def _build_jwt(method: str, path: str, api_key: str | None = None, api_secret: str | None = None) -> str:
    """Build a short-lived ES256 JWT using provided creds (never touches global config)."""
    key_name = api_key or config.COINBASE_API_KEY
    key_pem  = _normalize_pem(api_secret or config.COINBASE_API_SECRET)
    private_key = serialization.load_pem_private_key(key_pem.encode(), password=None)

    now = int(time.time())
    header  = {"alg": "ES256", "kid": key_name}
    payload = {
        "sub": key_name,
        "iss": "cdp",
        "nbf": now,
        "exp": now + 120,
        "uri": f"{method.upper()} api.coinbase.com{path}",
    }

    h = _b64url(json.dumps(header,  separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()

    der_sig = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_sig)
    sig_b64 = _b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))

    return f"{h}.{p}.{sig_b64}"


def _auth_headers(method: str, path: str, api_key: str | None = None, api_secret: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_build_jwt(method, path, api_key, api_secret)}",
        "Content-Type":  "application/json",
    }


def _get(path: str, api_key: str | None = None, api_secret: str | None = None) -> dict[str, Any]:
    headers = _auth_headers("GET", path, api_key, api_secret)
    req = urllib.request.Request(_BASE + path, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Coinbase {path} → HTTP {e.code}: {e.read().decode()}") from e


def _post(path: str, payload: dict[str, Any], api_key: str | None = None, api_secret: str | None = None) -> dict[str, Any]:
    body = json.dumps(payload)
    headers = _auth_headers("POST", path, api_key, api_secret)
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


def get_portfolio_name(api_key: str | None = None, api_secret: str | None = None) -> str:
    """Return the name of the user's default Coinbase portfolio."""
    try:
        data = _get("/api/v3/brokerage/portfolios", api_key, api_secret)
        portfolios = data.get("portfolios", [])
        active = [p for p in portfolios if not p.get("deleted")]
        return active[0]["name"] if active else ""
    except Exception:
        return ""


# ── orders ────────────────────────────────────────────────────────────────────

def place_market_order(
    side: str,
    base_size: str,
    product_id: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
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
    return _post("/api/v3/brokerage/orders", payload, api_key, api_secret)


def place_stop_limit_order(
    side: str,
    base_size: str,
    stop_price: float,
    limit_price: float,
    product_id: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> dict[str, Any]:
    """Place a GTC stop-limit order for stop-loss."""
    pid = product_id or config.COINBASE_PRODUCT_ID
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
    return _post("/api/v3/brokerage/orders", payload, api_key, api_secret)


def cancel_order(order_id: str, api_key: str | None = None, api_secret: str | None = None) -> dict[str, Any]:
    """Cancel a single order. Uses batch_cancel endpoint."""
    return _post("/api/v3/brokerage/orders/batch_cancel", {"order_ids": [order_id]}, api_key, api_secret)


def place_take_profit_order(
    side: str,
    base_size: str,
    stop_price: float,
    limit_price: float,
    product_id: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
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
    return _post("/api/v3/brokerage/orders", payload, api_key, api_secret)
