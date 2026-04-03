from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from libs.shares import registry


def file_manifest(share_id: str) -> list[dict[str, Any]]:
    rows = registry.list_files(share_id, prefix="", limit=100000, offset=0)
    return sorted(
        [{"path": r["relative_path"], "size": r["size_bytes"]} for r in rows],
        key=lambda x: x["path"],
    )


def compute_infohash(*, share_id: str, snapshot_id: str, revision: int, manifest: list[dict[str, Any]]) -> str:
    payload = {
        "share_id": share_id,
        "snapshot_id": snapshot_id,
        "revision": revision,
        "files": manifest,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha1(raw).hexdigest()


def infohash_binary_from_hex(hex_str: str) -> bytes:
    return bytes.fromhex(hex_str)


def publish_snapshot(*, share_id: str, owner_sub: str) -> tuple[str, str, int, str]:
    """Returns snapshot_id, infohash_hex, revision, manifest_json."""
    share = registry.get_share(share_id)
    if not share:
        raise ValueError("share not found")
    manifest = file_manifest(share_id)
    revision = int(share.snapshot_revision or 0) + 1
    snapshot_id = uuid.uuid4().hex[:16]
    ih = compute_infohash(
        share_id=share_id,
        snapshot_id=snapshot_id,
        revision=revision,
        manifest=manifest,
    )
    registry.update_snapshot(share_id, snapshot_id, revision)
    return snapshot_id, ih, revision, json.dumps(manifest, ensure_ascii=False)
