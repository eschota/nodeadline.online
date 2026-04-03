"""Обработчики задач единой очереди."""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from libs.media import pipeline
from libs.media import poster_sidecar
from libs.shares import index_manifest, indexer, registry
from libs.tasks import queue as taskq

log = logging.getLogger(__name__)


def dispatch_task(
    task: dict[str, Any],
    *,
    data_root: str,
    payload: dict[str, Any],
) -> None:
    kind = task["kind"]
    tid = task["task_id"]
    if kind == "index_share":
        _run_index_share(tid, payload, data_root)
    elif kind == "video_preview":
        _run_video_preview(task, payload, data_root)
    elif kind == "image_poster":
        _run_image_poster(task, payload, data_root)
    else:
        raise ValueError(f"unknown task kind: {kind}")


def _run_index_share(task_id: str, payload: dict[str, Any], data_root: str) -> None:
    share_id = str(payload.get("share_id") or "")
    local_path = str(payload.get("local_path") or "")
    if not share_id or not local_path:
        raise ValueError("index_share: share_id and local_path required")
    sh = registry.get_share(share_id)
    if not sh:
        raise ValueError("share not found")

    taskq.update_progress(task_id, progress_done=0, progress_total=0, phase="scan")
    indexer.scan_share(share_id, local_path, on_file=None)
    sh = registry.get_share(share_id)
    if not sh:
        raise ValueError("share not found")

    # Сначала видео — задачи в очереди сразу (раньше видео ставились после всех постеров картинок).
    vids = registry.list_files_by_media_type(share_id, "video")
    for v in vids:
        taskq.enqueue(
            kind="video_preview",
            payload={
                "share_id": share_id,
                "file_id": int(v["file_id"]),
                "source_path": os.path.join(sh.local_path, str(v["relative_path"]).replace("/", os.sep)),
                "job_id": uuid.uuid4().hex[:12],
            },
            share_id=share_id,
        )

    targets = registry.list_jpeg_png_for_posters(share_id)
    n = len(targets)
    taskq.update_progress(task_id, progress_done=0, progress_total=max(1, n), phase="poster_queue")

    for i, row in enumerate(targets):
        rel = str(row["relative_path"])
        fid = int(row["file_id"])
        sz = int(row.get("size_bytes") or 0)
        mtime = str(row.get("modified_at") or "")
        if poster_sidecar.poster_up_to_date(sh.local_path, rel):
            registry.set_preview_ready(fid, 1)
            taskq.update_progress(task_id, progress_done=i + 1, progress_total=n, phase="poster_queue")
            continue
        taskq.enqueue(
            kind="image_poster",
            payload={
                "share_id": share_id,
                "file_id": fid,
                "relative_path": rel,
                "size_bytes": sz,
                "modified_at": mtime,
            },
            share_id=share_id,
        )
        taskq.update_progress(task_id, progress_done=i + 1, progress_total=n, phase="poster_queue")

    taskq.update_progress(task_id, progress_done=1, progress_total=1, phase="done")
    index_manifest.touch(share_id, data_root)


def _run_image_poster(task: dict[str, Any], payload: dict[str, Any], data_root: str) -> None:
    share_id = str(payload.get("share_id") or "")
    fid = int(payload.get("file_id") or 0)
    rel = str(payload.get("relative_path") or "")
    if not share_id or not rel:
        raise ValueError("image_poster: share_id and relative_path required")
    sh = registry.get_share(share_id)
    if not sh:
        raise ValueError("share not found")
    sz = int(payload.get("size_bytes") or 0)
    mtime = str(payload.get("modified_at") or "")
    try:
        poster_sidecar.build_image_poster(
            share_local_root=sh.local_path,
            relative_path=rel,
            size_bytes=sz,
            modified_at=mtime,
        )
        registry.set_preview_ready(fid, 1)
        index_manifest.touch(share_id, data_root)
    except Exception as e:
        log.warning("image_poster %s: %s", rel, e)
        try:
            index_manifest.touch(share_id, data_root)
        except Exception:
            pass
        raise


def _run_video_preview(task: dict[str, Any], payload: dict[str, Any], data_root: str) -> None:
    job = {
        "job_id": str(payload.get("job_id") or uuid.uuid4().hex[:12]),
        "share_id": str(payload.get("share_id") or ""),
        "file_id": int(payload.get("file_id") or 0),
        "source_path": str(payload.get("source_path") or ""),
        "media_type": "video",
    }
    if not job["source_path"] or not os.path.isfile(job["source_path"]):
        raise ValueError("video_preview: missing source_path")
    pipeline.run_video_preview_for_task(job, data_root)
