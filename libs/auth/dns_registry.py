"""Реестр привязок sub → WAN → fqdn на мастере (после DNS claim)."""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from libs.auth import users

_lock = threading.Lock()


def _path() -> str:
    users._path()  # ensure data dir exists (users.json)
    base = os.path.dirname(users._path())
    return os.path.join(base, "dns_bindings.json")


def _load() -> dict[str, Any]:
    p = _path()
    if not os.path.isfile(p):
        return {"bindings": {}}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict[str, Any]) -> None:
    p = _path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def get_binding(sub: str) -> dict[str, Any] | None:
    sub = str(sub).strip()
    if not sub:
        return None
    data = _load()
    b = (data.get("bindings") or {}).get(sub)
    if not isinstance(b, dict):
        return None
    return dict(b)


def upsert_binding(
    *,
    sub: str,
    username: str,
    email: str,
    wan_ipv4: str,
    fqdn: str,
    public_port: int,
    ingress_ipv4: str,
) -> None:
    sub = str(sub).strip()
    if not sub:
        return
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _lock:
        data = _load()
        bindings = data.setdefault("bindings", {})
        bindings[sub] = {
            "username": str(username).strip(),
            "email": str(email).strip(),
            "wan_ipv4": str(wan_ipv4).strip(),
            "fqdn": str(fqdn).strip(),
            "public_port": int(public_port),
            "ingress_ipv4": str(ingress_ipv4).strip(),
            "updated_at": now,
        }
        _save(data)


def load_all_bindings() -> dict[str, dict[str, Any]]:
    """Все привязки sub → запись (для nginx map на ingress)."""
    data = _load()
    out: dict[str, dict[str, Any]] = {}
    for k, v in (data.get("bindings") or {}).items():
        if isinstance(v, dict):
            out[str(k)] = dict(v)
    return out
