from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request

from btc_agent.trading.brokers.base import BrokerAdapter

_BASE = "https://api.bybit.com"
_SYMBOL = "BTCUSDT"
_RECV_WINDOW = "5000"
_CONTRACT_SIZE = 0.001  # 1 contract = 0.001 BTC on Bybit Linear Perpetual


class BybitAdapter(BrokerAdapter):
    """Bybit V5 Linear Perpetual Futures via REST API."""

    def __init__(self, api_key: str, api_secret: str, contract_size_val: float | None = None):
        self._api_key = api_key
        self._api_secret = api_secret
        self._contract_size = contract_size_val if contract_size_val else _CONTRACT_SIZE

    def _sign(self, timestamp: str, body: str) -> str:
        raw = f"{timestamp}{self._api_key}{_RECV_WINDOW}{body}"
        return hmac.new(self._api_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

    def _post(self, path: str, payload: dict) -> dict:
        ts = str(int(time.time() * 1000))
        body = json.dumps(payload)
        sig = self._sign(ts, body)
        headers = {
            "X-BAPI-API-KEY":     self._api_key,
            "X-BAPI-TIMESTAMP":   ts,
            "X-BAPI-SIGN":        sig,
            "X-BAPI-RECV-WINDOW": _RECV_WINDOW,
            "Content-Type":       "application/json",
        }
        req = urllib.request.Request(_BASE + path, data=body.encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Bybit {path} → HTTP {e.code}: {e.read().decode()}") from e

    def place_market_order(self, side: str, qty: str) -> dict:
        bybit_side = "Buy" if side == "BUY" else "Sell"
        btc_qty = f"{int(qty) * self._contract_size:.3f}"
        resp = self._post("/v5/order/create", {
            "category": "linear", "symbol": _SYMBOL,
            "side": bybit_side, "orderType": "Market", "qty": btc_qty,
        })
        return {"order_id": resp.get("result", {}).get("orderId", "")}

    def place_stop_limit_order(self, side: str, qty: str, stop_price: float, limit_price: float) -> dict:
        bybit_side = "Buy" if side == "BUY" else "Sell"
        btc_qty = f"{int(qty) * self._contract_size:.3f}"
        resp = self._post("/v5/order/create", {
            "category": "linear", "symbol": _SYMBOL,
            "side": bybit_side, "orderType": "Limit",
            "qty": btc_qty, "price": f"{limit_price:.2f}",
            "triggerPrice": f"{stop_price:.2f}",
            "triggerBy": "LastPrice",
            "triggerDirection": 1 if side == "BUY" else 2,
            "timeInForce": "GTC",
        })
        return {"order_id": resp.get("result", {}).get("orderId", "")}

    def place_take_profit_order(self, side: str, qty: str, stop_price: float, limit_price: float) -> dict:
        bybit_side = "Buy" if side == "BUY" else "Sell"
        btc_qty = f"{int(qty) * self._contract_size:.3f}"
        # TP triggers when price moves INTO the target (opposite direction from SL):
        # SELL TP (long): price rises to TP → triggerDirection=1
        # BUY  TP (short): price falls to TP → triggerDirection=2
        trigger_dir = 1 if bybit_side == "Sell" else 2
        resp = self._post("/v5/order/create", {
            "category": "linear", "symbol": _SYMBOL,
            "side": bybit_side, "orderType": "Limit",
            "qty": btc_qty, "price": f"{limit_price:.2f}",
            "triggerPrice": f"{stop_price:.2f}",
            "triggerBy": "LastPrice", "triggerDirection": trigger_dir,
            "reduceOnly": True, "timeInForce": "GTC",
        })
        return {"order_id": resp.get("result", {}).get("orderId", "")}

    def cancel_order(self, order_id: str) -> dict:
        return self._post("/v5/order/cancel", {
            "category": "linear", "symbol": _SYMBOL, "orderId": order_id,
        })

    @property
    def contract_size(self) -> float:
        return self._contract_size
