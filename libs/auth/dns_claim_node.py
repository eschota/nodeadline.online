"""Авто-регистрация A-записи на мастере после OAuth (токен из /api/oauth/v1/redeem)."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from libs.auth import port_manager
from libs.protocol import RuntimeState

log = logging.getLogger(__name__)

_CLAIM_META = "dns_claim.json"
_INTERVAL_SEC = 75.0


def _meta_path(runtime_dir: str) -> str:
    return os.path.join(runtime_dir, _CLAIM_META)


def save_claim_context(
    runtime_dir: str,
    *,
    token: str,
    username: str,
    sub: str,
    email: str | None = None,
) -> None:
    if not token or not username:
        return
    os.makedirs(runtime_dir, mode=0o755, exist_ok=True)
    p = _meta_path(runtime_dir)
    data = {"token": token, "username": str(username).strip(), "sub": str(sub).strip()}
    if email:
        data["email"] = str(email).strip()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    st = port_manager.load_state(runtime_dir)
    if email:
        st.oauth_email = str(email).strip()
    st.oauth_bound_sub = str(sub).strip()
    st.dns_pipeline_stage = _compute_pipeline_stage(load_claim_context(runtime_dir), st, claiming=False)
    port_manager.save_state(runtime_dir, st)


def load_claim_context(runtime_dir: str) -> dict[str, str] | None:
    p = _meta_path(runtime_dir)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            return None
        tok = str(d.get("token") or "").strip()
        user = str(d.get("username") or "").strip()
        if not tok or not user:
            return None
        out = {"token": tok, "username": user, "sub": str(d.get("sub") or "")}
        if d.get("email"):
            out["email"] = str(d.get("email")).strip()
        return out
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _compute_pipeline_stage(
    ctx: dict[str, str] | None,
    st: RuntimeState,
    *,
    claiming: bool,
) -> str:
    if claiming:
        return "claiming"
    if not ctx:
        return "need_auth"
    wan = (st.wan_ip or "").strip()
    if not wan:
        return "need_wan"
    ds = str(st.dns_status or "idle")
    if ds == "no_public_port":
        return "need_public_port"
    if ds == "ok":
        return "ok"
    if ds == "error":
        return "error"
    if ds == "no_wan":
        return "need_wan"
    return "dns_pending"


def sync_dns_pipeline_stage(runtime_dir: str, *, claiming: bool = False) -> None:
    ctx = load_claim_context(runtime_dir)
    st = port_manager.load_state(runtime_dir)
    st.dns_pipeline_stage = _compute_pipeline_stage(ctx, st, claiming=claiming)
    port_manager.save_state(runtime_dir, st)


def _apply_dns_result(
    runtime_dir: str,
    *,
    ok: bool,
    fqdn: str | None,
    err: str | None,
    public_https_url: str | None = None,
) -> None:
    st = port_manager.load_state(runtime_dir)
    ctx = load_claim_context(runtime_dir)
    if ok and fqdn:
        st.dns_fqdn = fqdn
        st.dns_status = "ok"
        st.dns_error = None
        st.dns_claimed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        u = (public_https_url or "").strip()
        st.dns_public_https_url = u if u else None
    else:
        st.dns_status = "error"
        st.dns_error = (err or "claim_failed")[:500]
        st.dns_public_https_url = None
    st.dns_pipeline_stage = _compute_pipeline_stage(ctx, st, claiming=False)
    port_manager.save_state(runtime_dir, st)


def on_wan_updated(runtime_dir: str, old_wan: str, new_wan: str) -> None:
    new_wan = (new_wan or "").strip()
    if not new_wan:
        return
    if (old_wan or "").strip() == new_wan:
        return
    if not load_claim_context(runtime_dir):
        return
    try:
        from libs.auth import config

        master_url = config.master_base_url()
    except Exception:
        return

    def _run() -> None:
        try:
            try_claim_once(master_url, runtime_dir)
        except Exception:
            log.exception("dns_claim on_wan_updated")

    threading.Thread(target=_run, daemon=True, name="dns-claim-wan").start()


def try_claim_once(master_url: str, runtime_dir: str) -> dict[str, Any]:
    ctx = load_claim_context(runtime_dir)
    if not ctx:
        return {"ok": False, "reason": "no_token"}
    st = port_manager.load_state(runtime_dir)
    wan = (st.wan_ip or "").strip()
    if not wan:
        st.dns_status = "no_wan"
        st.dns_error = None
        st.dns_pipeline_stage = _compute_pipeline_stage(ctx, st, claiming=False)
        port_manager.save_state(runtime_dir, st)
        return {"ok": False, "reason": "no_wan"}
    if not st.public_port:
        st.dns_status = "no_public_port"
        st.dns_error = None
        st.dns_pipeline_stage = _compute_pipeline_stage(ctx, st, claiming=False)
        port_manager.save_state(runtime_dir, st)
        return {"ok": False, "reason": "no_public_port"}
    label = ctx["username"].lower().replace("_", "-")
    if not label:
        return {"ok": False, "reason": "no_label"}

    st2 = port_manager.load_state(runtime_dir)
    st2.dns_pipeline_stage = _compute_pipeline_stage(ctx, st2, claiming=True)
    port_manager.save_state(runtime_dir, st2)

    body = json.dumps(
        {"label": label, "wan_ipv4": wan, "public_port": int(st.public_port)},
        ensure_ascii=False,
    ).encode("utf-8")
    url = f"{master_url.rstrip('/')}/api/dns/v1/claim-subdomain"
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Authorization", f"Bearer {ctx['token']}")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode()
            data = json.loads(raw)
        except Exception:
            data = {"error": str(e.reason or e)}
        err = str(data.get("error") or data.get("detail") or "http_error")
        _apply_dns_result(runtime_dir, ok=False, fqdn=None, err=err)
        return {"ok": False, "error": err}
    except Exception as e:
        _apply_dns_result(runtime_dir, ok=False, fqdn=None, err=str(e)[:300])
        return {"ok": False, "error": str(e)[:300]}
    if not data.get("ok"):
        err = str(data.get("error") or data.get("detail") or "claim_failed")
        _apply_dns_result(runtime_dir, ok=False, fqdn=None, err=err)
        return {"ok": False, "error": err}
    fqdn = str(data.get("fqdn") or "").strip()
    ph = str(data.get("public_https_url") or "").strip()
    _apply_dns_result(
        runtime_dir,
        ok=True,
        fqdn=fqdn or None,
        err=None,
        public_https_url=ph or None,
    )
    return {"ok": True, "fqdn": fqdn}


def start_dns_claim_loop(master_url: str, runtime_dir: str) -> tuple[threading.Thread, threading.Event]:
    stop = threading.Event()

    def _run():
        time.sleep(2.0)
        while not stop.is_set():
            try:
                try_claim_once(master_url, runtime_dir)
            except Exception:
                log.exception("dns_claim loop")
            stop.wait(_INTERVAL_SEC)

    t = threading.Thread(target=_run, daemon=True, name="dns-claim")
    t.start()
    return t, stop
