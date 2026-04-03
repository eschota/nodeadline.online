"""
Авто-регистрация субдомена на мастере для пользователей без локальной ноды.

DNS: A(label) → ingress (как у claim ноды). Трафик: nginx map → backend на самом VPS
(по умолчанию 127.0.0.1:PORT мастера). Когда пользователь поднимает ноду и делает claim,
claim-subdomain перезаписывает привязку на WAN:порт ноды.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from libs.auth import config, dns_registry, nginx_ingress, users
from libs.dns.namecheap_api import client_from_config, NamecheapError

log = logging.getLogger(__name__)


def hosted_backend() -> tuple[str, int]:
    host = os.environ.get("NODEADLINE_HOSTED_BACKEND_HOST", "127.0.0.1").strip() or "127.0.0.1"
    p = os.environ.get("NODEADLINE_HOSTED_BACKEND_PORT", "").strip()
    if p.isdigit():
        port = int(p)
    else:
        port = int(os.environ.get("PORT", "8765"))
    return host, port


def _is_node_binding(binding: dict[str, Any] | None) -> bool:
    """Привязка к реальной ноде (не хост на мастере)."""
    if not binding:
        return False
    wan = str(binding.get("wan_ipv4") or "").strip()
    if not wan:
        return False
    if wan in ("127.0.0.1", "::1"):
        return False
    return True


def is_hosted_binding(binding: dict[str, Any] | None) -> bool:
    """Трафик идёт на backend мастера (ingress map), нода ещё не забрала WAN:порт."""
    if not binding:
        return False
    if _is_node_binding(binding):
        return False
    host, port = hosted_backend()
    return (
        str(binding.get("wan_ipv4") or "").strip() == host
        and int(binding.get("public_port") or 0) == port
    )


def ensure_hosted_subdomain_after_oauth(sub: str) -> dict[str, Any]:
    """
    Вызывать после users.upsert_user при успешном OAuth на мастере.
    Не бросает исключений наружу — ошибки DNS/nginx только в лог.
    """
    sub = str(sub).strip()
    out: dict[str, Any] = {"ok": False}
    if not sub:
        out["skipped"] = "no_sub"
        return out
    u = users.get_user_by_sub(sub)
    if not u:
        out["skipped"] = "no_user"
        return out
    username = str(u.username or "").strip()
    if not username:
        out["skipped"] = "no_username"
        return out
    label = username.lower().replace("_", "-")
    prev = dns_registry.get_binding(sub)
    if _is_node_binding(prev):
        out["ok"] = True
        out["skipped"] = "node_active"
        out["fqdn"] = str(prev.get("fqdn") or "").strip()
        return out

    nc_sec = config.namecheap_section()
    ingress = str(nc_sec.get("server_ipv4") or "").strip()
    nc_client = client_from_config(config.load_config())
    apex = str(nc_sec.get("apex_domain") or "nodeadline.online")
    fqdn = f"{label}.{apex}"
    host, port = hosted_backend()
    prev_ing = str(prev.get("ingress_ipv4") or "").strip() if prev else ""
    unchanged = bool(
        prev
        and str(prev.get("wan_ipv4") or "").strip() == host
        and int(prev.get("public_port") or 0) == port
        and str(prev.get("fqdn") or "").strip() == fqdn
        and prev_ing == ingress
    )
    if not nc_client or not ingress:
        log.warning("hosted subdomain skipped: namecheap or server_ipv4 not configured")
        out["skipped"] = "dns_not_configured"
        return out
    if not unchanged:
        try:
            nc_client.set_hosts_merged(domain=apex, subdomain=label, address=ingress, ttl=300)
        except NamecheapError as e:
            log.error("hosted subdomain Namecheap: %s", e)
            out["error"] = str(e)[:300]
            return out
    dns_registry.upsert_binding(
        sub=sub,
        username=username,
        email=str(u.email or ""),
        wan_ipv4=host,
        fqdn=fqdn,
        public_port=port,
        ingress_ipv4=ingress,
    )
    ok_ngx, ngx_err = nginx_ingress.rebuild_map_and_reload()
    if not ok_ngx:
        log.error("hosted subdomain nginx: %s", ngx_err)
        out["error"] = f"nginx: {ngx_err[:200]}"
        return out
    out["ok"] = True
    out["fqdn"] = fqdn
    out["public_https_url"] = f"https://{fqdn}/"
    out["unchanged"] = unchanged
    out["hosted"] = True
    log.info("hosted subdomain ready sub=%s fqdn=%s backend=%s:%s", sub, fqdn, host, port)
    return out
