"""BitTorrent download for site bundle (libtorrent), continuous session."""

from __future__ import annotations

import logging
import os
import threading
import time
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

_lt = None
_session: Any = None
_lock = threading.Lock()
_last_stats: dict[str, Any] = {"session": "off", "last_error": ""}


def _import_lt():
    global _lt
    if _lt is None:
        try:
            import libtorrent as lt
        except ImportError as e:
            raise ImportError(
                "python-libtorrent is optional; install a matching wheel for your OS or rely on HTTPS site sync"
            ) from e
        _lt = lt
    return _lt


def get_session():
    """Single libtorrent session (listen on ephemeral BT ports)."""
    global _session
    lt = _import_lt()
    with _lock:
        if _session is None:
            _session = lt.session(
                {
                    "listen_interfaces": "0.0.0.0:0",
                    "enable_dht": True,
                    "enable_lsd": True,
                }
            )
            _session.listen_on(6881, 6999)
            _last_stats["session"] = "on"
            log.info("libtorrent session started")
        return _session


def _pop_alerts(ses, max_rounds: int = 500) -> None:
    lt = _import_lt()
    for _ in range(max_rounds):
        if not ses.pop_alerts():
            break


def download_torrent_content(
    *,
    magnet: str,
    torrent_url: str,
    download_dir: str,
    timeout_sec: float = 900.0,
) -> str:
    """
    Download single-file torrent to download_dir; returns path to the downloaded file.
    Prefer magnet; fallback fetch .torrent from torrent_url if magnet empty.
    """
    lt = _import_lt()
    ses = get_session()
    os.makedirs(download_dir, mode=0o755, exist_ok=True)
    if magnet.strip():
        params = lt.parse_magnet_uri(magnet.strip())
        params.save_path = download_dir
        h = ses.add_torrent(params)
    elif torrent_url.strip():
        tpath = os.path.join(download_dir, "_meta.torrent")
        req = urllib.request.Request(torrent_url.strip(), headers={"User-Agent": "nodeadline-node/2"})
        with urllib.request.urlopen(req, timeout=60) as r:
            with open(tpath, "wb") as f:
                f.write(r.read())
        ti = lt.torrent_info(lt.bdecode(open(tpath, "rb").read()))
        h = ses.add_torrent({"ti": ti, "save_path": download_dir})
    else:
        raise ValueError("magnet or torrent_url required")

    deadline = time.time() + timeout_sec
    try:
        while time.time() < deadline:
            _pop_alerts(ses)
            st = h.status()
            fin = {lt.torrent_status.seeding}
            if hasattr(lt.torrent_status, "finished"):
                fin.add(lt.torrent_status.finished)
            if st.progress >= 0.999 or st.state in fin:
                break
            if st.errc:
                msg = str(st.errc.message())
                _last_stats["last_error"] = msg
                raise RuntimeError(f"torrent error: {msg}")
            time.sleep(0.15)
        else:
            raise TimeoutError("torrent download timeout")

        _pop_alerts(ses)
        path = _find_tar_gz(download_dir)
        return path
    finally:
        try:
            ses.remove_torrent(h)
        except Exception:
            pass


def _find_tar_gz(root: str) -> str:
    found: list[str] = []
    for dirpath, _, names in os.walk(root):
        for n in names:
            if n.endswith(".tar.gz"):
                found.append(os.path.join(dirpath, n))
    if not found:
        raise RuntimeError("no .tar.gz after torrent download")
    found.sort()
    return found[0]


def session_stats() -> dict[str, Any]:
    with _lock:
        out = dict(_last_stats)
        if _session is None:
            try:
                _import_lt()
            except ImportError:
                out["libtorrent"] = "unavailable"
            return out
    try:
        _import_lt()
        ses = _session
        st = ses.status()
        out["dht_nodes"] = st.dht_nodes
        out["has_session"] = True
    except ImportError:
        out["libtorrent"] = "unavailable"
    except Exception as e:
        out["session_error"] = str(e)[:200]
    return out