from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from typing import Any

from libs.torrent import snapshot

log = logging.getLogger(__name__)

_states: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()
_announce_lock = threading.Lock()
_announce_stats: dict[str, Any] = {"ok": 0, "fail": 0, "last_ok_at": None}


def get_state(share_id: str) -> dict[str, Any]:
    with _lock:
        return dict(_states.get(share_id, {}))


def all_states() -> list[dict[str, Any]]:
    with _lock:
        return [dict(v) for v in _states.values()]


def announce_stats() -> dict[str, Any]:
    with _announce_lock:
        return dict(_announce_stats)


def register_on_master(
    *,
    master_url: str,
    infohash_hex: str,
    owner_sub: str,
    share_id: str,
    file_count: int,
    total_bytes: int,
    snapshot_revision: int,
) -> dict[str, Any]:
    url = f"{master_url.rstrip('/')}/api/torrent/v1/register"
    body = json.dumps({
        "infohash": infohash_hex,
        "owner_sub": owner_sub,
        "share_id": share_id,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "snapshot_revision": snapshot_revision,
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log.error("register failed: %s", e)
        return {"error": str(e)}


def announce(
    *,
    announce_url: str,
    infohash_hex: str,
    port: int,
    peer_id: bytes | None = None,
) -> bool:
    ih = snapshot.infohash_binary_from_hex(infohash_hex)
    pid = peer_id or (b"-NDv2-" + os.urandom(12))
    q = "&".join([
        "info_hash=" + urllib.parse.quote(ih.decode("latin-1"), safe=""),
        "peer_id=" + urllib.parse.quote(pid.decode("latin-1", errors="replace"), safe=""),
        f"port={port}",
        "uploaded=0",
        "downloaded=0",
        "left=0",
        "compact=1",
    ])
    url = f"{announce_url}?{q}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        with _announce_lock:
            _announce_stats["ok"] = int(_announce_stats.get("ok", 0)) + 1
            _announce_stats["last_ok_at"] = time.time()
        return True
    except Exception as e:
        log.warning("announce failed: %s", e)
        with _announce_lock:
            _announce_stats["fail"] = int(_announce_stats.get("fail", 0)) + 1
        return False


def publish_and_register(
    *,
    share_id: str,
    owner_sub: str,
    master_url: str,
    announce_url: str,
    listen_port: int,
) -> dict[str, Any]:
    from libs.shares import registry as reg

    sid, ih, rev, man_raw = snapshot.publish_snapshot(share_id=share_id, owner_sub=owner_sub)
    manifest = json.loads(man_raw)
    total = sum(f["size"] for f in manifest)
    r = register_on_master(
        master_url=master_url,
        infohash_hex=ih,
        owner_sub=owner_sub,
        share_id=share_id,
        file_count=len(manifest),
        total_bytes=total,
        snapshot_revision=rev,
    )
    announce(announce_url=announce_url, infohash_hex=ih, port=listen_port)
    with _lock:
        _states[share_id] = {
            "share_id": share_id,
            "infohash": ih,
            "snapshot_id": sid,
            "revision": rev,
            "registered": "error" not in r,
            "last_announce": time.time(),
        }
    return {"snapshot_id": sid, "infohash": ih, "revision": rev, "register": r}


def publish_async(**kw) -> threading.Thread:
    t = threading.Thread(target=publish_and_register, kwargs=kw, daemon=True)
    t.start()
    return t
