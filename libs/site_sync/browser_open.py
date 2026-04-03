"""Open local static site (/site/index.html) when channel revision or installer build advances."""

from __future__ import annotations

import json
import logging
import os
import threading
import webbrowser

import libs.auth.port_manager as port_manager

log = logging.getLogger(__name__)
_open_lock = threading.Lock()


def _active_site_root(runtime_dir: str) -> str | None:
    """Same logic as channel.get_active_site_root — avoid importing channel (circular)."""
    p = os.path.join(runtime_dir, "site", "active.json")
    try:
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
        r = str(j.get("root", "")).strip()
        return r if r and os.path.isdir(r) else None
    except OSError:
        return None
    except (json.JSONDecodeError, TypeError):
        return None


def _load_local_revision(runtime_dir: str) -> int:
    p = os.path.join(runtime_dir, "site", "channel_state.json")
    try:
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
        return int(j.get("revision", 0))
    except OSError:
        return 0
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0

_STATE = "browser_open_state.json"
_LEGACY_REVISION = "browser_open_revision.txt"


def _state_path(runtime_dir: str) -> str:
    return os.path.join(runtime_dir, "site", _STATE)


def _legacy_revision_path(runtime_dir: str) -> str:
    return os.path.join(runtime_dir, "site", _LEGACY_REVISION)


def _read_installer_build(runtime_dir: str) -> str:
    p = os.path.join(runtime_dir, "installer_build.txt")
    try:
        with open(p, encoding="utf-8") as f:
            s = f.read().strip()
            return s if s else ""
    except OSError:
        return ""


def _parse_build(s: str) -> int:
    s = (s or "").strip()
    if not s:
        return 0
    try:
        return int(s, 10)
    except ValueError:
        return 0


def _load_open_state(runtime_dir: str) -> tuple[int, str]:
    p = _state_path(runtime_dir)
    try:
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
        return int(j.get("opened_revision", 0)), str(j.get("opened_installer_build", "") or "")
    except OSError:
        pass
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    # migrate from legacy single-file revision marker
    leg = _legacy_revision_path(runtime_dir)
    try:
        with open(leg, encoding="utf-8") as f:
            r = int(f.read().strip())
    except OSError:
        prev = 0
    except (TypeError, ValueError):
        prev = 0
    else:
        prev = r
    return prev, ""


def _save_open_state(runtime_dir: str, opened_revision: int, opened_installer_build: str) -> None:
    os.makedirs(os.path.join(runtime_dir, "site"), mode=0o755, exist_ok=True)
    p = _state_path(runtime_dir)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            {
                "opened_revision": opened_revision,
                "opened_installer_build": opened_installer_build,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")
    os.replace(tmp, p)


def _site_landing_url(port: int) -> str:
    """Explicit index.html so the browser always loads the synced static HTML, not the Python dashboard at /."""
    return f"http://127.0.0.1:{port}/site/index.html?local=1"


def maybe_open_local_site(runtime_dir: str) -> None:
    """If site bundle is ready and revision or installer build advanced since last open, open /site/index.html."""
    with _open_lock:
        if not _active_site_root(runtime_dir):
            return
        cur_rev = _load_local_revision(runtime_dir)
        cur_ib = _read_installer_build(runtime_dir)
        or_rev, or_ib = _load_open_state(runtime_dir)
        need = cur_rev > or_rev
        if not need and cur_ib:
            need = _parse_build(cur_ib) > _parse_build(or_ib)
        if not need:
            return
        st = port_manager.load_state(runtime_dir)
        port = int(st.listen_port or 0)
        if port <= 0:
            try:
                port = int(os.environ.get("PORT", "0") or 0)
            except ValueError:
                port = 0
        if port <= 0:
            log.warning("browser_open: no listen port")
            return
        url = _site_landing_url(port)
        try:
            webbrowser.open(url)
            log.info("opened browser for local site -> %s (rev=%s ib=%s)", url, cur_rev, cur_ib or "—")
        except Exception as e:
            log.warning("browser_open failed: %s", e)
            return
        _save_open_state(runtime_dir, cur_rev, cur_ib or or_ib)


def open_local_site_after_new_revision(runtime_dir: str, revision: int) -> None:
    """Backward-compatible name: channel calls this after applying a bundle; logic is unified."""
    _ = revision
    maybe_open_local_site(runtime_dir)
