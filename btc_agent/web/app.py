import json
import threading
from pathlib import Path

from fastapi import FastAPI, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from btc_agent import storage

BASE = Path(__file__).parent
_TRADING_SETTINGS_PATH = Path(__file__).parent.parent / "data" / "trading_settings.json"

app = FastAPI(title="BTC AI Agent Dashboard")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

# Track background task state
_scan_running    = False
_brief_running   = False
_trading_running = False
_scan_lock     = threading.Lock()
_brief_lock    = threading.Lock()
_trading_lock  = threading.Lock()
_trading_thread: threading.Thread | None = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/scan")
async def get_scan():
    return JSONResponse(storage.load_scan())


@app.get("/api/brief")
async def get_brief():
    return JSONResponse(storage.load_briefing())


@app.post("/api/scan/trigger")
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


@app.post("/api/brief/trigger")
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


@app.get("/api/status")
async def status():
    return JSONResponse(
        {"scan_running": _scan_running, "brief_running": _brief_running,
         "trading_running": _trading_running}
    )


# ── Trading scanner ───────────────────────────────────────────────────────────

@app.get("/api/trading/state")
async def trading_state():
    from btc_agent.trading.scanner import get_state
    return JSONResponse(get_state())


@app.post("/api/trading/start")
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


@app.post("/api/trading/stop")
async def trading_stop():
    global _trading_running
    from btc_agent.trading.scanner import stop_trading_scanner
    stop_trading_scanner()
    _trading_running = False
    return JSONResponse({"status": "stopped"})


@app.get("/api/trading/settings")
async def trading_get_settings():
    from btc_agent.trading.scanner import get_state
    return JSONResponse(get_state()["settings"])


@app.post("/api/trading/settings")
async def trading_save_settings(body: dict = Body(...)):
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
