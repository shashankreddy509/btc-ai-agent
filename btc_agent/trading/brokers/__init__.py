from __future__ import annotations

from btc_agent.trading.brokers.base import BrokerAdapter
from btc_agent.trading.brokers.binance import BinanceAdapter
from btc_agent.trading.brokers.bybit import BybitAdapter
from btc_agent.trading.brokers.coinbase import CoinbaseAdapter
from btc_agent.trading.brokers.coindcx import CoinDCXAdapter
from btc_agent.trading.brokers.delta import DeltaAdapter
from btc_agent.trading.brokers.pepperstone import PepperstoneAdapter

BROKER_NAMES = {
    "coinbase":    "Coinbase",
    "binance":     "Binance Futures",
    "bybit":       "Bybit",
    "delta":       "Delta Exchange",
    "coindcx":     "CoinDCX",
    "pepperstone": "Pepperstone (cTrader)",
}


def get_broker(name: str, creds: dict) -> BrokerAdapter:
    """Instantiate the correct broker adapter from user credentials."""
    api_key    = creds.get("api_key", "")
    api_secret = creds.get("api_secret", "")

    if name == "coinbase":
        return CoinbaseAdapter(
            api_key=api_key,
            api_secret=api_secret,
            product_id=creds.get("product_id", "BTC-PERP-INTX"),
            contract_size_val=float(creds.get("contract_size", 0.01)),
        )
    contract_size = float(creds.get("contract_size", 0.001)) or None
    if name == "binance":
        return BinanceAdapter(api_key=api_key, api_secret=api_secret, contract_size_val=contract_size)
    if name == "bybit":
        return BybitAdapter(api_key=api_key, api_secret=api_secret, contract_size_val=contract_size)
    if name == "delta":
        return DeltaAdapter(api_key=api_key, api_secret=api_secret, contract_size_val=contract_size)
    if name == "coindcx":
        return CoinDCXAdapter(api_key=api_key, api_secret=api_secret, contract_size_val=contract_size)
    if name == "pepperstone":
        return PepperstoneAdapter(
            client_id=creds.get("pepperstone_client_id", api_key),
            client_secret=creds.get("pepperstone_client_secret", api_secret),
            refresh_token=creds.get("pepperstone_refresh_token", ""),
            account_id=int(creds.get("pepperstone_account_id", 0) or 0),
            is_live=str(creds.get("pepperstone_is_live", "true")).lower() != "false",
            contract_size_val=contract_size,
        )
    raise ValueError(f"Unknown broker: {name!r}. Valid: {list(BROKER_NAMES)}")
