"""Синхронизация vendor/ffmpeg с мастера: BitTorrent + web seed, SHA256 (отдельно Windows / Linux)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import socket
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from libs.site_sync.torrent_sync import download_torrent_content

log = logging.getLogger(__name__)

FFMPEG_SYNC_INTERVAL_SEC = 42.0
_FETCH_WARN_INTERVAL_SEC = 300.0
_last_fetch_warn_mono: float = 0.0


def _is_http_not_found(exc: BaseException) -> bool:
    return isinstance(exc, urllib.error.HTTPError) and getattr(exc, "code", 0) == 404


def _is_transient_fetch_error(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.URLError) and exc.reason is not None:
        return _is_transient_fetch_error(exc.reason)
    if isinstance(exc, socket.gaierror):
        return True
    if isinstance(exc, OSError):
        if exc.errno in (11001, 11002, 11003):
            return True
    s = str(exc).lower()
    return "getaddrinfo" in s or "name or service not known" in s


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_to(path: str, url: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "nodeadline-node/2-ffmpeg-sync"})
    with urllib.request.urlopen(req, timeout=600) as r:
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


def _ffmpeg_state_dir(runtime_dir: str) -> str:
    return os.path.join(runtime_dir, "ffmpeg_vendor")


def _ffmpeg_state_path(runtime_dir: str) -> str:
    return os.path.join(_ffmpeg_state_dir(runtime_dir), "channel_state.json")


def _vendor_target(runtime_dir: str, platform_key: str) -> str:
    return os.path.join(runtime_dir, "vendor", "ffmpeg", platform_key)


def _platform_key() -> str | None:
    if sys.platform == "win32" or os.name == "nt":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return None


def fetch_ffmpeg_channel(master_base: str) -> dict[str, Any] | None:
    global _last_fetch_warn_mono
    base = master_base.rstrip("/")
    url = f"{base}/ffmpeg_channel.json?cb={int(time.time() * 1000)}"
    req = urllib.request.Request(
        url,
        headers={"Cache-Control": "no-cache", "User-Agent": "nodeadline-node/2-ffmpeg-sync"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        if _is_http_not_found(e):
            log.debug(
                "ffmpeg_channel: нет на мастере (404) — канал не опубликован, см. tools/build_ffmpeg_channel.py"
            )
            return None
        now = time.monotonic()
        if now - _last_fetch_warn_mono >= _FETCH_WARN_INTERVAL_SEC:
            _last_fetch_warn_mono = now
            if _is_transient_fetch_error(e):
                log.warning(
                    "ffmpeg_channel: master unreachable; retry every %ss. %s",
                    int(FFMPEG_SYNC_INTERVAL_SEC),
                    e,
                )
            else:
                log.warning("ffmpeg_channel fetch failed: %s", e)
        else:
            log.debug("ffmpeg_channel fetch failed: %s", e)
        return None


def _validate_top(ch: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
    if str(ch.get("distribution_tier", "")).strip() != "system_master":
        log.warning("ffmpeg_channel: reject non-system_master tier")
        return None
    if str(ch.get("sync_origin", "")).strip() != "system_master":
        log.warning("ffmpeg_channel: reject non-system_master origin")
        return None
    try:
        revision = int(ch.get("revision", 0))
    except (TypeError, ValueError):
        return None
    if revision < 1:
        return None
    return revision, ch


def _validate_platform_block(b: Any) -> tuple[str, str, str, str] | None:
    if not isinstance(b, dict):
        return None
    url = str(b.get("bundle_url", "")).strip()
    want = str(b.get("bundle_sha256", "")).strip().lower()
    magnet = str(b.get("magnet") or "").strip()
    torrent_url = str(b.get("torrent_url") or "").strip()
    if len(want) != 64:
        return None
    if not magnet and not torrent_url and not url:
        return None
    return url, want, magnet, torrent_url


def _load_local_revision(runtime_dir: str) -> int:
    p = _ffmpeg_state_path(runtime_dir)
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
    platform_key: str,
    last_download_bytes: int = 0,
) -> None:
    os.makedirs(_ffmpeg_state_dir(runtime_dir), mode=0o755, exist_ok=True)
    p = _ffmpeg_state_path(runtime_dir)
    now = int(time.time())
    with open(p, "w", encoding="utf-8") as f:
        json.dump(
            {
                "revision": revision,
                "platform": platform_key,
                "bundle_sha256": bundle_sha256,
                "updated_at": now,
                "last_bundle_bytes": last_download_bytes,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")


def _apply_bundle(
    runtime_dir: str,
    revision: int,
    tgz_path: str,
    want_sha: str,
    platform_key: str,
) -> bool:
    got = _sha256_file(tgz_path)
    if got.lower() != want_sha.lower():
        log.error("ffmpeg bundle sha256 mismatch got=%s want=%s", got, want_sha)
        return False
    stage = tempfile.mkdtemp(prefix="ndl-ff-")
    try:
        with tarfile.open(tgz_path, "r:gz") as tf:
            _safe_extractall(tf, stage)
        sub = os.path.join(stage, platform_key)
        if not os.path.isdir(sub):
            log.error("ffmpeg archive: missing %s/", platform_key)
            return False
        dest_root = os.path.join(runtime_dir, "vendor", "ffmpeg")
        os.makedirs(dest_root, mode=0o755, exist_ok=True)
        target = os.path.join(dest_root, platform_key)
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(sub, target)
        if platform_key == "linux":
            for name in ("ffmpeg", "ffprobe"):
                p = os.path.join(target, name)
                if os.path.isfile(p):
                    os.chmod(p, 0o755)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    try:
        sz = os.path.getsize(tgz_path)
    except OSError:
        sz = 0
    _save_state(runtime_dir, revision, want_sha, platform_key=platform_key, last_download_bytes=sz)
    log.info("ffmpeg vendor applied revision=%s platform=%s", revision, platform_key)
    return True


def sync_ffmpeg_once(master_base: str, runtime_dir: str) -> tuple[bool, str]:
    pk = _platform_key()
    if not pk:
        return False, "unsupported_platform"

    ch = fetch_ffmpeg_channel(master_base)
    if not ch:
        return False, "fetch_failed"
    parsed = _validate_top(ch)
    if not parsed:
        return False, "invalid_channel"
    revision, full = parsed
    block = full.get(pk)
    plat = _validate_platform_block(block)
    if not plat:
        return False, f"missing_{pk}"
    bundle_url, want_sha, magnet, torrent_url = plat

    if revision <= _load_local_revision(runtime_dir):
        return False, "up_to_date"

    tgz_path: str | None = None
    inc_cleanup: str | None = None
    tmp_https: str | None = None

    if magnet or torrent_url:
        inc = os.path.join(_ffmpeg_state_dir(runtime_dir), f"_in-{revision}-{pk}")
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
            log.warning("ffmpeg torrent download failed (%s) — HTTPS", e)
            tgz_path = None
            shutil.rmtree(inc, ignore_errors=True)
            inc_cleanup = None

    if tgz_path is None:
        if not bundle_url:
            return False, "no_bundle_url"
        fd, tmp = tempfile.mkstemp(suffix=".tar.gz")
        os.close(fd)
        tmp_https = tmp
        _download_to(tmp_https, bundle_url)
        tgz_path = tmp_https

    try:
        ok = _apply_bundle(runtime_dir, revision, tgz_path, want_sha, pk)
        return (True, "applied") if ok else (False, "apply_failed")
    finally:
        if inc_cleanup:
            shutil.rmtree(inc_cleanup, ignore_errors=True)
        if tmp_https:
            try:
                os.remove(tmp_https)
            except OSError:
                pass


def ffmpeg_vendor_status(runtime_dir: str) -> dict[str, Any]:
    rev = _load_local_revision(runtime_dir)
    pk = _platform_key()
    root = _vendor_target(runtime_dir, pk) if pk else ""
    ok = bool(pk and root and os.path.isdir(root))
    exe = os.path.join(root, "ffmpeg.exe" if pk == "windows" else "ffmpeg")
    return {
        "revision": rev,
        "platform": pk,
        "vendor_dir": root if ok else None,
        "binaries_present": ok and os.path.isfile(exe),
    }


def ffmpeg_sync_loop(master_base: str, runtime_dir: str, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            sync_ffmpeg_once(master_base, runtime_dir)
        except Exception:
            log.exception("ffmpeg sync tick")
        stop.wait(FFMPEG_SYNC_INTERVAL_SEC)


def start_ffmpeg_background_sync(master_base: str, runtime_dir: str) -> tuple[threading.Thread, threading.Event]:
    stop = threading.Event()
    t = threading.Thread(
        target=ffmpeg_sync_loop,
        args=(master_base, runtime_dir, stop),
        name="ffmpeg-sync",
        daemon=True,
    )
    t.start()
    return t, stop
