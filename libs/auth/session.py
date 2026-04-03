from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

SESSION_COOKIE = "nd_session"
SESSION_TTL = 86400 * 7
HANDOFF_TTL_SEC = 120


def sign_session(payload: dict[str, Any], secret: str) -> str:
    payload = dict(payload)
    payload["exp"] = int(time.time()) + SESSION_TTL
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(body + b"." + sig).decode().rstrip("=")


def verify_session(token: str, secret: str) -> dict[str, Any] | None:
    try:
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + pad)
        body, sig = raw.rsplit(b".", 1)
        expect = hmac.new(secret.encode(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expect):
            return None
        data = json.loads(body.decode())
        if int(data.get("exp", 0)) < time.time():
            return None
        return data
    except Exception:
        return None


def sign_handoff(payload: dict[str, Any], secret: str) -> str:
    """Короткоживущий токен для переноса сессии с localhost на публичный HTTPS-хост (один запрос claim)."""
    payload = dict(payload)
    payload["exp"] = int(time.time()) + HANDOFF_TTL_SEC
    payload["handoff"] = True
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(body + b"." + sig).decode().rstrip("=")


def verify_handoff(token: str, secret: str) -> dict[str, Any] | None:
    data = verify_session(token, secret)
    if not data or not data.get("handoff"):
        return None
    return data
