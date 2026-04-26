from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request

from btc_agent.trading.brokers.base import BrokerAdapter

_BASE = "https://api.delta.exchange"
_SYMBOL = "BTCUSD"
_CONTRACT_SIZE = 0.001  # approximate — Delta uses USD-settled contracts


class DeltaAdapter(BrokerAdapter):
    """Delta Exchange Perpetual Futures via REST API v2."""

    def __init__(self, api_key: str, api_secret: str, contract_size_val: float | None = None):
        self._api_key = api_key
        self._api_secret = api_secret
        self._product_id: int | None = None
        self._contract_size = contract_size_val if contract_size_val else _CONTRACT_SIZE

    def _sign(self, method: str, path: str, timestamp: str, body: str) -> str:
        message = method + timestamp + path + body
        return hmac.new(self._api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        ts = str(int(time.time()))
        body = json.dumps(payload) if payload else ""
        sig = self._sign(method, path, ts, body)
        headers = {
            "api-key":      self._api_key,
            "timestamp":    ts,
            "signature":    sig,
            "Content-Type": "application/json",
        }
        data = body.encode() if body else None
        req = urllib.request.Request(_BASE + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Delta {method} {path} → HTTP {e.code}: {e.read().decode()}") from e

    def _resolve_product_id(self) -> int:
        if self._product_id:
            return self._product_id
        resp = self._request("GET", f"/v2/products?contract_type=perpetual_futures&symbol={_SYMBOL}")
        for p in resp.get("result", []):
            if p.get("symbol") == _SYMBOL:
                self._product_id = p["id"]
                return self._product_id
        raise RuntimeError(f"Delta product ID not found for {_SYMBOL}")

    def place_market_order(self, side: str, qty: str) -> dict:
        resp = self._request("POST", "/v2/orders", {
            "product_id": self._resolve_product_id(),
            "side": side.lower(),
            "order_type": "market_order",
            "size": int(qty),
        })
        return {"order_id": str(resp.get("result", {}).get("id", ""))}

    def place_stop_limit_order(self, side: str, qty: str, stop_price: float, limit_price: float) -> dict:
        resp = self._request("POST", "/v2/orders", {
            "product_id": self._resolve_product_id(),
            "side": side.lower(),
            "order_type": "stop_loss_order",
            "size": int(qty),
            "stop_price": f"{stop_price:.2f}",
            "limit_price": f"{limit_price:.2f}",
        })
        return {"order_id": str(resp.get("result", {}).get("id", ""))}

    def cancel_order(self, order_id: str) -> dict:
        return self._request("DELETE", f"/v2/orders/{order_id}", {
            "product_id": self._resolve_product_id(),
        })

    @property
    def contract_size(self) -> float:
        return self._contract_size
