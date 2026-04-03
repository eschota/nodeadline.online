"""Site bundle sync: BitTorrent (libtorrent) + web seed, или HTTPS; проверка SHA256."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tarfile
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from libs.site_sync.browser_open import open_local_site_after_new_revision
from libs.site_sync.torrent_sync import download_torrent_content

log = logging.getLogger(__name__)

SYNC_INTERVAL_SEC = 30.0
# Не засорять лог каждые 30 с при офлайне / DNS (Windows 11001 = getaddrinfo failed).
_FETCH_WARN_INTERVAL_SEC = 300.0
_last_fetch_warn_mono: float = 0.0


def _is_transient_fetch_error(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.URLError) and exc.reason is not None:
        return _is_transient_fetch_error(exc.reason)
    if isinstance(exc, socket.gaierror):
        return True
    if isinstance(exc, OSError):
        e = exc.errno
        if e in (11001, 11002, 11003):
            return True
    s = str(exc).lower()
    return "getaddrinfo" in s or "name or service not known" in s or "temporary failure" in s


def fetch_site_channel(master_base: str) -> dict[str, Any] | None:
    global _last_fetch_warn_mono
    base = master_base.rstrip("/")
    url = f"{base}/site_channel.json?cb={int(time.time() * 1000)}"
    req = urllib.request.Request(
        url,
        headers={"Cache-Control": "no-cache", "User-Agent": "nodeadline-node/2-site-sync"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.loads(r.read().decode())
        _last_fetch_warn_mono = 0.0
        return out
    except Exception as e:
        now = time.monotonic()
        if now - _last_fetch_warn_mono >= _FETCH_WARN_INTERVAL_SEC:
            _last_fetch_warn_mono = now
            if _is_transient_fetch_error(e):
                # English only: Windows consoles often use legacy code pages and mangle UTF-8 log lines.
                log.warning(
                    "site_channel: master unreachable (network/DNS); retry every %ss. %s "
                    "(hint: check internet, DNS, or set NODEADLINE_MASTER_BASE_URL)",
                    int(SYNC_INTERVAL_SEC),
                    e,
                )
            else:
                log.warning("site_channel fetch failed: %s", e)
        else:
            log.debug("site_channel fetch failed: %s", e)
        return None


def _site_root(runtime_dir: str) -> str:
    return os.path.join(runtime_dir, "site")


def _state_path(runtime_dir: str) -> str:
    return os.path.join(_site_root(runtime_dir), "channel_state.json")


def _active_root_from_state(runtime_dir: str) -> str | None:
    p = os.path.join(_site_root(runtime_dir), "active.json")
    try:
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
        r = str(j.get("root", "")).strip()
        return r if r and os.path.isdir(r) else None
    except OSError:
        return None
    except (json.JSONDecodeError, TypeError):
        return None


def _resolved_site_root(runtime_dir: str) -> tuple[str | None, bool]:
    """Корень статики /site/: либо NODEADLINE_SITE_ROOT (dev), либо active.json после синка."""
    override = os.environ.get("NODEADLINE_SITE_ROOT", "").strip()
    if override:
        p = os.path.abspath(os.path.expanduser(override))
        if os.path.isdir(p):
            log.info("site static root: NODEADLINE_SITE_ROOT=%s", p)
            return p, True
        log.warning("NODEADLINE_SITE_ROOT is not a directory, falling back to active.json: %s", p)
    r = _active_root_from_state(runtime_dir)
    return r, False


def _load_local_revision(runtime_dir: str) -> int:
    p = _state_path(runtime_dir)
    try:
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
        return int(j.get("revision", 0))
    except OSError:
        return 0
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0


def _save_state(
    runtime_dir: str,
    revision: int,
    bundle_sha256: str,
    *,
    last_download_bytes: int = 0,
) -> None:
    os.makedirs(_site_root(runtime_dir), mode=0o755, exist_ok=True)
    p = _state_path(runtime_dir)
    prev_total = 0
    prev_count = 0
    try:
        with open(p, encoding="utf-8") as f:
            prev = json.load(f)
            prev_total = int(prev.get("bytes_downloaded_total", 0))
            prev_count = int(prev.get("download_count", 0))
    except OSError:
        pass
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    total = prev_total + max(0, last_download_bytes)
    count = prev_count + (1 if last_download_bytes > 0 else 0)
    now = int(time.time())
    with open(p, "w", encoding="utf-8") as f:
        json.dump(
            {
                "revision": revision,
                "bundle_sha256": bundle_sha256,
                "updated_at": now,
                "bytes_downloaded_total": total,
                "last_bundle_bytes": last_download_bytes,
                "download_count": count,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")


def _validate_channel(ch: dict[str, Any]) -> tuple[int, str, str, str, str] | None:
    if str(ch.get("distribution_tier", "")).strip() != "system_master":
        log.warning("site_channel: reject non-system_master tier")
        return None
    if str(ch.get("sync_origin", "")).strip() != "system_master":
        log.warning("site_channel: reject non-system_master origin")
        return None
    rev = ch.get("revision")
    try:
        revision = int(rev)
    except (TypeError, ValueError):
        return None
    if revision < 1:
        return None
    url = str(ch.get("bundle_url", "")).strip()
    want = str(ch.get("bundle_sha256", "")).strip().lower()
    magnet = str(ch.get("magnet") or "").strip()
    torrent_url = str(ch.get("torrent_url") or "").strip()
    if len(want) != 64:
        return None
    if not magnet and not torrent_url and not url:
        return None
    return revision, url, want, magnet, torrent_url


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_to(path: str, url: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "nodeadline-node/2-site-sync"})
    with urllib.request.urlopen(req, timeout=300) as r:
        with open(path, "wb") as out:
            shutil.copyfileobj(r, out)


def _safe_extractall(tf: tarfile.TarFile, dest: str) -> None:
    dest_abs = os.path.abspath(dest)
    for m in tf.getmembers():
        target = os.path.join(dest_abs, m.name)
        abs_target = os.path.abspath(target)
        if not abs_target.startswith(dest_abs + os.sep) and abs_target != dest_abs:
            raise ValueError(f"unsafe path in archive: {m.name!r}")
    tf.extractall(dest_abs)


def _apply_bundle(runtime_dir: str, revision: int, tgz_path: str, want_sha: str) -> bool:
    got = _sha256_file(tgz_path)
    if got.lower() != want_sha:
        log.error("site bundle sha256 mismatch got=%s want=%s", got, want_sha)
        return False
    root = _site_root(runtime_dir)
    stage = os.path.join(root, f"rev-{revision}")
    if os.path.isdir(stage):
        shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage, mode=0o755, exist_ok=True)
    with tarfile.open(tgz_path, "r:gz") as tf:
        _safe_extractall(tf, stage)
    stage_abs = os.path.abspath(stage)
    active_p = os.path.join(_site_root(runtime_dir), "active.json")
    tmp = active_p + ".new"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"revision": revision, "root": stage_abs}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, active_p)
    try:
        dl_bytes = os.path.getsize(tgz_path)
    except OSError:
        dl_bytes = 0
    _save_state(runtime_dir, revision, want_sha, last_download_bytes=dl_bytes)
    log.info("site bundle applied revision=%s -> %s", revision, stage)
    return True


def sync_once(master_base: str, runtime_dir: str) -> tuple[bool, str]:
    """Синхронизация с мастером. applied=True только если скачан и применён новый бандл."""
    ch = fetch_site_channel(master_base)
    if not ch:
        return False, "fetch_failed"
    parsed = _validate_channel(ch)
    if not parsed:
        return False, "invalid_channel"
    revision, bundle_url, want_sha, magnet, torrent_url = parsed
    local_rev = _load_local_revision(runtime_dir)
    if revision <= local_rev:
        return False, "up_to_date"

    tgz_path: str | None = None
    inc_cleanup: str | None = None
    tmp_https: str | None = None

    if magnet or torrent_url:
        inc = os.path.join(runtime_dir, "site", f"_in-{revision}")
        shutil.rmtree(inc, ignore_errors=True)
        os.makedirs(inc, mode=0o755, exist_ok=True)
        inc_cleanup = inc
        try:
            tgz_path = download_torrent_content(
                magnet=magnet,
                torrent_url=torrent_url if not magnet else "",
                download_dir=inc,
            )
        except Exception as e:
            log.warning("site torrent download failed (%s) — using HTTPS bundle", e)
            tgz_path = None
            shutil.rmtree(inc, ignore_errors=True)
            inc_cleanup = None

    if tgz_path is None:
        if not bundle_url:
            log.error("site sync: no bundle_url for HTTPS fallback")
            return False, "no_bundle_url"
        fd, tmp = tempfile.mkstemp(suffix=".tar.gz")
        os.close(fd)
        tmp_https = tmp
        _download_to(tmp_https, bundle_url)
        tgz_path = tmp_https

    try:
        ok = _apply_bundle(runtime_dir, revision, tgz_path, want_sha)
        if ok:
            open_local_site_after_new_revision(runtime_dir, revision)
        if ok:
            return True, "applied"
        return False, "apply_failed"
    finally:
        if inc_cleanup:
            shutil.rmtree(inc_cleanup, ignore_errors=True)
        if tmp_https:
            try:
                os.remove(tmp_https)
            except OSError:
                pass


def sync_site_bundle_loop(master_base: str, runtime_dir: str, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            applied, _reason = sync_once(master_base, runtime_dir)
            if applied:
                pass
        except Exception:
            log.exception("site sync tick")
        stop.wait(SYNC_INTERVAL_SEC)


def get_active_site_root(runtime_dir: str) -> str | None:
    root, _ = _resolved_site_root(runtime_dir)
    return root


def site_status(runtime_dir: str) -> dict[str, Any]:
    rev = _load_local_revision(runtime_dir)
    root, dev_override = _resolved_site_root(runtime_dir)
    p = _state_path(runtime_dir)
    extra: dict[str, Any] = {}
    bundle_sha256 = ""
    try:
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
        extra["bytes_downloaded_total"] = int(j.get("bytes_downloaded_total", 0))
        extra["last_bundle_bytes"] = int(j.get("last_bundle_bytes", 0))
        extra["download_count"] = int(j.get("download_count", 0))
        extra["updated_at"] = int(j.get("updated_at", 0))
        bundle_sha256 = str(j.get("bundle_sha256", "") or "").strip().lower()
    except OSError:
        extra["bytes_downloaded_total"] = 0
        extra["last_bundle_bytes"] = 0
        extra["download_count"] = 0
        extra["updated_at"] = 0
    except (json.JSONDecodeError, TypeError, ValueError):
        extra["bytes_downloaded_total"] = 0
        extra["last_bundle_bytes"] = 0
        extra["download_count"] = 0
        extra["updated_at"] = 0
    return {
        "ok": True,
        "revision": rev,
        "bundle_sha256": bundle_sha256,
        "active": root is not None,
        "root": root or "",
        "dev_site_override": dev_override,
        **extra,
    }


def channel_state_dict(runtime_dir: str) -> dict[str, Any]:
    """Full channel_state.json for dashboard API."""
    p = _state_path(runtime_dir)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}
    except (json.JSONDecodeError, TypeError):
        return {}


def start_background_sync(master_base: str, runtime_dir: str) -> tuple[threading.Thread, threading.Event]:
    stop = threading.Event()

    def _run():
        time.sleep(1.5)
        sync_site_bundle_loop(master_base, runtime_dir, stop)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t, stop
