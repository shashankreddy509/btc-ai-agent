from __future__ import annotations
from btc_agent.trading.brokers.base import BrokerAdapter


class CoinbaseAdapter(BrokerAdapter):
    """Wraps executor.py — passes credentials per-call, never mutates global config."""

    def __init__(self, api_key: str, api_secret: str, product_id: str, contract_size_val: float):
        self._api_key       = api_key
        self._api_secret    = api_secret
        self._product_id    = product_id
        self._contract_size = contract_size_val

    def place_market_order(self, side: str, qty: str) -> dict:
        from btc_agent.trading.executor import place_market_order
        resp = place_market_order(side, qty,
                                  product_id=self._product_id,
                                  api_key=self._api_key,
                                  api_secret=self._api_secret)
        order_id = resp.get("order_id") or resp.get("success_response", {}).get("order_id", "")
        return {"order_id": order_id}

    def place_stop_limit_order(self, side: str, qty: str, stop_price: float, limit_price: float) -> dict:
        from btc_agent.trading.executor import place_stop_limit_order
        resp = place_stop_limit_order(side, qty, stop_price, limit_price,
                                      product_id=self._product_id,
                                      api_key=self._api_key,
                                      api_secret=self._api_secret)
        order_id = resp.get("order_id") or resp.get("success_response", {}).get("order_id", "")
        return {"order_id": order_id}

    def cancel_order(self, order_id: str) -> dict:
        from btc_agent.trading.executor import cancel_order
        return cancel_order(order_id, api_key=self._api_key, api_secret=self._api_secret)

    def get_display_name(self) -> str:
        from btc_agent.trading.executor import get_portfolio_name
        return get_portfolio_name(api_key=self._api_key, api_secret=self._api_secret)

    @property
    def contract_size(self) -> float:
        return self._contract_size
