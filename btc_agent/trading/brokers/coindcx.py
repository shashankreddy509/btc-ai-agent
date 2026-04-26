from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request

from btc_agent.trading.brokers.base import BrokerAdapter

_BASE = "https://api.coindcx.com"
_MARKET = "BTCUSDT"
_CONTRACT_SIZE = 0.001  # 1 contract ≈ 0.001 BTC on CoinDCX Futures


class CoinDCXAdapter(BrokerAdapter):
    """CoinDCX Futures via REST API."""

    def __init__(self, api_key: str, api_secret: str):
        self._api_key = api_key
        self._api_secret = api_secret

    def _sign(self, body: str) -> str:
        return hmac.new(self._api_secret.encode(), body.encode(), hashlib.sha256).hexdigest()

    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload, separators=(",", ":"))
        sig = self._sign(body)
        headers = {
            "X-AUTH-APIKEY":    self._api_key,
            "X-AUTH-SIGNATURE": sig,
            "Content-Type":     "application/json",
        }
        req = urllib.request.Request(_BASE + path, data=body.encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"CoinDCX {path} → HTTP {e.code}: {e.read().decode()}") from e

    def place_market_order(self, side: str, qty: str) -> dict:
        resp = self._post("/exchange/v1/orders/create", {
            "side": side.lower(),
            "order_type": "market_order",
            "market": _MARKET,
            "total_quantity": float(qty),
            "timestamp": int(time.time() * 1000),
        })
        return {"order_id": str(resp.get("id", ""))}

    def place_stop_limit_order(self, side: str, qty: str, stop_price: float, limit_price: float) -> dict:
        resp = self._post("/exchange/v1/orders/create", {
            "side": side.lower(),
            "order_type": "stop_limit_order",
            "market": _MARKET,
            "total_quantity": float(qty),
            "price_per_unit": limit_price,
            "stop_price": stop_price,
            "timestamp": int(time.time() * 1000),
        })
        return {"order_id": str(resp.get("id", ""))}

    def cancel_order(self, order_id: str) -> dict:
        return self._post("/exchange/v1/orders/cancel", {
            "id": order_id,
            "timestamp": int(time.time() * 1000),
        })

    @property
    def contract_size(self) -> float:
        return _CONTRACT_SIZE
