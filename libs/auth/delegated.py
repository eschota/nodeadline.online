from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlparse

import urllib.request
import json

_redeem: dict[str, dict[str, Any]] = {}
_REDEEM_TTL = 300


def allowed_return_to(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        host = (p.hostname or "").lower()
        return host in ("127.0.0.1", "localhost", "::1")
    except Exception:
        return False


def generate_redeem_code(*, sub: str, email: str, name: str, picture: str) -> str:
    code = secrets.token_urlsafe(32)
    _redeem[code] = {
        "sub": sub,
        "email": email,
        "name": name,
        "picture": picture,
        "created_at": int(time.time()),
    }
    return code


def consume_redeem_code(code: str) -> dict[str, Any] | None:
    entry = _redeem.pop(code, None)
    if not entry:
        return None
    if int(time.time()) - entry["created_at"] > _REDEEM_TTL:
        return None
    return {k: v for k, v in entry.items() if k != "created_at"}


def node_exchange_code(*, master_url: str, code: str) -> dict[str, Any]:
    url = f"{master_url.rstrip('/')}/api/oauth/v1/redeem"
    body = json.dumps({"code": code}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode())
