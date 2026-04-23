"""Shared Firebase Admin App — initialised once, reused by auth and Firestore modules."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import firebase_admin
from firebase_admin import credentials

_SERVICE_ACCOUNT_PATH = Path(__file__).parent.parent / "serviceAccountKey.json"


@lru_cache(maxsize=1)
def get_firebase_app() -> firebase_admin.App:
    if _SERVICE_ACCOUNT_PATH.exists():
        cred = credentials.Certificate(str(_SERVICE_ACCOUNT_PATH))
    elif os.environ.get("FIREBASE_SERVICE_ACCOUNT"):
        cred = credentials.Certificate(json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT"]))
    else:
        raise RuntimeError(
            "Firebase Admin credentials not found. "
            "Place serviceAccountKey.json in the project root, "
            "or set the FIREBASE_SERVICE_ACCOUNT env var."
        )
    try:
        return firebase_admin.get_app()
    except ValueError:
        return firebase_admin.initialize_app(cred)
