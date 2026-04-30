"""
Firestore persistence for trading state.

Collections:
  trading_signals/{signal_id}      — one document per signal
  trading_positions/{signal_id}    — one document per position (upserted on every change)
  trading_history/{signal_id}_{suffix} — one document per close event

All writes are fire-and-forget (background thread) so they never block the 5-second tick loop.
Reads (load_state) are synchronous — called once at scanner startup.
"""
from __future__ import annotations

import threading
from typing import Any

from rich.console import Console
from google.cloud.firestore_v1.base_query import FieldFilter

console = Console()


def _get_db():
    from btc_agent.firebase_app import get_firebase_app
    from firebase_admin import firestore
    get_firebase_app()
    return firestore.client()


def _bg(fn, *args) -> None:
    """Run fn(*args) in a daemon thread — fire and forget."""
    threading.Thread(target=fn, args=args, daemon=True).start()


# ── Writes ─────────────────────────────────────────────────────────────────────

def save_signal(d: dict, uid: str) -> None:
    doc = {**d, "uid": uid}
    def _write():
        try:
            _get_db().collection("trading_signals").document(doc["id"]).set(doc)
        except Exception as e:
            console.print(f"[dim yellow]FS signal write failed: {e}[/dim yellow]")
    _bg(_write)


def update_signal_status(signal_id: str, status: str) -> None:
    def _write():
        try:
            _get_db().collection("trading_signals").document(signal_id).update({"status": status})
        except Exception as e:
            console.print(f"[dim yellow]FS signal update failed: {e}[/dim yellow]")
    _bg(_write)


def save_position(d: dict, uid: str) -> None:
    doc = {**d, "uid": uid}
    def _write():
        try:
            _get_db().collection("trading_positions").document(doc["signal_id"]).set(doc)
        except Exception as e:
            console.print(f"[dim yellow]FS position write failed: {e}[/dim yellow]")
    _bg(_write)


def save_history(d: dict, doc_id: str, uid: str) -> None:
    doc = {**d, "uid": uid}
    def _write():
        try:
            _get_db().collection("trading_history").document(doc_id).set(doc)
        except Exception as e:
            console.print(f"[dim yellow]FS history write failed: {e}[/dim yellow]")
    _bg(_write)


# ── App-level settings (app_settings/config) ───────────────────────────────────

def save_app_settings(d: dict) -> None:
    def _write():
        try:
            _get_db().collection("app_settings").document("config").set(d, merge=True)
        except Exception as e:
            console.print(f"[dim yellow]FS app_settings write failed: {e}[/dim yellow]")
    _bg(_write)


def load_app_settings() -> dict | None:
    try:
        doc = _get_db().collection("app_settings").document("config").get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        console.print(f"[yellow]Firestore load_app_settings failed: {e}[/yellow]")
        return None


# ── User-level settings (user_settings/{uid}) ──────────────────────────────────

def save_user_prefs(uid: str, d: dict) -> None:
    def _write():
        try:
            _get_db().collection("user_settings").document(uid).set(d, merge=True)
        except Exception as e:
            console.print(f"[dim yellow]FS user_prefs write failed: {e}[/dim yellow]")
    _bg(_write)


def load_user_prefs(uid: str) -> dict | None:
    try:
        doc = _get_db().collection("user_settings").document(uid).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        console.print(f"[yellow]Firestore load_user_prefs failed: {e}[/yellow]")
        return None


# ── Read ───────────────────────────────────────────────────────────────────────

def load_state(uid: str) -> dict | None:
    """
    Read all three collections for the given uid, or None if Firestore is unavailable.
    Admin uid (FIREBASE_OWNER_UID) loads all docs for backward compat with untagged records.
    """
    try:
        from btc_agent import config as _cfg
        db = _get_db()
        is_admin = uid == _cfg.FIREBASE_OWNER_UID

        if is_admin:
            sig_query = db.collection("trading_signals").where(filter=FieldFilter("status", "==", "pending"))
            pos_query = db.collection("trading_positions").where(filter=FieldFilter("status", "==", "open"))
            hist_query = db.collection("trading_history")
        else:
            sig_query  = db.collection("trading_signals").where(filter=FieldFilter("uid", "==", uid)).where(filter=FieldFilter("status", "==", "pending"))
            pos_query  = db.collection("trading_positions").where(filter=FieldFilter("uid", "==", uid)).where(filter=FieldFilter("status", "==", "open"))
            hist_query = db.collection("trading_history").where(filter=FieldFilter("uid", "==", uid))

        signals   = [doc.to_dict() for doc in sig_query.stream()]
        positions = [doc.to_dict() for doc in pos_query.stream()]
        history   = sorted(
            [doc.to_dict() for doc in hist_query.stream()],
            key=lambda d: d.get("closed_at", ""),
        )
        return {"signals": signals, "positions": positions, "history": history}
    except Exception as e:
        console.print(f"[yellow]Firestore load_state failed: {e}[/yellow]")
        return None
