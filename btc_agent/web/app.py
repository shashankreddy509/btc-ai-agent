import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import FastAPI, Body, Depends, APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from btc_agent import storage
from btc_agent.web.auth import verify_token

BASE = Path(__file__).parent

app = FastAPI(title="BTC AI Agent Dashboard")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

# Public API — no auth required (briefing + scanner)
pub = APIRouter(prefix="/api")

# Private API — Firebase token required (live trading only)
priv = APIRouter(prefix="/api/trading", dependencies=[Depends(verify_token)])

# Private settings API
priv_cfg = APIRouter(prefix="/api/settings", dependencies=[Depends(verify_token)])

# Background task state
_scan_running    = False
_brief_running   = False
_scan_lock  = threading.Lock()
_brief_lock = threading.Lock()

# Pepperstone OAuth2 state store — maps state token → {uid, expires}
_pepperstone_states: dict[str, dict] = {}

# Feature flag cache — re-reads Firestore at most once every 30 s
_flag_cache: dict = {}
_flag_cache_ts: float = 0.0
_FLAG_TTL = 30.0


def _get_feature_flags() -> dict:
    global _flag_cache, _flag_cache_ts
    if time.time() - _flag_cache_ts < _FLAG_TTL:
        return _flag_cache
    try:
        from btc_agent.trading.firestore_store import load_app_settings
        data = load_app_settings() or {}
        _flag_cache = {
            "vishal_enabled":      bool(data.get("vishal_enabled", False)),
            "retracement_enabled": bool(data.get("retracement_enabled", False)),
        }
    except Exception:
        pass
    _flag_cache_ts = time.time()
    return _flag_cache


def _mask(s: str) -> str:
    s = str(s)
    return s[:4] + "****" + s[-4:] if len(s) > 8 else "****"


def _mask_dict(d: dict, fields: list[str]) -> dict:
    out = dict(d)
    for f in fields:
        if out.get(f):
            out[f] = _mask(out[f])
    return out


def _is_valid_qty(qty) -> bool:
    """qty must be a positive integer that is a multiple of 2."""
    try:
        n = int(qty)
    except (TypeError, ValueError):
        return False
    return n == qty and n > 0 and n % 2 == 0


async def _require_admin(token: dict = Depends(verify_token)) -> dict:
    from btc_agent import config
    owner = config.FIREBASE_OWNER_UID
    if owner:
        if token.get("uid") != owner:
            raise HTTPException(status_code=403, detail="Admin only")
    else:
        if token.get("email") != config.FIREBASE_ADMIN_EMAIL:
            raise HTTPException(status_code=403, detail="Admin only")
    return token


# ── Startup: load Firestore settings into config ──────────────────────────────

@app.on_event("startup")
async def _load_firestore_settings():
    try:
        from btc_agent import config
        from btc_agent.trading.firestore_store import load_app_settings, load_user_prefs
        app_data = load_app_settings()
        if app_data:
            config.apply_settings(app_data)
        if config.FIREBASE_OWNER_UID:
            user_data = load_user_prefs(config.FIREBASE_OWNER_UID)
            if user_data:
                config.apply_settings(user_data)
                if user_data.get("scanner_running"):
                    _auto_restart_scanner(config.FIREBASE_OWNER_UID, user_data)
    except Exception as e:
        print(f"[startup] Firestore settings load skipped: {e}")


def _auto_restart_scanner(uid: str, user_data: dict) -> None:
    from btc_agent.trading.scanner import run_trading_scanner
    setting_keys = {"mode", "tf_min", "tf_max", "scan_interval_min", "qty",
                    "max_sl", "min_tp", "max_concurrent", "patterns", "broker", "broker_nickname",
                    "lookback_candles", "entry_mode",
                    "coinbase_api_key", "coinbase_api_secret",
                    "binance_api_key", "binance_api_secret",
                    "bybit_api_key", "bybit_api_secret",
                    "delta_api_key", "delta_api_secret",
                    "coindcx_api_key", "coindcx_api_secret",
                    "pepperstone_client_id", "pepperstone_client_secret",
                    "pepperstone_refresh_token", "pepperstone_account_id",
                    "pepperstone_is_live"}
    user_settings = {k: v for k, v in user_data.items() if k in setting_keys}
    user_email = ""
    try:
        from firebase_admin import auth as fb_auth
        user_email = fb_auth.get_user(uid).email or ""
    except Exception:
        pass
    threading.Thread(
        target=run_trading_scanner,
        args=(uid,),
        kwargs={"user_settings": user_settings, "email": user_email},
        daemon=True,
        name=f"trading-{uid[:8]}-autostart",
    ).start()
    print(f"[startup] Auto-restarting trading scanner for uid={uid[:8]}…")


# ── Public pages ──────────────────────────────────────────────────────────────

def _firebase_web_config() -> dict:
    from btc_agent import config
    return {
        "fb_api_key":            config.FIREBASE_WEB_API_KEY,
        "fb_auth_domain":        config.FIREBASE_AUTH_DOMAIN,
        "fb_project_id":         config.FIREBASE_PROJECT_ID,
        "fb_storage_bucket":     config.FIREBASE_STORAGE_BUCKET,
        "fb_messaging_sender_id": config.FIREBASE_MESSAGING_SENDER_ID,
        "fb_app_id":             config.FIREBASE_APP_ID,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context=_firebase_web_config())


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context=_firebase_web_config())


# ── Pepperstone OAuth2 flow ───────────────────────────────────────────────────

def _pepperstone_redirect_uri(request: Request) -> str:
    from btc_agent import config
    if config.PEPPERSTONE_REDIRECT_URI:
        return config.PEPPERSTONE_REDIRECT_URI
    scheme = request.headers.get("X-Forwarded-Proto", request.url.scheme)
    host   = request.headers.get("X-Forwarded-Host", request.url.netloc)
    return f"{scheme}://{host}/auth/pepperstone/callback"


@app.get("/auth/pepperstone")
async def pepperstone_auth_start(token: str, request: Request):
    """Step 1: validate Firebase token, generate state, redirect to cTrader authorize."""
    from btc_agent import config
    try:
        from firebase_admin import auth as fb_auth
        decoded = fb_auth.verify_id_token(token)
        uid = decoded["uid"]
    except Exception:
        return HTMLResponse("<p>Invalid session. Close this window and try again.</p>", status_code=401)

    from btc_agent.trading.firestore_store import load_user_prefs
    prefs = load_user_prefs(uid) or {}
    client_id = prefs.get("pepperstone_client_id") or config.PEPPERSTONE_CLIENT_ID
    if not client_id:
        return HTMLResponse("<p>Save your Pepperstone Client ID in Settings first.</p>", status_code=400)

    state = secrets.token_urlsafe(32)
    _pepperstone_states[state] = {"uid": uid, "expires": time.time() + 300}
    # Prune stale states
    now = time.time()
    for k in [k for k, v in _pepperstone_states.items() if v["expires"] < now]:
        _pepperstone_states.pop(k, None)

    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id":     client_id,
        "redirect_uri":  _pepperstone_redirect_uri(request),
        "scope":         "trading",
        "state":         state,
    })
    return RedirectResponse(f"https://id.ctrader.com/connect/authorize?{params}")


@app.get("/auth/pepperstone/callback")
async def pepperstone_callback(request: Request, code: str = None, state: str = None, error: str = None):
    """Step 2: exchange code for tokens, save refresh_token to Firestore."""
    if error:
        return HTMLResponse(f"<html><body><p>Authorization denied: {error}</p>"
                            "<script>setTimeout(()=>window.close(),2000);</script></body></html>")

    state_data = _pepperstone_states.pop(state or "", None)
    if not state_data or time.time() > state_data["expires"]:
        return HTMLResponse("<html><body><p>Invalid or expired state. Please try again.</p>"
                            "<script>setTimeout(()=>window.close(),2000);</script></body></html>",
                            status_code=400)

    uid = state_data["uid"]
    from btc_agent import config
    from btc_agent.trading.firestore_store import load_user_prefs, save_user_prefs
    prefs = load_user_prefs(uid) or {}
    client_id     = prefs.get("pepperstone_client_id")     or config.PEPPERSTONE_CLIENT_ID
    client_secret = prefs.get("pepperstone_client_secret") or config.PEPPERSTONE_CLIENT_SECRET

    try:
        data = urllib.parse.urlencode({
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  _pepperstone_redirect_uri(request),
            "client_id":     client_id,
            "client_secret": client_secret,
        }).encode()
        req = urllib.request.Request(
            "https://id.ctrader.com/connect/token", data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        return HTMLResponse(f"<html><body><p>Token exchange failed: {e}</p>"
                            "<script>setTimeout(()=>window.close(),3000);</script></body></html>",
                            status_code=500)

    refresh_token = result.get("refresh_token", "")
    if not refresh_token:
        return HTMLResponse("<html><body><p>No refresh_token in response. "
                            "Ensure your cTrader app has offline_access scope.</p>"
                            "<script>setTimeout(()=>window.close(),3000);</script></body></html>",
                            status_code=500)

    save_user_prefs(uid, {"pepperstone_refresh_token": refresh_token})
    return HTMLResponse("""
        <html><body style="font-family:sans-serif;text-align:center;padding:40px">
        <h2>&#x2705; Pepperstone Connected!</h2>
        <p>This window will close automatically.</p>
        <script>setTimeout(()=>{ window.close(); if(window.opener) window.opener.location.reload(); }, 1500);</script>
        </body></html>
    """)


# ── Public API: scan + briefing ───────────────────────────────────────────────

@pub.get("/price")
async def get_price():
    from btc_agent.trading.scanner import _scanners
    price = next((sc.last_price for sc in _scanners.values() if sc.last_price), None)
    if not price:
        from btc_agent.scanner.data import fetch_current_price
        price = fetch_current_price()
    return JSONResponse({"price": price})


@pub.get("/liquidity")
async def get_liquidity():
    import csv as _csv
    from pathlib import Path
    csv_path = Path("leverage_data.csv")
    if not csv_path.exists():
        return JSONResponse({"rows": [], "status": "no_data"})
    rows = []
    with open(csv_path, newline="") as f:
        for row in _csv.DictReader(f):
            rows.append(row)
    return JSONResponse({"rows": rows[-200:], "status": "ok"})


@pub.get("/scan")
async def get_scan():
    return JSONResponse(storage.load_scan())


@pub.get("/brief")
async def get_brief():
    return JSONResponse(storage.load_briefing())


@pub.post("/scan/trigger")
async def trigger_scan():
    global _scan_running
    with _scan_lock:
        if _scan_running:
            return JSONResponse({"status": "already_running"})
        _scan_running = True

    def _run():
        global _scan_running
        try:
            from btc_agent.scanner.agent import run_scanner
            run_scanner()
        finally:
            _scan_running = False

    threading.Thread(target=_run, daemon=True).start()
    return JSONResponse({"status": "started"})


@pub.post("/brief/trigger")
async def trigger_brief():
    global _brief_running
    with _brief_lock:
        if _brief_running:
            return JSONResponse({"status": "already_running"})
        _brief_running = True

    def _run():
        global _brief_running
        try:
            from btc_agent.briefing.agent import run_briefing
            run_briefing()
        finally:
            _brief_running = False

    threading.Thread(target=_run, daemon=True).start()
    return JSONResponse({"status": "started"})


@pub.get("/status")
async def status():
    from btc_agent.trading.scanner import is_any_running
    flags = _get_feature_flags()
    return JSONResponse(
        {"scan_running": _scan_running, "brief_running": _brief_running,
         "trading_running": is_any_running(),
         "vishal_enabled": flags.get("vishal_enabled", False),
         "retracement_enabled": flags.get("retracement_enabled", False)}
    )


# ── Private API: live trading (auth required) ─────────────────────────────────

@priv.get("/state")
async def trading_state(token: dict = Depends(verify_token)):
    from btc_agent.trading.scanner import get_state
    return JSONResponse(get_state(token["uid"]))


@priv.post("/start")
async def trading_start(token: dict = Depends(verify_token)):
    from btc_agent.trading.scanner import get_state, run_trading_scanner
    uid = token["uid"]
    state = get_state(uid)
    if state["running"]:
        return JSONResponse({"status": "already_running"})

    # Load user's trading settings from Firestore to seed the scanner
    user_settings: dict = {}
    try:
        from btc_agent.trading.firestore_store import load_user_prefs
        prefs = load_user_prefs(uid) or {}
        setting_keys = {"mode", "tf_min", "tf_max", "scan_interval_min", "qty",
                        "max_sl", "min_tp", "max_concurrent", "patterns", "broker", "broker_nickname",
                        "bias_filter", "lookback_candles", "entry_mode",
                        "bsg_enabled", "bsg_trade_enabled",
                        "coinbase_api_key", "coinbase_api_secret",
                        "binance_api_key", "binance_api_secret",
                        "bybit_api_key", "bybit_api_secret",
                        "delta_api_key", "delta_api_secret",
                        "pepperstone_client_id", "pepperstone_client_secret",
                        "pepperstone_access_token", "pepperstone_account_id",
                        "pepperstone_is_live",
                        "coindcx_api_key", "coindcx_api_secret"}
        user_settings = {k: v for k, v in prefs.items() if k in setting_keys}
    except Exception as e:
        pass

    threading.Thread(
        target=run_trading_scanner,
        args=(uid,),
        kwargs={"user_settings": user_settings, "email": token.get("email", "")},
        daemon=True,
        name=f"trading-{uid[:8]}",
    ).start()
    return JSONResponse({"status": "started"})


@priv.post("/autostart")
async def trading_autostart(token: dict = Depends(verify_token)):
    """Called by frontend on login — restarts scanner if Firestore says it was running."""
    from btc_agent.trading.scanner import get_state, run_trading_scanner
    from btc_agent.trading.firestore_store import load_user_prefs
    uid = token["uid"]
    if get_state(uid)["running"]:
        return JSONResponse({"status": "already_running"})
    prefs = load_user_prefs(uid) or {}
    if not prefs.get("scanner_running"):
        return JSONResponse({"status": "not_requested"})
    setting_keys = {"mode", "tf_min", "tf_max", "scan_interval_min", "qty",
                    "max_sl", "min_tp", "max_concurrent", "patterns", "broker", "broker_nickname",
                    "bias_filter", "lookback_candles", "entry_mode",
                    "bsg_enabled", "bsg_trade_enabled",
                    "coinbase_api_key", "coinbase_api_secret",
                    "binance_api_key", "binance_api_secret",
                    "bybit_api_key", "bybit_api_secret",
                    "delta_api_key", "delta_api_secret",
                    "pepperstone_client_id", "pepperstone_client_secret",
                    "pepperstone_refresh_token", "pepperstone_account_id",
                    "pepperstone_is_live",
                    "coindcx_api_key", "coindcx_api_secret"}
    user_settings = {k: v for k, v in prefs.items() if k in setting_keys}
    threading.Thread(
        target=run_trading_scanner,
        args=(uid,),
        kwargs={"user_settings": user_settings, "email": token.get("email", "")},
        daemon=True,
        name=f"trading-{uid[:8]}-autostart",
    ).start()
    return JSONResponse({"status": "started"})


@priv.post("/stop")
async def trading_stop(token: dict = Depends(verify_token)):
    from btc_agent.trading.scanner import stop_trading_scanner
    stop_trading_scanner(token["uid"])
    return JSONResponse({"status": "stopped"})


@priv.get("/settings")
async def trading_get_settings(token: dict = Depends(verify_token)):
    from btc_agent.trading.scanner import get_state
    from btc_agent.trading.firestore_store import load_user_prefs
    uid = token["uid"]
    settings = get_state(uid)["settings"]
    # Merge Firestore prefs so UI shows correct values even when scanner is stopped
    try:
        prefs = load_user_prefs(uid) or {}
        fs_keys = {"mode", "tf_min", "tf_max", "scan_interval_min", "qty",
                   "max_sl", "min_tp", "max_concurrent", "patterns", "broker",
                   "broker_nickname", "bias_filter", "lookback_candles",
                   "entry_mode", "bsg_enabled", "bsg_trade_enabled", "trail_offset"}
        for k in fs_keys:
            if k in prefs:
                settings[k] = prefs[k]
    except Exception:
        pass
    return JSONResponse(settings)


@priv.post("/settings")
async def trading_save_settings(body: dict = Body(...), token: dict = Depends(verify_token)):
    from btc_agent.trading.firestore_store import save_user_prefs
    from btc_agent.trading.scanner import _scanners
    qty = body.get("qty")
    if qty is not None and not _is_valid_qty(qty):
        raise HTTPException(status_code=422, detail="Qty must be a multiple of 2")
    uid = token["uid"]
    setting_keys = {"mode", "tf_min", "tf_max", "scan_interval_min", "qty",
                    "max_sl", "min_tp", "max_concurrent", "patterns", "vishal", "bias_filter",
                    "trail_offset", "lookback_candles", "entry_mode",
                    "broker", "broker_nickname", "bsg_enabled", "bsg_trade_enabled"}
    clean = {k: v for k, v in body.items() if k in setting_keys and v is not None}
    save_user_prefs(uid, clean)
    # Update live scanner if running
    sc = _scanners.get(uid)
    if sc is not None:
        sc.settings.update(clean)
    return JSONResponse({"status": "saved", "settings": clean})


@priv.post("/position/{signal_id}/cancel")
async def cancel_position(signal_id: str, token: dict = Depends(verify_token)):
    from btc_agent.trading import scanner
    sc = scanner._scanners.get(token["uid"])
    if sc is None:
        return JSONResponse({"error": "scanner not running"}, status_code=404)
    pos = next(
        (p for p in sc.open_positions if p.signal_id == signal_id and p.status == "open"),
        None,
    )
    if not pos:
        return JSONResponse({"error": "position not found"}, status_code=404)
    price = sc.last_price or pos.entry_price
    scanner._close_position(sc, pos, price, "manual")
    scanner._save_state(sc)
    return JSONResponse({"status": "cancelled"})


# ── Settings API ──────────────────────────────────────────────────────────────

_SENSITIVE_APP = ["anthropic_api_key", "telegram_bot_token", "email_pass"]
_SENSITIVE_USER = [
    "coinbase_api_key", "coinbase_api_secret",
    "binance_api_key", "binance_api_secret",
    "bybit_api_key", "bybit_api_secret",
    "delta_api_key", "delta_api_secret",
    "coindcx_api_key", "coindcx_api_secret",
    "pepperstone_client_secret", "pepperstone_refresh_token",
]


@priv_cfg.get("/app")
async def settings_get_app():
    from btc_agent.trading.firestore_store import load_app_settings
    data = load_app_settings() or {}
    return JSONResponse(_mask_dict(data, _SENSITIVE_APP))


@priv_cfg.put("/app")
async def settings_save_app(body: dict = Body(...), _: dict = Depends(_require_admin)):
    from btc_agent import config
    from btc_agent.trading.firestore_store import save_app_settings
    clean = {k: v for k, v in body.items() if v is not None and "****" not in str(v)}
    save_app_settings(clean)
    config.apply_settings(clean)
    return JSONResponse({"status": "saved"})


@priv_cfg.get("/user")
async def settings_get_user(token: dict = Depends(verify_token)):
    from btc_agent.trading.firestore_store import load_user_prefs
    data = load_user_prefs(token["uid"]) or {}
    return JSONResponse(_mask_dict(data, _SENSITIVE_USER))


@priv_cfg.put("/user")
async def settings_save_user(body: dict = Body(...), token: dict = Depends(verify_token)):
    from btc_agent import config
    from btc_agent.trading.firestore_store import save_user_prefs
    clean = {k: v for k, v in body.items() if v is not None and "****" not in str(v)}
    save_user_prefs(token["uid"], clean)
    config.apply_settings(clean)
    return JSONResponse({"status": "saved"})


# Admin API — owner only
admin_router = APIRouter(prefix="/api/admin", dependencies=[Depends(_require_admin)])


@admin_router.get("/users")
async def admin_list_users():
    import firebase_admin.auth as fb_auth
    from btc_agent.trading.scanner import _scanners
    from btc_agent.trading.firestore_store import load_user_prefs
    users = []
    try:
        page = fb_auth.list_users()
        for user in page.users:
            uid = user.uid
            sc = _scanners.get(uid)
            if sc:
                mode   = sc.settings.get("mode", "paper")
                broker = sc.settings.get("broker", "coinbase")
                running = sc.running
            else:
                prefs  = load_user_prefs(uid) or {}
                mode   = prefs.get("mode", "paper")
                broker = prefs.get("broker", "coinbase")
                running = False
            users.append({
                "uid":          uid,
                "email":        user.email or "",
                "display_name": user.display_name or user.email or uid[:8],
                "mode":         mode,
                "broker":       broker,
                "scanner_running": running,
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(users)


@admin_router.post("/users/{uid}/stop")
async def admin_stop_user(uid: str):
    from btc_agent.trading.scanner import stop_trading_scanner
    stop_trading_scanner(uid)
    return JSONResponse({"status": "stopped"})


@admin_router.post("/users/{uid}/mode")
async def admin_set_mode(uid: str, body: dict = Body(...)):
    from btc_agent.trading.firestore_store import save_user_prefs
    from btc_agent.trading.scanner import _scanners
    mode = body.get("mode")
    if mode not in ("paper", "live"):
        raise HTTPException(status_code=422, detail="mode must be 'paper' or 'live'")
    save_user_prefs(uid, {"mode": mode})
    sc = _scanners.get(uid)
    if sc:
        sc.settings["mode"] = mode
    return JSONResponse({"status": "saved"})


@admin_router.get("/users/{uid}/state")
async def admin_user_state(uid: str, token: dict = Depends(_require_admin)):
    from btc_agent.trading.scanner import get_state, _scanners
    # If scanner is live in memory, return its current state
    if uid in _scanners:
        return JSONResponse(get_state(uid))
    # Scanner not running — load historical data directly from Firestore
    try:
        from btc_agent.trading.firestore_store import load_state as fs_load_state
        state = fs_load_state(uid) or {}
        return JSONResponse({
            "signals":   state.get("signals", []),
            "positions": state.get("positions", []),
            "history":   state.get("history", []),
            "running":   False,
        })
    except Exception:
        return JSONResponse({"signals": [], "positions": [], "history": [], "running": False})


app.include_router(pub)
app.include_router(priv)
app.include_router(priv_cfg)
app.include_router(admin_router)


@app.on_event("startup")
async def _start_liquidity_collector():
    import os
    if os.getenv("LIQUIDITY_ENABLED", "true").lower() == "false":
        return
    import asyncio

    def _run():
        import time as _time
        while True:
            try:
                from btc_agent.liquidity.collector import run_collect
                asyncio.run(run_collect())
            except Exception as exc:
                print(f"[liquidity-collector] crashed: {exc} — restarting in 60s")
            _time.sleep(60)

    t = threading.Thread(target=_run, daemon=True, name="liquidity-collector")
    t.start()
