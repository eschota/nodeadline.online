from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from libs.protocol import UserIdentity

_lock = threading.Lock()
_DATA_DIR: str | None = None


def set_data_dir(d: str) -> None:
    global _DATA_DIR
    _DATA_DIR = d


def _path() -> str:
    base = _DATA_DIR or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
    )
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "users.json")


def _load() -> dict[str, Any]:
    p = _path()
    if not os.path.isfile(p):
        return {"users": []}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict[str, Any]) -> None:
    p = _path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def upsert_user(*, sub: str, email: str, name: str, picture: str, username: str) -> UserIdentity:
    with _lock:
        data = _load()
        users = data.setdefault("users", [])
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for u in users:
            if u.get("google_sub") == sub:
                u.update({
                    "email": email,
                    "name": name,
                    "picture": picture,
                    "username": username,
                })
                _save(data)
                return UserIdentity.from_dict(u)
        ent = {
            "google_sub": sub,
            "email": email,
            "name": name,
            "picture": picture,
            "username": username,
            "created_at": now,
        }
        users.append(ent)
        _save(data)
        return UserIdentity.from_dict(ent)


def get_user_by_username(username: str) -> UserIdentity | None:
    data = _load()
    for u in data.get("users", []):
        if u.get("username") == username:
            return UserIdentity.from_dict(u)
    return None


def get_user_by_sub(sub: str) -> UserIdentity | None:
    data = _load()
    for u in data.get("users", []):
        if u.get("google_sub") == sub:
            return UserIdentity.from_dict(u)
    return None


def list_users() -> list[dict[str, Any]]:
    """Все записи из users.json (для каталога на мастере)."""
    data = _load()
    out: list[dict[str, Any]] = []
    for u in data.get("users") or []:
        if isinstance(u, dict):
            out.append(dict(u))
    return out
