from __future__ import annotations

import json
import socket
import ssl
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from btc_agent.trading.brokers.base import BrokerAdapter

_TOKEN_URL = "https://id.ctrader.com/connect/token"


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> tuple[str, float]:
    """Exchange refresh_token for a new access_token. Returns (access_token, expires_at)."""
    data = urllib.parse.urlencode({
        "grant_type":    "refresh_token",
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }).encode()
    req = urllib.request.Request(
        _TOKEN_URL, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"cTrader token refresh failed HTTP {e.code}: {e.read().decode()}") from e
    access_token = result.get("access_token", "")
    expires_in   = int(result.get("expires_in", 3600))
    if not access_token:
        raise RuntimeError(f"cTrader token refresh returned no access_token: {result}")
    return access_token, time.time() + expires_in

# ── cTrader Open API endpoint ─────────────────────────────────────────────────
_LIVE_HOST = "live.ctraderapi.com"
_DEMO_HOST = "demo.ctraderapi.com"
_PORT = 5036  # TLS

# ── ProtoOAPayloadType constants (from cTrader Open API spec) ─────────────────
_APP_AUTH_REQ   = 2100
_APP_AUTH_RES   = 2101
_ACCT_AUTH_REQ  = 2102
_ACCT_AUTH_RES  = 2103
_NEW_ORDER_REQ  = 2106
_EXEC_EVENT     = 2107
_CANCEL_ORDER_REQ = 2108
_AMEND_SLTP_REQ = 2109
_SYMBOLS_REQ    = 2114

# ── ProtoOAOrderType ──────────────────────────────────────────────────────────
_ORDER_MARKET = 1
_ORDER_STOP   = 3

# ── ProtoOATradeSide ──────────────────────────────────────────────────────────
_SIDE_BUY  = 1
_SIDE_SELL = 2

# Default contract size: 1 lot = 1 BTC on Pepperstone cTrader (verify in account)
_DEFAULT_CONTRACT_SIZE = 0.01  # 0.01 BTC per unit/contract

_BTCUSD_SYMBOL = "BTCUSD"  # verify exact name in your Pepperstone account


# ── Minimal Protobuf encoder ──────────────────────────────────────────────────

def _varint_enc(n: int) -> bytes:
    out = []
    while n > 0x7F:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n & 0x7F)
    return bytes(out)


def _sint64_enc(n: int) -> bytes:
    """Zigzag-encode signed int64 → varint bytes."""
    return _varint_enc((n << 1) ^ (n >> 63))


def _fld_varint(fnum: int, val: int) -> bytes:
    return _varint_enc((fnum << 3) | 0) + _varint_enc(val)


def _fld_sint64(fnum: int, val: int) -> bytes:
    return _varint_enc((fnum << 3) | 0) + _sint64_enc(val)


def _fld_bytes(fnum: int, data: bytes) -> bytes:
    return _varint_enc((fnum << 3) | 2) + _varint_enc(len(data)) + data


def _fld_str(fnum: int, s: str) -> bytes:
    return _fld_bytes(fnum, s.encode())


def _fld_double(fnum: int, val: float) -> bytes:
    return _varint_enc((fnum << 3) | 1) + struct.pack("<d", val)


def _proto_wrap(payload_type: int, payload: bytes) -> bytes:
    """Wrap in ProtoMessage envelope (field 1=payloadType, field 3=payload)."""
    return _fld_varint(1, payload_type) + _fld_bytes(3, payload)


# ── Minimal Protobuf decoder ──────────────────────────────────────────────────

def _varint_dec(data: bytes, pos: int) -> tuple[int, int]:
    result, shift = 0, 0
    while pos < len(data):
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _sint64_dec(n: int) -> int:
    """Zigzag decode."""
    return (n >> 1) ^ -(n & 1)


def _parse_fields(data: bytes) -> dict[int, list[bytes]]:
    """Parse protobuf wire format → {field_num: [raw_bytes, ...]}."""
    fields: dict[int, list[bytes]] = {}
    pos = 0
    while pos < len(data):
        tag, pos = _varint_dec(data, pos)
        fnum = tag >> 3
        wtype = tag & 0x7
        if wtype == 0:
            val, pos = _varint_dec(data, pos)
            fields.setdefault(fnum, []).append(struct.pack("<Q", val))
        elif wtype == 1:
            fields.setdefault(fnum, []).append(data[pos:pos + 8]); pos += 8
        elif wtype == 2:
            length, pos = _varint_dec(data, pos)
            fields.setdefault(fnum, []).append(data[pos:pos + length]); pos += length
        elif wtype == 5:
            fields.setdefault(fnum, []).append(data[pos:pos + 4]); pos += 4
        else:
            break
    return fields


def _read_varint_field(fields: dict, fnum: int) -> int | None:
    raw = fields.get(fnum)
    if not raw:
        return None
    val = struct.unpack("<Q", raw[0])[0]
    return val


def _read_sint64_field(fields: dict, fnum: int) -> int | None:
    val = _read_varint_field(fields, fnum)
    return None if val is None else _sint64_dec(val)


def _read_bytes_field(fields: dict, fnum: int) -> bytes | None:
    raw = fields.get(fnum)
    return raw[0] if raw else None


# ── Message builders ──────────────────────────────────────────────────────────

def _app_auth_msg(client_id: str, client_secret: str) -> bytes:
    return _proto_wrap(_APP_AUTH_REQ, _fld_str(1, client_id) + _fld_str(2, client_secret))


def _acct_auth_msg(account_id: int, access_token: str) -> bytes:
    return _proto_wrap(_ACCT_AUTH_REQ, _fld_sint64(1, account_id) + _fld_str(2, access_token))


def _symbols_req_msg(account_id: int) -> bytes:
    return _proto_wrap(_SYMBOLS_REQ, _fld_sint64(1, account_id))


def _new_order_msg(account_id: int, symbol_id: int, order_type: int,
                   trade_side: int, volume: int) -> bytes:
    payload = (
        _fld_sint64(1, account_id) +
        _fld_sint64(2, symbol_id) +
        _fld_varint(3, order_type) +
        _fld_varint(4, trade_side) +
        _fld_sint64(5, volume)
    )
    return _proto_wrap(_NEW_ORDER_REQ, payload)


def _cancel_order_msg(account_id: int, order_id: int) -> bytes:
    return _proto_wrap(_CANCEL_ORDER_REQ,
                       _fld_sint64(1, account_id) + _fld_sint64(2, order_id))


def _amend_sltp_msg(account_id: int, position_id: int,
                    stop_loss: float | None = None,
                    take_profit: float | None = None) -> bytes:
    payload = _fld_sint64(1, account_id) + _fld_sint64(2, position_id)
    if take_profit is not None:
        payload += _fld_double(3, take_profit)
    if stop_loss is not None:
        payload += _fld_double(4, stop_loss)
    return _proto_wrap(_AMEND_SLTP_REQ, payload)


# ── TLS socket I/O ────────────────────────────────────────────────────────────

def _connect(host: str) -> ssl.SSLSocket:
    ctx = ssl.create_default_context()
    raw = socket.create_connection((host, _PORT), timeout=15)
    return ctx.wrap_socket(raw, server_hostname=host)


def _send_msg(sock: ssl.SSLSocket, data: bytes) -> None:
    sock.sendall(struct.pack(">I", len(data)) + data)


def _recv_msg(sock: ssl.SSLSocket) -> bytes:
    raw_len = b""
    while len(raw_len) < 4:
        chunk = sock.recv(4 - len(raw_len))
        if not chunk:
            raise ConnectionError("cTrader connection closed")
        raw_len += chunk
    size = struct.unpack(">I", raw_len)[0]
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("cTrader connection closed mid-message")
        data += chunk
    return data


def _recv_until(sock: ssl.SSLSocket, expected_ptype: int, timeout: float = 15.0) -> bytes:
    """Read messages until one with expected payloadType arrives."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sock.settimeout(max(1.0, deadline - time.monotonic()))
        msg = _recv_msg(sock)
        fields = _parse_fields(msg)
        ptype = _read_varint_field(fields, 1)
        payload = _read_bytes_field(fields, 3) or b""
        if ptype == expected_ptype:
            return payload
        # Surface server errors
        if ptype == 50:  # PROTO_MESSAGE_ERROR
            raise RuntimeError(f"cTrader server error: {msg!r}")
    raise TimeoutError(f"Timed out waiting for cTrader response type {expected_ptype}")


# ── PepperstoneAdapter ────────────────────────────────────────────────────────

class PepperstoneAdapter(BrokerAdapter):
    """
    Pepperstone via cTrader Open API (TLS TCP + Protobuf).

    Credentials required in settings:
      pepperstone_client_id     — cTrader Open API application Client ID
      pepperstone_client_secret — cTrader Open API application Client Secret
      pepperstone_refresh_token — OAuth2 refresh token (obtained via Connect button)
      pepperstone_account_id    — Numeric cTrader trader account ID
      pepperstone_is_live       — "true" for live, "false" for demo (default live)
    """

    def __init__(self, client_id: str, client_secret: str, refresh_token: str,
                 account_id: int, is_live: bool = True,
                 contract_size_val: float | None = None):
        self._client_id      = client_id
        self._client_secret  = client_secret
        self._refresh_token  = refresh_token
        self._account_id     = int(account_id)
        self._host           = _LIVE_HOST if is_live else _DEMO_HOST
        self._contract_size  = contract_size_val or _DEFAULT_CONTRACT_SIZE
        self._symbol_id: int | None = None
        self._last_position_id: int | None = None
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._token_lock = threading.Lock()

    def _ensure_token(self) -> str:
        """Return a valid access_token, refreshing silently if expired."""
        with self._token_lock:
            if self._access_token and time.time() < self._token_expires_at - 60:
                return self._access_token
            if not self._refresh_token:
                raise RuntimeError("Pepperstone not connected — use the Connect button in Settings")
            self._access_token, self._token_expires_at = refresh_access_token(
                self._client_id, self._client_secret, self._refresh_token,
            )
            return self._access_token

    def _open_session(self) -> ssl.SSLSocket:
        access_token = self._ensure_token()
        sock = _connect(self._host)
        _send_msg(sock, _app_auth_msg(self._client_id, self._client_secret))
        _recv_until(sock, _APP_AUTH_RES)
        _send_msg(sock, _acct_auth_msg(self._account_id, access_token))
        _recv_until(sock, _ACCT_AUTH_RES)
        return sock

    def _resolve_symbol_id(self) -> int:
        if self._symbol_id:
            return self._symbol_id
        sock = self._open_session()
        try:
            _send_msg(sock, _symbols_req_msg(self._account_id))
            # response payload type for symbols list is 2115
            payload = _recv_until(sock, 2115)
            fields = _parse_fields(payload)
            # field 2 = repeated ProtoOALightSymbol; each has symbolId=1, symbolName=2
            symbols_raw = fields.get(2, [])
            for sym_bytes in symbols_raw:
                sf = _parse_fields(sym_bytes)
                name_raw = _read_bytes_field(sf, 2)
                name = name_raw.decode() if name_raw else ""
                if "BTC" in name.upper() and "USD" in name.upper():
                    sid = _read_sint64_field(sf, 1)
                    if sid:
                        self._symbol_id = sid
                        return sid
            raise RuntimeError(f"BTC/USD symbol not found on account {self._account_id}; "
                               f"check _BTCUSD_SYMBOL constant matches your Pepperstone account")
        finally:
            sock.close()

    def _parse_position_id(self, exec_payload: bytes) -> int:
        """Extract positionId from ProtoOAExecutionEvent payload."""
        fields = _parse_fields(exec_payload)
        # field 4 = ProtoOAPosition, field 1 of that = positionId (sint64)
        pos_bytes = _read_bytes_field(fields, 4)
        if pos_bytes:
            pf = _parse_fields(pos_bytes)
            pid = _read_sint64_field(pf, 1)
            if pid:
                return pid
        # fallback: field 3 = ProtoOAOrder, field 12 = positionId
        order_bytes = _read_bytes_field(fields, 3)
        if order_bytes:
            of = _parse_fields(order_bytes)
            pid = _read_sint64_field(of, 12)
            if pid:
                return pid
        raise RuntimeError("Could not extract positionId from cTrader execution event")

    @property
    def contract_size(self) -> float:
        return self._contract_size

    def place_market_order(self, side: str, qty: str) -> dict:
        volume = max(1, round(int(qty) * self._contract_size * 100))
        trade_side = _SIDE_BUY if side == "BUY" else _SIDE_SELL
        sock = self._open_session()
        try:
            _send_msg(sock, _new_order_msg(
                self._account_id, self._resolve_symbol_id(),
                _ORDER_MARKET, trade_side, volume,
            ))
            exec_payload = _recv_until(sock, _EXEC_EVENT, timeout=20)
        finally:
            sock.close()
        position_id = self._parse_position_id(exec_payload)
        self._last_position_id = position_id
        return {"order_id": str(position_id)}

    def place_stop_limit_order(self, side: str, qty: str,
                               stop_price: float, limit_price: float) -> dict:
        if not self._last_position_id:
            raise RuntimeError("No open position to attach SL to")
        sock = self._open_session()
        try:
            _send_msg(sock, _amend_sltp_msg(
                self._account_id, self._last_position_id, stop_loss=stop_price,
            ))
            _recv_until(sock, _AMEND_SLTP_REQ + 1)  # 2110 = AMEND_SLTP_RES
        finally:
            sock.close()
        return {"order_id": f"sl_{self._last_position_id}"}

    def place_take_profit_order(self, side: str, qty: str,
                                stop_price: float, limit_price: float) -> dict:
        if not self._last_position_id:
            raise RuntimeError("No open position to attach TP to")
        sock = self._open_session()
        try:
            _send_msg(sock, _amend_sltp_msg(
                self._account_id, self._last_position_id, take_profit=stop_price,
            ))
            _recv_until(sock, _AMEND_SLTP_REQ + 1)
        finally:
            sock.close()
        return {"order_id": f"tp_{self._last_position_id}"}

    def cancel_order(self, order_id: str) -> dict:
        sock = self._open_session()
        try:
            if order_id.startswith("sl_"):
                pos_id = int(order_id[3:])
                # Remove SL by setting stopLoss=0
                _send_msg(sock, _amend_sltp_msg(self._account_id, pos_id, stop_loss=0.0))
                _recv_until(sock, _AMEND_SLTP_REQ + 1)
            elif order_id.startswith("tp_"):
                pos_id = int(order_id[3:])
                # Remove TP by setting takeProfit=0
                _send_msg(sock, _amend_sltp_msg(self._account_id, pos_id, take_profit=0.0))
                _recv_until(sock, _AMEND_SLTP_REQ + 1)
            else:
                # Raw order cancellation (e.g. pending order)
                _send_msg(sock, _cancel_order_msg(self._account_id, int(order_id)))
                _recv_until(sock, _EXEC_EVENT)
        finally:
            sock.close()
        return {"order_id": order_id}

    def get_display_name(self) -> str:
        return f"Pepperstone ({self._account_id})"
