#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
================================================================================
ТЗ / ЛАБОРАТОРНЫЙ СТЕНД: UPnP remap «другой внешний порт» (Windows / Linux)
================================================================================
Проблема (исправлено в проде в libs/auth/port_manager.py):
  Кнопка «Другой внешний порт» вызывала fallback AddPortMapping с external=0,
  что на IGD даёт внешний порт = внутреннему (1:1). Пользователь снова видел
  тот же порт (напр. 37651), хотя ожидал другой; на роутере могло не быть
  нового запроса, если маппинг уже совпадал.

Ожидаемое поведение remap:
  1) DeletePortMapping(предыдущий внешний), если был.
  2) Перебор кандидатов внешних портов (случайные 22000–52000), НЕ равных
     внутреннему и НЕ равных предыдущему внешнему.
  3) Никогда не использовать «внешний = внутренний» как финальный fallback.
  4) Дополнительно — несколько случайных внешних портов, если список исчерпан.
  5) Опционально: проверка доступности через мастер GET .../api/public/tcp-probe
     (если не нужна — флаг --no-probe или env NODEADLINE_UPNP_REMAP_REQUIRE_PROBE=0).

Зависимости:
  pip install miniupnpc

Переменные окружения (как в ноде):
  NODEADLINE_UPNP_LOCAL_IP   — явный LAN IP для SSDP/multicastif (Wi‑Fi/VPN).
  NODEADLINE_UPNP_REMAP_REQUIRE_PROBE=0 — успех только по AddPortMapping, без probe.

Примеры:
  python upnp_remap_standalone.py --internal 37651 --previous-external 37651
  python upnp_remap_standalone.py --internal 37651 --master https://master.example.com
  python upnp_remap_standalone.py --internal 37651 --no-probe

Синхронизация: при изменении логики UPnP в проде обновляйте и этот файл
(или удалите и тестируйте из репозитория через import из libs — но для
чистого «одного файла на Windows» держим копию здесь).
================================================================================
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import sys
import time
import urllib.parse
import urllib.request
from typing import Any


def _guess_local_ipv4() -> str | None:
    s: socket.socket | None = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1.5)
        s.connect(("8.8.8.8", 53))
        ip = s.getsockname()[0]
        if ip and not ip.startswith("127."):
            return str(ip)
    except OSError:
        return None
    finally:
        if s is not None:
            try:
                s.close()
            except OSError:
                pass
    return None


def _upnp_discover_and_connect() -> tuple[Any, dict[str, Any]]:
    import miniupnpc  # type: ignore

    meta: dict[str, Any] = {}
    env_ip = os.environ.get("NODEADLINE_UPNP_LOCAL_IP", "").strip()
    local_ip = env_ip or _guess_local_ipv4()
    meta["local_ip_for_multicast"] = local_ip
    last_err: str | None = None
    for attempt in range(3):
        u = miniupnpc.UPnP()
        u.discoverdelay = 10000 if sys.platform == "win32" else 5500
        if local_ip:
            try:
                u.multicastif = local_ip
                meta["multicastif_set"] = local_ip
            except (AttributeError, TypeError):
                meta["multicastif_set"] = None
        try:
            ndev = int(u.discover())
        except Exception as e:
            last_err = str(e)[:300]
            time.sleep(0.45 * (attempt + 1))
            continue
        meta["devices_found"] = ndev
        if ndev <= 0:
            last_err = "no_ssdp_devices"
            time.sleep(0.45 * (attempt + 1))
            continue
        try:
            u.selectigd()
        except Exception as e:
            last_err = str(e)[:300]
            time.sleep(0.45 * (attempt + 1))
            continue
        meta["lanaddr_igd"] = getattr(u, "lanaddr", None)
        return u, meta
    raise RuntimeError(last_err or "upnp_igd_not_found")


def _upnp_discover() -> Any:
    u, _ = _upnp_discover_and_connect()
    return u


def try_delete_portmapping(external_port: int) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False}
    try:
        u = _upnp_discover()
        ok = u.deleteportmapping(int(external_port), "TCP")
        if ok is False or ok == 0:
            out["error"] = "deleteportmapping_rejected"
            return out
        out["ok"] = True
    except Exception as e:
        out["error"] = str(e)[:240]
    return out


def try_upnp_mapping(internal_port: int, external_port: int = 0) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "failed", "external_port": None, "wan_ip": None}
    try:
        u, disc_meta = _upnp_discover_and_connect()
        wan = u.externalipaddress()
        ext = int(external_port) if external_port else int(internal_port)
        env_lan = os.environ.get("NODEADLINE_UPNP_LOCAL_IP", "").strip()
        lan_host = env_lan or _guess_local_ipv4() or str(getattr(u, "lanaddr", "") or "").strip()
        if not lan_host:
            result["error"] = "no_lan_ip"
            result["diag"] = disc_meta
            return result
        desc = "nodeadline-standalone"
        ok = u.addportmapping(ext, "TCP", lan_host, int(internal_port), desc, "")
        if ok is False or ok == 0:
            result["error"] = "addportmapping_rejected_by_router"
            result["diag"] = {**disc_meta, "lan_used": lan_host, "external_ip": str(wan)}
            return result
        post_verify: str | None = None
        chk = None
        for _ in range(4):
            try:
                chk = u.getspecificportmapping(ext, "TCP")
                if chk is not None:
                    break
            except Exception as ver_e:
                post_verify = str(ver_e)[:160]
            time.sleep(0.12)
        if chk is None:
            post_verify = (post_verify or "") + " · mapping list delayed or empty"
        result["status"] = "mapped"
        result["external_port"] = ext
        result["wan_ip"] = str(wan)
        result["diag"] = {
            **disc_meta,
            "lan_used": lan_host,
            "lanaddr_igd": getattr(u, "lanaddr", None),
            "external_ip": str(wan),
            "post_add_verify": post_verify or ("ok" if chk is not None else "pending"),
        }
    except Exception as e:
        result["error"] = str(e)[:300]
    return result


def default_external_port_candidates(
    internal_port: int,
    count: int = 14,
    *,
    also_exclude: set[int] | None = None,
) -> list[int]:
    seen: set[int] = {int(internal_port)}
    if also_exclude:
        seen |= {int(x) for x in also_exclude if 1 <= int(x) <= 65535}
    out: list[int] = []
    for _ in range(count * 8):
        if len(out) >= count:
            break
        p = random.randint(22000, 52000)
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _remap_require_probe() -> bool:
    return os.environ.get("NODEADLINE_UPNP_REMAP_REQUIRE_PROBE", "1").strip() != "0"


def probe_via_master(master_url: str, host: str, port: int, timeout: int = 12) -> dict[str, Any]:
    q = urllib.parse.urlencode({"host": host, "port": str(port)})
    url = f"{master_url.rstrip('/')}/api/public/tcp-probe?{q}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"ok": False, "reachable": False, "error": str(e)[:200]}


def try_upnp_remap_external(
    internal_port: int,
    *,
    previous_external: int | None,
    candidates: list[int],
    master_url: str,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    prev = int(previous_external) if previous_external else None
    need_probe = _remap_require_probe()

    if prev:
        dr = try_delete_portmapping(prev)
        attempts.append({"step": "delete_previous", "port": prev, "delete": dr})

    def _finish_ok(r: dict[str, Any], reachable: bool) -> dict[str, Any]:
        o = dict(r)
        o["reachable"] = reachable
        o["attempts"] = attempts
        return o

    for ext in candidates:
        if ext < 1 or ext > 65535:
            continue
        if ext == int(internal_port):
            continue
        if prev is not None and ext == prev:
            continue
        r = try_upnp_mapping(internal_port, external_port=ext)
        att: dict[str, Any] = {
            "external_port": ext,
            "upnp_status": r.get("status"),
            "wan_ip": r.get("wan_ip"),
            "upnp_error": r.get("error"),
            "diag": r.get("diag"),
        }
        if r.get("status") != "mapped":
            attempts.append(att)
            continue
        ext_p = int(r["external_port"])
        wan = str(r.get("wan_ip") or "")
        pr: dict[str, Any] = {}
        if need_probe and master_url and wan:
            pr = probe_via_master(master_url, wan, ext_p)
        att["probe"] = pr
        att["reachable"] = bool(pr.get("reachable")) if need_probe else False
        attempts.append(att)
        if not need_probe:
            o = _finish_ok(r, False)
            o["accepted_without_probe"] = True
            return o
        reachable = bool(pr.get("reachable"))
        if reachable:
            return _finish_ok(r, True)
        try_delete_portmapping(ext_p)
        attempts.append({"step": "rollback_mapping", "port": ext_p})

    for _ in range(10):
        fb_ext = random.randint(22000, 52000)
        if fb_ext == int(internal_port) or (prev is not None and fb_ext == prev):
            continue
        fb = try_upnp_mapping(internal_port, external_port=fb_ext)
        attempts.append({"step": "fallback_random_external", "tried": fb_ext, "result": fb})
        if fb.get("status") != "mapped":
            continue
        ext_p = int(fb["external_port"])
        wan = str(fb.get("wan_ip") or "")
        pr: dict[str, Any] = {}
        if need_probe and master_url and wan:
            pr = probe_via_master(master_url, wan, ext_p)
        attempts[-1]["probe"] = pr
        if not need_probe:
            o = _finish_ok(fb, False)
            o["accepted_without_probe"] = True
            return o
        reachable = bool(pr.get("reachable"))
        if reachable:
            return _finish_ok(fb, True)
        try_delete_portmapping(ext_p)
        attempts.append({"step": "rollback_fallback", "port": ext_p})

    return {
        "status": "failed",
        "external_port": None,
        "wan_ip": None,
        "error": "upnp_remap_exhausted",
        "attempts": attempts,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="UPnP remap standalone (see module docstring)")
    ap.add_argument("--internal", type=int, required=True, help="локальный порт сервиса")
    ap.add_argument("--previous-external", type=int, default=0, help="старый внешний порт для DeletePortMapping")
    ap.add_argument("--master", default="", help="базовый URL мастера для tcp-probe")
    ap.add_argument("--no-probe", action="store_true", help="успех при успешном AddPortMapping (как env REQUIRE_PROBE=0)")
    args = ap.parse_args()
    if args.no_probe:
        os.environ["NODEADLINE_UPNP_REMAP_REQUIRE_PROBE"] = "0"
    prev = int(args.previous_external) if args.previous_external else None
    excl: set[int] = set()
    if prev:
        excl.add(prev)
    cands = default_external_port_candidates(args.internal, also_exclude=excl)
    res = try_upnp_remap_external(
        args.internal,
        previous_external=prev,
        candidates=cands,
        master_url=(args.master or "").strip(),
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("status") == "mapped" or res.get("external_port") else 1


if __name__ == "__main__":
    raise SystemExit(main())
