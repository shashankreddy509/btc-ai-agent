from __future__ import annotations
from abc import ABC, abstractmethod


class BrokerAdapter(ABC):
    """Minimal interface every broker must implement."""

    @abstractmethod
    def place_market_order(self, side: str, qty: str) -> dict:
        """Place an immediate market order.

        side: "BUY" or "SELL"
        qty:  quantity string (meaning varies by broker)
        Returns dict with at least {"order_id": str}
        """

    @abstractmethod
    def place_stop_limit_order(
        self,
        side: str,
        qty: str,
        stop_price: float,
        limit_price: float,
    ) -> dict:
        """Place a GTC stop-limit order for stop-loss protection."""

    @abstractmethod
    def place_take_profit_order(
        self,
        side: str,
        qty: str,
        stop_price: float,
        limit_price: float,
    ) -> dict:
        """Place a GTC take-profit order that closes the position when TP is reached."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> dict:
        """Cancel an open order by its broker-assigned order_id."""

    @property
    @abstractmethod
    def contract_size(self) -> float:
        """BTC equivalent per unit/contract — used for PnL calculation."""

    def get_display_name(self) -> str:
        """Return a human-readable account name from the broker API."""
        return ""
