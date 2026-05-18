import logging

from firebase_admin import auth as fb_auth
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from btc_agent.firebase_app import get_firebase_app

_bearer = HTTPBearer(auto_error=False)
_log = logging.getLogger(__name__)


async def verify_token(
    creds: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> dict:
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        get_firebase_app()
        return fb_auth.verify_id_token(creds.credentials)
    except (ValueError, fb_auth.InvalidIdTokenError) as e:
        _log.warning("auth rejected: %s", e)
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    except Exception as e:
        _log.error("auth service error: %s", e)
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
