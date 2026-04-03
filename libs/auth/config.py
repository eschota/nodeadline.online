from __future__ import annotations

import json
import os
import secrets
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_cached: dict[str, Any] | None = None


def _config_path() -> str:
    explicit = os.environ.get("NODEADLINE_CONFIG", "").strip()
    if explicit:
        return explicit
    for name in ("nodeadline.json", "master.json"):
        p = os.path.join(_ROOT, name)
        if os.path.isfile(p):
            return p
    return os.path.join(_ROOT, "nodeadline.json")


def _merge_embedded(cfg: dict[str, Any]) -> dict[str, Any]:
    try:
        from libs.auth.embedded_secrets import merge_encrypted_namecheap

        return merge_encrypted_namecheap(cfg)
    except Exception:
        return cfg


def load_config() -> dict[str, Any]:
    global _cached
    if _cached is not None:
        return _cached
    p = _config_path()
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            _cached = json.load(f)
    else:
        _cached = {}
    _cached = _merge_embedded(_cached)
    return _cached


def reload_config() -> dict[str, Any]:
    global _cached, _session_secret_memo
    _cached = None
    _session_secret_memo = None
    return load_config()


def role() -> str:
    return str(load_config().get("role", "node")).strip().lower()


def is_master() -> bool:
    return role() == "master"


def oauth_section() -> dict[str, Any]:
    return load_config().get("oauth") or {}


def google_creds() -> tuple[str, str]:
    g = oauth_section().get("google") or {}
    cid = str(g.get("client_id", "")).strip()
    csec = str(g.get("client_secret", "")).strip()
    if not cid:
        cid = os.environ.get("NODEADLINE_GOOGLE_CLIENT_ID", "").strip()
    if not csec:
        csec = os.environ.get("NODEADLINE_GOOGLE_CLIENT_SECRET", "").strip()
    return (cid, csec)


_session_secret_memo: str | None = None


def session_secret() -> str:
    global _session_secret_memo
    s = str(oauth_section().get("session_secret", "")).strip()
    if not s:
        s = os.environ.get("NODEADLINE_SESSION_SECRET", "").strip()
    if s:
        return s
    if _session_secret_memo:
        return _session_secret_memo
    _session_secret_memo = _auto_session_secret()
    return _session_secret_memo


def _session_secret_file_paths() -> list[str]:
    """Порядок: каталог данных ноды (NODEADLINE_RUNTIME_DIR), затем рядом с конфигом (legacy)."""
    out: list[str] = []
    rd = os.environ.get("NODEADLINE_RUNTIME_DIR", "").strip()
    if rd:
        out.append(os.path.join(os.path.abspath(rd), ".nodeadline_session_secret"))
    cp = _config_path()
    if cp:
        base = os.path.dirname(os.path.abspath(cp))
        out.append(os.path.join(base, ".nodeadline_session_secret"))
    seen: set[str] = set()
    uniq: list[str] = []
    for p in out:
        ap = os.path.abspath(p)
        if ap not in seen:
            seen.add(ap)
            uniq.append(ap)
    return uniq


def _auto_session_secret() -> str:
    paths = _session_secret_file_paths()
    if not paths:
        return secrets.token_hex(32)

    found: str | None = None
    found_at: str | None = None
    for p in paths:
        try:
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    raw = f.read().strip()
                if len(raw) >= 16:
                    found = raw
                    found_at = p
                    break
        except OSError:
            pass

    if found:
        # Миграция: секрет был только рядом с nodeadline.json — копируем в runtime, чтобы переживать ребуты.
        if len(paths) >= 2 and found_at == paths[1] and not os.path.isfile(paths[0]):
            try:
                os.makedirs(os.path.dirname(paths[0]) or ".", exist_ok=True)
                tmp = paths[0] + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(found)
                os.replace(tmp, paths[0])
                os.chmod(paths[0], 0o600)
            except OSError:
                pass
        return found

    key = secrets.token_hex(32)
    for p in paths:
        try:
            d = os.path.dirname(p)
            if d:
                os.makedirs(d, exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(key)
            os.replace(tmp, p)
            try:
                os.chmod(p, 0o600)
            except OSError:
                pass
            return key
        except OSError:
            continue
    return key


def callback_base() -> str:
    b = str(oauth_section().get("callback_base", "https://nodeadline.online")).strip().rstrip("/")
    return b or "https://nodeadline.online"


def master_base_url() -> str:
    b = os.environ.get("NODEADLINE_MASTER_BASE_URL", "").strip().rstrip("/")
    if b:
        return b
    m = oauth_section().get("master") or {}
    u = str(m.get("base_url", "")).strip().rstrip("/")
    return u or callback_base()


def node_section() -> dict[str, Any]:
    return load_config().get("node") or {}


def namecheap_section() -> dict[str, Any]:
    return load_config().get("namecheap") or {}


def tracker_section() -> dict[str, Any]:
    return load_config().get("tracker") or {}


def tcp_probe_section() -> dict[str, Any]:
    return load_config().get("tcp_probe") or {}
