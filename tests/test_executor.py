"""
Unit tests for btc_agent/trading/executor.py

All network calls are mocked — no real HTTP requests are made.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest

import btc_agent.trading.executor as executor


# ── helpers ───────────────────────────────────────────────────────────────────

_FAKE_KEY    = "test-api-key"
_FAKE_SECRET = "test-api-secret"
_FAKE_PID    = "BTC-USD"


def _make_urlopen_mock(response_body: dict):
    """Return a context-manager mock that yields a fake HTTP response."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(response_body).encode()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__  = MagicMock(return_value=False)
    return cm


# ── _sign ─────────────────────────────────────────────────────────────────────

class TestSign:
    def test_required_headers_present(self):
        with patch.object(executor.config, "COINBASE_API_KEY", _FAKE_KEY), \
             patch.object(executor.config, "COINBASE_API_SECRET", _FAKE_SECRET):
            headers = executor._sign("POST", "/api/v3/brokerage/orders", '{"foo":1}')
        assert headers["CB-ACCESS-KEY"] == _FAKE_KEY
        assert "CB-ACCESS-TIMESTAMP" in headers
        assert "CB-ACCESS-SIGN" in headers
        assert headers["Content-Type"] == "application/json"

    def test_signature_is_valid_hmac_sha256(self):
        body = '{"test": true}'
        with patch.object(executor.config, "COINBASE_API_KEY", _FAKE_KEY), \
             patch.object(executor.config, "COINBASE_API_SECRET", _FAKE_SECRET), \
             patch("btc_agent.trading.executor.time.time", return_value=1234567890):
            headers = executor._sign("POST", "/some/path", body)
        ts = headers["CB-ACCESS-TIMESTAMP"]
        message = ts + "POST" + "/some/path" + body
        expected = hmac.new(
            _FAKE_SECRET.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        assert headers["CB-ACCESS-SIGN"] == expected

    def test_empty_body_allowed(self):
        with patch.object(executor.config, "COINBASE_API_KEY", _FAKE_KEY), \
             patch.object(executor.config, "COINBASE_API_SECRET", _FAKE_SECRET):
            headers = executor._sign("GET", "/api/v3/brokerage/accounts")
        assert "CB-ACCESS-SIGN" in headers


# ── _post ─────────────────────────────────────────────────────────────────────

class TestPost:
    def test_returns_parsed_json(self):
        expected = {"order_id": "abc123", "success": True}
        cm = _make_urlopen_mock(expected)
        with patch.object(executor.config, "COINBASE_API_KEY", _FAKE_KEY), \
             patch.object(executor.config, "COINBASE_API_SECRET", _FAKE_SECRET), \
             patch("btc_agent.trading.executor.urllib.request.urlopen", return_value=cm):
            result = executor._post("/api/v3/brokerage/orders", {"side": "BUY"})
        assert result == expected

    def test_http_error_raises_runtime_error(self):
        import urllib.error
        http_err = urllib.error.HTTPError(
            url="https://api.coinbase.com/api/v3/brokerage/orders",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=MagicMock(read=lambda: b'{"error":"INVALID_ORDER"}'),
        )
        with patch.object(executor.config, "COINBASE_API_KEY", _FAKE_KEY), \
             patch.object(executor.config, "COINBASE_API_SECRET", _FAKE_SECRET), \
             patch("btc_agent.trading.executor.urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(RuntimeError, match="HTTP 400"):
                executor._post("/api/v3/brokerage/orders", {})


# ── place_market_order ────────────────────────────────────────────────────────

class TestPlaceMarketOrder:
    def _run(self, side: str, base_size: str, captured: list):
        def fake_post(path, payload):
            captured.append(payload)
            return {"success": True, "order_id": "mkt-001"}

        with patch.object(executor.config, "COINBASE_API_KEY", _FAKE_KEY), \
             patch.object(executor.config, "COINBASE_API_SECRET", _FAKE_SECRET), \
             patch.object(executor.config, "COINBASE_PRODUCT_ID", _FAKE_PID), \
             patch("btc_agent.trading.executor._post", side_effect=fake_post):
            return executor.place_market_order(side, base_size)

    def test_buy_side(self):
        captured = []
        result = self._run("BUY", "0.001", captured)
        payload = captured[0]
        assert payload["side"] == "BUY"
        assert payload["product_id"] == _FAKE_PID
        assert "market_market_ioc" in payload["order_configuration"]
        assert payload["order_configuration"]["market_market_ioc"]["base_size"] == "0.001"
        assert result["success"] is True

    def test_sell_side(self):
        captured = []
        self._run("SELL", "0.002", captured)
        assert captured[0]["side"] == "SELL"

    def test_unique_client_order_ids(self):
        ids = set()
        for _ in range(5):
            captured = []
            self._run("BUY", "0.001", captured)
            ids.add(captured[0]["client_order_id"])
        assert len(ids) == 5, "client_order_id must be unique per order"

    def test_custom_product_id(self):
        captured = []
        with patch.object(executor.config, "COINBASE_API_KEY", _FAKE_KEY), \
             patch.object(executor.config, "COINBASE_API_SECRET", _FAKE_SECRET), \
             patch("btc_agent.trading.executor._post", side_effect=lambda p, pl: captured.append(pl) or {}):
            executor.place_market_order("BUY", "0.001", product_id="ETH-USD")
        assert captured[0]["product_id"] == "ETH-USD"


# ── place_stop_limit_order ────────────────────────────────────────────────────

class TestPlaceStopLimitOrder:
    def _run(self, side, base_size, stop_price, limit_price, captured):
        with patch.object(executor.config, "COINBASE_API_KEY", _FAKE_KEY), \
             patch.object(executor.config, "COINBASE_API_SECRET", _FAKE_SECRET), \
             patch.object(executor.config, "COINBASE_PRODUCT_ID", _FAKE_PID), \
             patch("btc_agent.trading.executor._post",
                   side_effect=lambda p, pl: captured.append(pl) or {"success": True}):
            return executor.place_stop_limit_order(side, base_size, stop_price, limit_price)

    def test_sell_stop_uses_stop_down(self):
        captured = []
        self._run("SELL", "0.001", 95000.0, 94900.0, captured)
        cfg = captured[0]["order_configuration"]["stop_limit_stop_limit_gtc"]
        assert cfg["stop_direction"] == "STOP_DIRECTION_STOP_DOWN"
        assert cfg["stop_price"]  == "95000.00"
        assert cfg["limit_price"] == "94900.00"

    def test_buy_stop_uses_stop_up(self):
        captured = []
        self._run("BUY", "0.001", 105000.0, 105100.0, captured)
        cfg = captured[0]["order_configuration"]["stop_limit_stop_limit_gtc"]
        assert cfg["stop_direction"] == "STOP_DIRECTION_STOP_UP"

    def test_price_formatted_to_two_decimals(self):
        captured = []
        self._run("SELL", "0.001", 98765.1, 98700.9, captured)
        cfg = captured[0]["order_configuration"]["stop_limit_stop_limit_gtc"]
        assert cfg["stop_price"]  == "98765.10"
        assert cfg["limit_price"] == "98700.90"


# ── place_take_profit_order ───────────────────────────────────────────────────

class TestPlaceTakeProfitOrder:
    def _run(self, side, base_size, stop_price, limit_price, captured):
        with patch.object(executor.config, "COINBASE_API_KEY", _FAKE_KEY), \
             patch.object(executor.config, "COINBASE_API_SECRET", _FAKE_SECRET), \
             patch.object(executor.config, "COINBASE_PRODUCT_ID", _FAKE_PID), \
             patch("btc_agent.trading.executor._post",
                   side_effect=lambda p, pl: captured.append(pl) or {"success": True}):
            return executor.place_take_profit_order(side, base_size, stop_price, limit_price)

    def test_sell_tp_uses_stop_up(self):
        """Long position take-profit: sell when price rises above target."""
        captured = []
        self._run("SELL", "0.001", 110000.0, 110100.0, captured)
        cfg = captured[0]["order_configuration"]["stop_limit_stop_limit_gtc"]
        assert cfg["stop_direction"] == "STOP_DIRECTION_STOP_UP"

    def test_buy_tp_uses_stop_down(self):
        """Short position take-profit: buy when price falls below target."""
        captured = []
        self._run("BUY", "0.001", 90000.0, 89900.0, captured)
        cfg = captured[0]["order_configuration"]["stop_limit_stop_limit_gtc"]
        assert cfg["stop_direction"] == "STOP_DIRECTION_STOP_DOWN"

    def test_product_id_defaults_from_config(self):
        captured = []
        self._run("SELL", "0.001", 100000.0, 100100.0, captured)
        assert captured[0]["product_id"] == _FAKE_PID
