import json
import os
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

SCAN_FILE = DATA_DIR / "latest_scan.json"
BRIEF_FILE = DATA_DIR / "latest_briefing.json"


def save_scan(results: list[dict]) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    SCAN_FILE.write_text(json.dumps(payload, indent=2))


def load_scan() -> dict:
    if not SCAN_FILE.exists():
        return {"timestamp": None, "results": []}
    return json.loads(SCAN_FILE.read_text())


def save_briefing(text: str) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": text,
    }
    BRIEF_FILE.write_text(json.dumps(payload, indent=2))


def load_briefing() -> dict:
    if not BRIEF_FILE.exists():
        return {"timestamp": None, "text": "No briefing generated yet."}
    return json.loads(BRIEF_FILE.read_text())
