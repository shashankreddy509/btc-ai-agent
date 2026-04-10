import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from btc_agent import storage

BASE = Path(__file__).parent

app = FastAPI(title="BTC AI Agent Dashboard")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

# Track background task state
_scan_running  = False
_brief_running = False
_scan_lock     = threading.Lock()
_brief_lock    = threading.Lock()


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
        {"scan_running": _scan_running, "brief_running": _brief_running}
    )
