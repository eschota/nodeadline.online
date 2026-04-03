"""Обновление nginx map: fqdn → WAN:порт для HTTPS reverse-proxy на VPS."""
from __future__ import annotations

import logging
import os
import subprocess

from libs.auth import dns_registry

log = logging.getLogger(__name__)

MAP_PATH = "/var/lib/nodeadline/nginx-user-backend.map"


def rebuild_map_and_reload() -> tuple[bool, str]:
    """
    Пересобирает map-файл из dns_bindings.json и выполняет nginx -s reload.
    Вызывается с мастера на том же хосте, что и nginx.
    """
    bindings = dns_registry.load_all_bindings()
    lines: list[str] = []
    for b in bindings.values():
        fqdn = str(b.get("fqdn") or "").strip()
        wan = str(b.get("wan_ipv4") or "").strip()
        try:
            pp = int(b.get("public_port") or 0)
        except (TypeError, ValueError):
            continue
        if not fqdn or not wan or pp < 1 or pp > 65535:
            continue
        lines.append(f"{fqdn} {wan}:{pp};")
    lines.sort()
    body = "\n".join(lines) + ("\n" if lines else "")
    try:
        os.makedirs(os.path.dirname(MAP_PATH), mode=0o755, exist_ok=True)
        tmp = MAP_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, MAP_PATH)
    except OSError as e:
        return False, str(e)[:500]

    r1 = subprocess.run(["nginx", "-t"], capture_output=True, text=True, timeout=30)
    if r1.returncode != 0:
        msg = (r1.stderr or r1.stdout or "nginx -t failed").strip()
        log.error("nginx -t failed: %s", msg)
        return False, msg[:500]

    r2 = subprocess.run(["nginx", "-s", "reload"], capture_output=True, text=True, timeout=30)
    if r2.returncode != 0:
        msg = (r2.stderr or r2.stdout or "reload failed").strip()
        log.error("nginx reload failed: %s", msg)
        return False, msg[:500]
    return True, ""
