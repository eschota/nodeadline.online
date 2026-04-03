"""
Вшитые на мастере секреты Namecheap: Fernet-файл + ключ только в окружении сервера.
Файл apps/master/embedded/namecheap.fernet — base64-текст одной строкой (ciphertext).
Ключ: NODEADLINE_FERNET_KEY (то же значение, что даёт Fernet.generate_key()).
"""
from __future__ import annotations

import json
import os
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def merge_encrypted_namecheap(cfg: dict[str, Any]) -> dict[str, Any]:
    key_raw = os.environ.get("NODEADLINE_FERNET_KEY", "").strip()
    if not key_raw:
        return cfg
    path = os.path.join(_ROOT, "apps", "master", "embedded", "namecheap.fernet")
    if not os.path.isfile(path):
        return cfg
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError:
        return cfg
    try:
        f = Fernet(key_raw.encode("ascii"))
        with open(path, encoding="utf-8") as fp:
            raw = fp.read().strip()
        dec = f.decrypt(raw.encode("ascii"))
        overlay = json.loads(dec.decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, InvalidToken):
        return cfg
    if not isinstance(overlay, dict):
        return cfg
    out = dict(cfg)
    nc = dict(out.get("namecheap") or {})
    for k, v in (overlay.get("namecheap") or {}).items():
        if v is not None and str(v).strip() != "":
            nc[k] = v
    out["namecheap"] = nc
    return out
