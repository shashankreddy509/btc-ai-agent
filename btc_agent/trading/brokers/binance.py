from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from btc_agent.trading.brokers.base import BrokerAdapter

_BASE = "https://fapi.binance.com"
_SYMBOL = "BTCUSDT"
_CONTRACT_SIZE = 0.001  # 1 contract = 0.001 BTC on Binance USDT-M Futures


class BinanceAdapter(BrokerAdapter):
    """Binance USDT-M Perpetual Futures via REST API."""

    def __init__(self, api_key: str, api_secret: str, contract_size_val: float | None = None):
        self._api_key = api_key
        self._api_secret = api_secret
        self._contract_size = contract_size_val if contract_size_val else _CONTRACT_SIZE

    def _sign(self, params: dict) -> str:
        query = urllib.parse.urlencode(params)
        return hmac.new(
            self._api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self._api_key, "Content-Type": "application/x-www-form-urlencoded"}

    def _post(self, path: str, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = self._sign(params)
        body = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(_BASE + path, data=body, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Binance {path} → HTTP {e.code}: {e.read().decode()}") from e

    def _delete(self, path: str, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = self._sign(params)
        query = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{_BASE}{path}?{query}", headers=self._headers(), method="DELETE"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Binance DELETE {path} → HTTP {e.code}: {e.read().decode()}") from e

    def place_market_order(self, side: str, qty: str) -> dict:
        btc_qty = f"{int(qty) * self._contract_size:.3f}"
        resp = self._post("/fapi/v1/order", {
            "symbol": _SYMBOL, "side": side,
            "type": "MARKET", "quantity": btc_qty,
        })
        return {"order_id": str(resp.get("orderId", ""))}

    def place_stop_limit_order(self, side: str, qty: str, stop_price: float, limit_price: float) -> dict:
        btc_qty = f"{int(qty) * self._contract_size:.3f}"
        resp = self._post("/fapi/v1/order", {
            "symbol": _SYMBOL, "side": side,
            "type": "STOP", "quantity": btc_qty,
            "stopPrice": f"{stop_price:.2f}",
            "price": f"{limit_price:.2f}",
            "timeInForce": "GTC",
        })
        return {"order_id": str(resp.get("orderId", ""))}

    def cancel_order(self, order_id: str) -> dict:
        return self._delete("/fapi/v1/order", {"symbol": _SYMBOL, "orderId": order_id})

    @property
    def contract_size(self) -> float:
        return self._contract_size
