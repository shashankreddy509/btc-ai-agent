import json
import threading
from pathlib import Path

from fastapi import FastAPI, Body, Depends, APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from btc_agent import storage
from btc_agent.web.auth import verify_token

BASE = Path(__file__).parent
_TRADING_SETTINGS_PATH = Path(__file__).parent.parent / "data" / "trading_settings.json"

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
_trading_running = False
_scan_lock     = threading.Lock()
_brief_lock    = threading.Lock()
_trading_lock  = threading.Lock()
_trading_thread: threading.Thread | None = None


def _mask(s: str) -> str:
    s = str(s)
    return s[:4] + "****" + s[-4:] if len(s) > 8 else "****"


def _mask_dict(d: dict, fields: list[str]) -> dict:
    out = dict(d)
    for f in fields:
        if out.get(f):
            out[f] = _mask(out[f])
    return out


async def _require_admin(token: dict = Depends(verify_token)) -> dict:
    from btc_agent import config
    owner = config.FIREBASE_OWNER_UID
    if not owner or token.get("uid") != owner:
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
    except Exception as e:
        print(f"[startup] Firestore settings load skipped: {e}")


# ── Public pages ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")


# ── Public API: scan + briefing ───────────────────────────────────────────────

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
    return JSONResponse(
        {"scan_running": _scan_running, "brief_running": _brief_running,
         "trading_running": _trading_running}
    )


# ── Private API: live trading (auth required) ─────────────────────────────────

@priv.get("/state")
async def trading_state():
    from btc_agent.trading.scanner import get_state
    return JSONResponse(get_state())


@priv.post("/start")
async def trading_start():
    global _trading_running, _trading_thread
    with _trading_lock:
        if _trading_running:
            return JSONResponse({"status": "already_running"})
        _trading_running = True

    def _run():
        global _trading_running
        try:
            from btc_agent.trading.scanner import run_trading_scanner
            run_trading_scanner()
        finally:
            _trading_running = False

    _trading_thread = threading.Thread(target=_run, daemon=True, name="trading")
    _trading_thread.start()
    return JSONResponse({"status": "started"})


@priv.post("/stop")
async def trading_stop():
    global _trading_running
    from btc_agent.trading.scanner import stop_trading_scanner
    stop_trading_scanner()
    _trading_running = False
    return JSONResponse({"status": "stopped"})


@priv.get("/settings")
async def trading_get_settings():
    from btc_agent.trading.scanner import get_state
    return JSONResponse(get_state()["settings"])


@priv.post("/settings")
async def trading_save_settings(body: dict = Body(...), _: dict = Depends(_require_admin)):
    from btc_agent import config
    from btc_agent.trading.firestore_store import save_app_settings
    # Map trading settings keys to Firestore keys and apply to config
    fs_body = {
        "trading_mode":             body.get("mode"),
        "trading_tf_min":           body.get("tf_min"),
        "trading_tf_max":           body.get("tf_max"),
        "trading_scan_interval_min": body.get("scan_interval_min"),
        "trading_qty":              body.get("qty"),
        "trading_max_sl":           body.get("max_sl"),
        "trading_min_tp":           body.get("min_tp"),
        "trading_max_concurrent":   body.get("max_concurrent"),
        "trading_patterns":         body.get("patterns"),
    }
    fs_body = {k: v for k, v in fs_body.items() if v is not None}
    save_app_settings(fs_body)
    config.apply_settings(fs_body)
    # Also keep local JSON for backward compat with scanner get_state()
    _TRADING_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if _TRADING_SETTINGS_PATH.exists():
        try:
            existing = json.loads(_TRADING_SETTINGS_PATH.read_text())
        except Exception:
            pass
    existing.update(body)
    _TRADING_SETTINGS_PATH.write_text(json.dumps(existing, indent=2))
    return JSONResponse({"status": "saved", "settings": existing})


@priv.post("/position/{signal_id}/cancel")
async def cancel_position(signal_id: str, _: dict = Depends(_require_admin)):
    from btc_agent.trading import scanner
    pos = next(
        (p for p in scanner.open_positions if p.signal_id == signal_id and p.status == "open"),
        None,
    )
    if not pos:
        return JSONResponse({"error": "position not found"}, status_code=404)
    price = scanner._last_price or pos.entry_price
    scanner._close_position(pos, price, "manual")
    scanner._save_state()
    return JSONResponse({"status": "cancelled"})


# ── Settings API ──────────────────────────────────────────────────────────────

_SENSITIVE_APP = ["anthropic_api_key", "telegram_bot_token", "email_pass"]
_SENSITIVE_USER = ["coinbase_api_key", "coinbase_api_secret"]


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


app.include_router(pub)
app.include_router(priv)
app.include_router(priv_cfg)
