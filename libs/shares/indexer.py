from __future__ import annotations

import logging
import mimetypes
import os
import threading
import time
from typing import Callable

from libs.shares import registry

log = logging.getLogger(__name__)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv"}


def classify_media(rel_path: str) -> str:
    ext = os.path.splitext(rel_path)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return ""


def scan_share(share_id: str, local_path: str, *, on_file: Callable | None = None) -> int:
    if not os.path.isdir(local_path):
        registry.update_scan_status(share_id, "error")
        return 0
    registry.update_scan_status(share_id, "scanning")
    registry.clear_files(share_id)
    count = 0
    for dirpath, _dirs, filenames in os.walk(local_path):
        for fname in filenames:
            if fname.lower().endswith("_poster.jpg"):
                continue
            abs_path = os.path.join(dirpath, fname)
            try:
                stat = os.stat(abs_path)
            except OSError:
                continue
            rel = os.path.relpath(abs_path, local_path).replace("\\", "/")
            mime, _ = mimetypes.guess_type(fname)
            media_type = classify_media(rel)
            fid = registry.add_file(
                share_id=share_id,
                relative_path=rel,
                size_bytes=stat.st_size,
                modified_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
                mime_type=mime or "application/octet-stream",
                media_type=media_type,
            )
            count += 1
            if on_file:
                on_file(share_id=share_id, file_id=fid, rel=rel, media_type=media_type)
    registry.set_scan_status_after_filesystem_scan(share_id)
    log.info("indexed share %s: %d files", share_id, count)
    return count


def scan_share_async(share_id: str, local_path: str, **kw) -> threading.Thread:
    t = threading.Thread(
        target=scan_share,
        args=(share_id, local_path),
        kwargs=kw,
        daemon=True,
        name=f"indexer-{share_id}",
    )
    t.start()
    return t
