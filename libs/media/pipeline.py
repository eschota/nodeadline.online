from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import threading
import time
import uuid
from typing import Any, Callable

from libs.system.ffmpeg_paths import ffmpeg_executable, ffprobe_executable

log = logging.getLogger(__name__)

_DATA_DIR: str | None = None
_lock = threading.Lock()
_on_done: Callable[[int], None] | None = None

PREVIEW_MAX_WIDTH = 600
POSTER_QUALITY = 85


def set_data_dir(d: str) -> None:
    global _DATA_DIR
    _DATA_DIR = d


def set_on_preview_done(cb: Callable[[int], None] | None) -> None:
    global _on_done
    _on_done = cb


def _db_path() -> str:
    base = _DATA_DIR or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
    )
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "media_jobs.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id         TEXT PRIMARY KEY,
            share_id       TEXT NOT NULL,
            file_id        INTEGER NOT NULL DEFAULT 0,
            source_path    TEXT NOT NULL,
            media_type     TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'pending',
            error          TEXT NOT NULL DEFAULT '',
            orig_w         INTEGER NOT NULL DEFAULT 0,
            orig_h         INTEGER NOT NULL DEFAULT 0,
            preview_w      INTEGER NOT NULL DEFAULT 0,
            preview_h      INTEGER NOT NULL DEFAULT 0,
            duration_sec   REAL NOT NULL DEFAULT 0,
            poster_path    TEXT NOT NULL DEFAULT '',
            preview_path   TEXT NOT NULL DEFAULT '',
            created_at     TEXT NOT NULL DEFAULT '',
            finished_at    TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS ix_jobs_share ON jobs(share_id);
        CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs(status);
    """)


_local = threading.local()


def _conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = _connect()
        _ensure_schema(_local.conn)
    return _local.conn


def ffmpeg_available() -> bool:
    return ffmpeg_executable() is not None


def ffprobe_info(path: str) -> dict[str, Any]:
    ffprobe = ffprobe_executable()
    if not ffprobe:
        return {"error": "ffprobe not found"}
    try:
        out = subprocess.check_output(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
            timeout=30,
        )
        return json.loads(out)
    except Exception as e:
        return {"error": str(e)[:300]}


def enqueue(*, share_id: str, file_id: int, source_path: str, media_type: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = _conn()
    with _lock:
        conn.execute(
            "INSERT OR IGNORE INTO jobs (job_id, share_id, file_id, source_path, media_type, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (job_id, share_id, file_id, source_path, media_type, now),
        )
        conn.commit()
    return job_id


def next_pending() -> dict[str, Any] | None:
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM jobs WHERE status='pending' ORDER BY created_at ASC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def mark_processing(job_id: str) -> None:
    conn = _conn()
    with _lock:
        conn.execute("UPDATE jobs SET status='processing' WHERE job_id=?", (job_id,))
        conn.commit()


def mark_done(job_id: str, **kw: Any) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    sets = ["status='done'", f"finished_at='{now}'"]
    params: list[Any] = []
    for col in ("preview_path", "poster_path", "preview_w", "preview_h", "orig_w", "orig_h", "duration_sec"):
        if col in kw:
            sets.append(f"{col}=?")
            params.append(kw[col])
    params.append(job_id)
    conn = _conn()
    with _lock:
        conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE job_id=?", params)
        conn.commit()


def mark_error(job_id: str, error: str) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = _conn()
    with _lock:
        conn.execute(
            "UPDATE jobs SET status='error', error=?, finished_at=? WHERE job_id=?",
            (error[:500], now, job_id),
        )
        conn.commit()


def list_jobs(share_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    conn = _conn()
    q = "SELECT * FROM jobs WHERE 1=1"
    params: list[Any] = []
    if share_id:
        q += " AND share_id=?"
        params.append(share_id)
    if status:
        q += " AND status=?"
        params.append(status)
    q += " ORDER BY created_at DESC LIMIT 200"
    return [dict(r) for r in conn.execute(q, params).fetchall()]


def preview_dir(data_root: str) -> str:
    d = os.path.join(data_root, "previews")
    os.makedirs(d, exist_ok=True)
    return d


def _dims(orig_w: int, orig_h: int) -> tuple[int, int]:
    if orig_w <= 0 or orig_h <= 0:
        return PREVIEW_MAX_WIDTH, PREVIEW_MAX_WIDTH
    if orig_w <= PREVIEW_MAX_WIDTH:
        return orig_w, orig_h
    ratio = PREVIEW_MAX_WIDTH / orig_w
    return PREVIEW_MAX_WIDTH, max(2, int(orig_h * ratio))


def process_image(job: dict[str, Any], data_root: str) -> None:
    src = job["source_path"]
    job_id = job["job_id"]
    fid = int(job.get("file_id") or 0)
    mark_processing(job_id)
    try:
        info = ffprobe_info(src)
        streams = info.get("streams") or []
        vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
        orig_w = int(vstream.get("width") or 0)
        orig_h = int(vstream.get("height") or 0)
        pw, ph = _dims(orig_w, orig_h)
        ph += ph % 2
        pw += pw % 2
        out_name = f"{job_id}_preview.webp"
        out_path = os.path.join(preview_dir(data_root), out_name)
        ff = ffmpeg_executable()
        if not ff:
            raise RuntimeError("ffmpeg not found")
        subprocess.check_call(
            [ff, "-y", "-i", src, "-vf", f"scale={pw}:{ph}", "-quality", "80", out_path],
            timeout=120,
        )
        mark_done(job_id, preview_path=out_path, orig_w=orig_w, orig_h=orig_h, preview_w=pw, preview_h=ph)
        if fid and _on_done:
            _on_done(fid)
    except Exception as e:
        mark_error(job_id, str(e))


def _run_video_ffmpeg(
    src: str,
    job_id: str,
    data_root: str,
) -> tuple[str, str, int, int, int, int, float]:
    """Возвращает poster_path, video_path, orig_w, orig_h, pw, ph, duration."""
    ff = ffmpeg_executable()
    if not ff:
        raise RuntimeError("ffmpeg not found")
    info = ffprobe_info(src)
    streams = info.get("streams") or []
    vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
    orig_w = int(vstream.get("width") or 0)
    orig_h = int(vstream.get("height") or 0)
    duration = float((info.get("format") or {}).get("duration") or 0)
    pw, ph = _dims(orig_w, orig_h)
    ph += ph % 2
    pw += pw % 2
    pdir = preview_dir(data_root)
    poster_path = os.path.join(pdir, f"{job_id}_poster.jpg")
    video_path = os.path.join(pdir, f"{job_id}_video_preview_{pw}x{ph}.mp4")
    mid_sec = max(0, min(duration / 2, 5))
    subprocess.check_call(
        [
            ff, "-y", "-ss", str(mid_sec), "-i", src,
            "-frames:v", "1", "-q:v", str(POSTER_QUALITY // 25),
            "-vf", f"scale={pw}:{ph}",
            poster_path,
        ],
        timeout=60,
    )
    subprocess.check_call(
        [
            ff, "-y", "-i", src, "-vf", f"scale={pw}:{ph}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "28", "-an",
            "-movflags", "+faststart", "-t", "30",
            video_path,
        ],
        timeout=300,
    )
    return poster_path, video_path, orig_w, orig_h, pw, ph, duration


def process_video(job: dict[str, Any], data_root: str) -> None:
    src = job["source_path"]
    job_id = job["job_id"]
    fid = int(job.get("file_id") or 0)
    mark_processing(job_id)
    try:
        poster_path, video_path, orig_w, orig_h, pw, ph, duration = _run_video_ffmpeg(src, job_id, data_root)
        mark_done(
            job_id,
            poster_path=poster_path,
            preview_path=video_path,
            orig_w=orig_w,
            orig_h=orig_h,
            preview_w=pw,
            preview_h=ph,
            duration_sec=duration,
        )
        if fid and _on_done:
            _on_done(fid)
    except Exception as e:
        mark_error(job_id, str(e))


def run_video_preview_for_task(job: dict[str, Any], data_root: str) -> None:
    """Видео-превью для единой очереди (без media_jobs)."""
    src = job["source_path"]
    job_id = str(job.get("job_id") or uuid.uuid4().hex[:12])
    fid = int(job.get("file_id") or 0)
    _run_video_ffmpeg(src, job_id, data_root)
    if fid and _on_done:
        _on_done(fid)


def worker_loop(data_root: str, stop_event: threading.Event | None = None) -> None:
    log.info("media worker started")
    while True:
        if stop_event and stop_event.is_set():
            break
        job = next_pending()
        if job is None:
            time.sleep(2)
            continue
        if job["media_type"] == "image":
            process_image(job, data_root)
        elif job["media_type"] == "video":
            process_video(job, data_root)
        else:
            mark_error(job["job_id"], "unknown media")


def start_worker(data_root: str) -> tuple[threading.Thread, threading.Event]:
    stop = threading.Event()
    t = threading.Thread(target=worker_loop, args=(data_root,), kwargs={"stop_event": stop}, daemon=True)
    t.start()
    return t, stop
