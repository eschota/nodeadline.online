"""
Port selection, persistence, UPnP, WAN probe via master.
"""
from __future__ import annotations

import json
import os
import random
import socket
import threading
import time
import urllib.parse
import urllib.request
from typing import Any

from libs.protocol import RuntimeState

_lock = threading.Lock()


def _guess_local_ipv4() -> str | None:
    """IP интерфейса по умолчанию (маршрут в интернет). На Windows/VPN важнее, чем u.lanaddr."""
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
    """
    SSDP/IGD: на ПК с несколькими адаптерами (Wi‑Fi, VPN, Hyper‑V) без multicastif
    discover() часто не видит TP‑Link — задаём интерфейс по NODEADLINE_UPNP_LOCAL_IP или авто.
    """
    import sys
    import time

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
            last_err = "no_ssdp_devices (проверьте сеть/VPN, брандмауэр Windows для «частной сети»)"
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


def _can_bind(host: str, port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def pick_port(
    host: str,
    preferred: int | None,
    candidates: list[int],
) -> int:
    seen: set[int] = set()
    ordered: list[int] = []

    def add(p: int) -> None:
        if 1 <= p <= 65535 and p not in seen:
            seen.add(p)
            ordered.append(p)

    env_port = os.environ.get("NODEADLINE_LOCAL_PORT", "").strip()
    if env_port:
        try:
            add(int(env_port))
        except ValueError:
            pass
    env_port2 = os.environ.get("PORT", "").strip()
    if env_port2:
        try:
            add(int(env_port2))
        except ValueError:
            pass
    if preferred and preferred > 0:
        add(preferred)
    for p in candidates:
        add(p)

    for p in ordered:
        if _can_bind(host, p):
            return p

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _state_path(runtime_dir: str) -> str:
    return os.path.join(runtime_dir, "runtime_state.json")


def load_state(runtime_dir: str) -> RuntimeState:
    p = _state_path(runtime_dir)
    with _lock:
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return RuntimeState.from_dict(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
    return RuntimeState()


def save_state(runtime_dir: str, state: RuntimeState) -> None:
    p = _state_path(runtime_dir)
    old_wan = ""
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                old_wan = (RuntimeState.from_dict(json.load(f)).wan_ip or "").strip()
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    with _lock:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    new_wan = (state.wan_ip or "").strip()
    if new_wan and new_wan != old_wan:
        try:
            from libs.auth import dns_claim_node

            dns_claim_node.on_wan_updated(runtime_dir, old_wan, new_wan)
        except Exception:
            pass


def _upnp_discover():
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
        desc = "nodeadline"
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
            post_verify = (post_verify or "") + " · список на роутере пока пуст/не читается (часто TP‑Link обновляет с задержкой)"
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
        try:
            si = getattr(u, "statusinfo", None)
            if callable(si):
                x = si()
                if x:
                    result["diag"]["igd_status"] = str(x)[:300]
        except Exception:
            pass
    except Exception as e:
        result["error"] = str(e)[:300]
    return result


def default_external_port_candidates(
    internal_port: int,
    count: int = 14,
    *,
    also_exclude: set[int] | None = None,
) -> list[int]:
    """Случайные внешние порты 22000–52000; исключаем внутренний и предыдущий внешний (чтобы не «возвращаться» на старый)."""
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


def try_upnp_remap_external(
    internal_port: int,
    *,
    previous_external: int | None,
    candidates: list[int],
    master_url: str,
) -> dict[str, Any]:
    """
    Пробует внешние порты по очереди: UPnP → TCP-probe с мастера.
    НИКОГДА не использует fallback «внешний = внутренний» (он давал тот же порт, что уже был при 1:1).
    Если NODEADLINE_UPNP_REMAP_REQUIRE_PROBE=0 — достаточно успешного AddPortMapping (роутер покажет запись даже при «сером» NAT).
    """
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


def probe_via_master(master_url: str, host: str, port: int, timeout: int = 12) -> dict[str, Any]:
    q = urllib.parse.urlencode({"host": host, "port": str(port)})
    url = f"{master_url.rstrip('/')}/api/public/tcp-probe?{q}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode())
            return raw
    except Exception as e:
        return {"ok": False, "reachable": False, "error": str(e)[:200]}


def run_network_bootstrap(
    *,
    runtime_dir: str,
    listen_host: str,
    listen_port: int,
    expose_lan: bool,
    auto_upnp: bool,
    auto_probe: bool,
    master_url: str,
) -> RuntimeState:
    state = load_state(runtime_dir)
    state.listen_host = listen_host
    state.listen_port = listen_port
    state.expose_lan = expose_lan
    state.network_mode = "lan" if expose_lan else "local"
    state.pid = os.getpid()

    if auto_upnp:
        up = try_upnp_mapping(listen_port)
        state.upnp_status = up.get("status", "failed")
        state.upnp_last_error = up.get("error")
        if up.get("external_port"):
            state.public_port = int(up["external_port"])
        if up.get("wan_ip"):
            state.wan_ip = str(up["wan_ip"])
    else:
        state.upnp_status = "skipped"

    if auto_probe and master_url and state.wan_ip and state.public_port:
        pr = probe_via_master(master_url, state.wan_ip, int(state.public_port))
        state.public_probe_status = "reachable" if pr.get("reachable") else "unreachable"
        state.last_verified_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    elif auto_probe:
        state.public_probe_status = "unknown"

    save_state(runtime_dir, state)
    return state
