"""Манифест индексации шара: JSON в runtime + синхронизация scan_status."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from libs.shares import registry

log = logging.getLogger(__name__)


def _manifest_path(runtime_dir: str, share_id: str) -> str:
    d = os.path.join(runtime_dir, "index_manifest")
    os.makedirs(d, mode=0o755, exist_ok=True)
    return os.path.join(d, f"{share_id}.json")


def try_finalize_scan_status(share_id: str) -> None:
    """ready — когда не осталось медиа без превью; иначе posters_pending."""
    sh = registry.get_share(share_id)
    if not sh or sh.scan_status == "error":
        return
    if registry.count_pending_media(share_id) == 0:
        registry.update_scan_status(share_id, "ready")
    else:
        registry.update_scan_status(share_id, "posters_pending")


def write_manifest(share_id: str, runtime_dir: str) -> dict[str, Any]:
    total_n, total_b = registry.share_files_total_stats(share_id)
    ready_n, ready_b = registry.share_index_ready_stats(share_id)
    pending = registry.count_pending_media(share_id)
    sh = registry.get_share(share_id)
    st = str(sh.scan_status) if sh else ""
    out: dict[str, Any] = {
        "share_id": share_id,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scan_status": st,
        "files_total": total_n,
        "files_total_bytes": total_b,
        "indexed_files": ready_n,
        "indexed_bytes": ready_b,
        "media_pending": pending,
        "index_complete": pending == 0 and st == "ready",
    }
    try:
        p = _manifest_path(runtime_dir, share_id)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        log.warning("index_manifest write failed: %s", e)
    return out


def touch(share_id: str, runtime_dir: str) -> None:
    """После смены preview_ready или скана — обновить манифест и статус шара."""
    try_finalize_scan_status(share_id)
    write_manifest(share_id, runtime_dir)
