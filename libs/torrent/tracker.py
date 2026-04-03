"""
Master-side in-memory tracker registry + bencode announce response (compact).
"""
from __future__ import annotations

import os
import struct
import threading
import time
from typing import Any
from urllib.parse import parse_qs

_lock = threading.Lock()
# infohash hex -> list of {ip, port, peer_id, last_seen}
_peers: dict[str, list[dict[str, Any]]] = {}
_meta: dict[str, dict[str, Any]] = {}


def register_content(
    *,
    infohash_hex: str,
    owner_sub: str,
    share_id: str,
    file_count: int,
    total_bytes: int,
    snapshot_revision: int = 0,
) -> None:
    with _lock:
        _meta[infohash_hex.lower()] = {
            "owner_sub": owner_sub,
            "share_id": share_id,
            "file_count": file_count,
            "total_bytes": total_bytes,
            "snapshot_revision": snapshot_revision,
            "registered_at": time.time(),
        }


def list_content(owner_sub: str | None = None) -> list[dict[str, Any]]:
    with _lock:
        out = []
        for ih, m in _meta.items():
            if owner_sub and m.get("owner_sub") != owner_sub:
                continue
            out.append({"infohash": ih, **m, "peers": len(_peers.get(ih, []))})
        return out


def _bencode(x: Any) -> bytes:
    if isinstance(x, int):
        return b"i" + str(x).encode() + b"e"
    if isinstance(x, bytes):
        return str(len(x)).encode() + b":" + x
    if isinstance(x, str):
        b = x.encode()
        return str(len(b)).encode() + b":" + b
    if isinstance(x, list):
        return b"l" + b"".join(_bencode(i) for i in x) + b"e"
    if isinstance(x, dict):
        items = sorted(x.items(), key=lambda kv: kv[0].encode())
        return b"d" + b"".join(_bencode(k.encode()) + _bencode(v) for k, v in items) + b"e"
    raise TypeError(type(x))


def _info_hash_raw(info_hash: str | bytes) -> bytes | None:
    """20 байт из бинарного query или из 40-символьного hex; иначе None."""
    if isinstance(info_hash, bytes):
        return info_hash if len(info_hash) == 20 else None
    if not isinstance(info_hash, str):
        return None
    if len(info_hash) == 20:
        try:
            return info_hash.encode("latin-1")
        except UnicodeEncodeError:
            return None
    s = info_hash.strip().lower()
    if len(s) == 40 and all(c in "0123456789abcdef" for c in s):
        try:
            b = bytes.fromhex(s)
            return b if len(b) == 20 else None
        except ValueError:
            return None
    return None


def announce(query_string: str, remote_ip: str) -> bytes:
    qs = parse_qs(query_string)
    info_hash = (qs.get("info_hash") or [b""])[0]
    ih_raw = _info_hash_raw(info_hash)
    if ih_raw is None or len(ih_raw) != 20:
        return _bencode({"failure reason": "invalid info_hash"})
    ih_hex = ih_raw.hex()

    port_s = (qs.get("port") or ["0"])[0]
    try:
        port = int(port_s if isinstance(port_s, str) else port_s.decode())
    except Exception:
        port = 0
    peer_id = (qs.get("peer_id") or [b""])[0]
    if isinstance(peer_id, str):
        peer_id_b = peer_id.encode("latin-1", errors="replace")
    else:
        peer_id_b = peer_id or (b"-ND0001-" + os.urandom(12))

    ip = remote_ip.split("%")[0]
    if ip.startswith("::ffff:"):
        ip = ip[7:]

    with _lock:
        lst = _peers.setdefault(ih_hex, [])
        now = time.time()
        lst[:] = [p for p in lst if now - p["last_seen"] < 3600]
        lst.append({"ip": ip, "port": port, "peer_id": peer_id_b, "last_seen": now})
        peers_compact = b""
        for p in lst[:50]:
            try:
                parts = p["ip"].split(".")
                if len(parts) == 4:
                    peers_compact += bytes([int(x) for x in parts]) + struct.pack("!H", p["port"])
            except Exception:
                continue

    return _bencode({"interval": 600, "complete": 1, "incomplete": 0, "peers": peers_compact})
