from __future__ import annotations
from btc_agent.trading.brokers.base import BrokerAdapter


class CoinbaseAdapter(BrokerAdapter):
    """Wraps existing executor.py — no logic duplication."""

    def __init__(self, api_key: str, api_secret: str, product_id: str, contract_size_val: float):
        self._api_key = api_key
        self._api_secret = api_secret
        self._product_id = product_id
        self._contract_size = contract_size_val

    def _apply_creds(self) -> None:
        from btc_agent import config
        if self._api_key:
            config.COINBASE_API_KEY = self._api_key
        if self._api_secret:
            config.COINBASE_API_SECRET = self._api_secret
        if self._product_id:
            config.COINBASE_PRODUCT_ID = self._product_id

    def place_market_order(self, side: str, qty: str) -> dict:
        self._apply_creds()
        from btc_agent.trading.executor import place_market_order
        resp = place_market_order(side, qty)
        order_id = resp.get("order_id") or resp.get("success_response", {}).get("order_id", "")
        return {"order_id": order_id}

    def place_stop_limit_order(self, side: str, qty: str, stop_price: float, limit_price: float) -> dict:
        self._apply_creds()
        from btc_agent.trading.executor import place_stop_limit_order
        resp = place_stop_limit_order(side, qty, stop_price, limit_price)
        order_id = resp.get("order_id") or resp.get("success_response", {}).get("order_id", "")
        return {"order_id": order_id}

    def cancel_order(self, order_id: str) -> dict:
        self._apply_creds()
        from btc_agent.trading.executor import cancel_order
        return cancel_order(order_id)

    @property
    def contract_size(self) -> float:
        return self._contract_size
