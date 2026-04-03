"""Очередь задач: SQLite, FIFO, один последовательный воркер."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from urllib.parse import quote
import threading
import time
import uuid
from typing import Any

log = logging.getLogger(__name__)

_DATA_DIR: str | None = None
_lock = threading.Lock()
_worker_started = False

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Параллельные воркеры постеров/превью (I/O + CPU); SQLite claim атомарен под _lock.
def _task_worker_count() -> int:
    raw = os.environ.get("NODEADLINE_TASK_WORKERS", "4").strip() or "4"
    try:
        n = int(raw)
    except ValueError:
        n = 4
    return max(1, min(n, 16))


def set_data_dir(d: str) -> None:
    global _DATA_DIR
    _DATA_DIR = d


def _db_path() -> str:
    base = _DATA_DIR or os.path.join(_REPO_ROOT, "data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "tasks.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id         TEXT PRIMARY KEY,
            kind            TEXT NOT NULL,
            payload_json    TEXT NOT NULL DEFAULT '{}',
            share_id        TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'pending',
            progress_done   INTEGER NOT NULL DEFAULT 0,
            progress_total  INTEGER NOT NULL DEFAULT 0,
            phase           TEXT NOT NULL DEFAULT '',
            error           TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT '',
            started_at      TEXT NOT NULL DEFAULT '',
            finished_at     TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS ix_tasks_created ON tasks(created_at);
    """)


_local = threading.local()


def _conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = _connect()
        _ensure_schema(_local.conn)
    return _local.conn


def enqueue(
    *,
    kind: str,
    payload: dict[str, Any],
    share_id: str = "",
) -> str:
    task_id = uuid.uuid4().hex[:16]
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = _conn()
    with _lock:
        conn.execute(
            "INSERT INTO tasks (task_id, kind, payload_json, share_id, status, created_at) "
            "VALUES (?,?,?,?, 'pending', ?)",
            (task_id, kind, json.dumps(payload, ensure_ascii=False), share_id, now),
        )
        conn.commit()
    return task_id


def _count_pending_processing() -> tuple[int, int]:
    conn = _conn()
    p = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]
    r = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='processing'").fetchone()[0]
    return int(p), int(r)


def get_current_processing() -> dict[str, Any] | None:
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM tasks WHERE status='processing' ORDER BY started_at ASC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def get_last_failed_task() -> dict[str, Any] | None:
    conn = _conn()
    row = conn.execute(
        "SELECT task_id, kind, share_id, error, finished_at FROM tasks "
        "WHERE status='error' AND COALESCE(error,'')!='' ORDER BY finished_at DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def get_status_snapshot() -> dict[str, Any]:
    """Для GET /api/tasks/status: очередь, текущая задача, ETA (сек)."""
    conn = _conn()
    pending = int(conn.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0])
    cur = get_current_processing()
    eta_seconds: float | None = None
    if cur:
        done = int(cur.get("progress_done") or 0)
        total = int(cur.get("progress_total") or 0)
        started = str(cur.get("started_at") or "").replace("Z", "").strip()
        if done > 0 and total > done and started:
            try:
                t0 = time.mktime(time.strptime(started[:19], "%Y-%m-%dT%H:%M:%S"))
                elapsed = max(0.001, time.time() - t0)
                rate = done / elapsed
                if rate > 0:
                    eta_seconds = round((total - done) / rate, 1)
            except (ValueError, OSError):
                pass
    return {
        "ok": True,
        "queue_pending": pending,
        "queue_processing": int(conn.execute("SELECT COUNT(*) FROM tasks WHERE status='processing'").fetchone()[0]),
        "current": cur,
        "eta_seconds": eta_seconds,
        "last_failed": get_last_failed_task(),
    }


def _thumb_url_for_task(kind: str, status: str, share_id: str, payload_json: str) -> str:
    try:
        p = json.loads(payload_json or "{}")
    except json.JSONDecodeError:
        return ""
    if not isinstance(p, dict):
        return ""
    sid = (share_id or str(p.get("share_id") or "")).strip()
    if kind == "image_poster":
        rel = str(p.get("relative_path") or "")
        if not sid or not rel:
            return ""
        if status == "done":
            from libs.media.poster_sidecar import poster_relpath_for_image

            pr = poster_relpath_for_image(rel)
            return f"/api/shares/{sid}/file?path={quote(pr, safe='')}"
        if status == "error":
            return f"/api/shares/{sid}/file?path={quote(rel, safe='')}"
        return ""
    if kind == "video_preview":
        jid = str(p.get("job_id") or "")
        if jid and status == "done":
            return f"/preview/{jid}_poster.jpg"
        return ""
    return ""


def _task_row_public(d: dict[str, Any]) -> dict[str, Any]:
    pj = str(d.get("payload_json") or "")
    summary = _payload_summary(pj)
    sid = str(d.get("share_id") or "").strip()
    if not sid:
        try:
            parsed = json.loads(pj or "{}")
            if isinstance(parsed, dict):
                sid = str(parsed.get("share_id") or "").strip()
        except json.JSONDecodeError:
            pass
    err = str(d.get("error") or "")
    st = str(d.get("status") or "")
    kind = str(d.get("kind") or "")
    tier = 2
    if st == "processing":
        tier = 0
    elif st == "pending":
        tier = 1
    fn = ""
    try:
        p = json.loads(pj or "{}")
        if isinstance(p, dict) and p.get("relative_path"):
            fn = os.path.basename(str(p["relative_path"]))
    except json.JSONDecodeError:
        pass
    return {
        "task_id": str(d.get("task_id") or ""),
        "kind": kind,
        "share_id": sid,
        "status": st,
        "status_tier": tier,
        "phase": str(d.get("phase") or "")[:200],
        "progress_done": int(d.get("progress_done") or 0),
        "progress_total": int(d.get("progress_total") or 0),
        "error": err[:400],
        "created_at": str(d.get("created_at") or ""),
        "started_at": str(d.get("started_at") or ""),
        "finished_at": str(d.get("finished_at") or ""),
        "payload_summary": summary,
        "file_label": fn[:120],
        "thumb_url": _thumb_url_for_task(kind, st, sid, pj),
    }


def list_recent_done(limit: int = 12) -> list[dict[str, Any]]:
    """Последние успешно завершённые задачи (для превью в UI)."""
    lim = max(1, min(int(limit), 50))
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE status='done' ORDER BY COALESCE(NULLIF(finished_at,''), created_at) DESC LIMIT ?",
        (lim,),
    ).fetchall()
    return [_task_row_public(dict(r)) for r in rows]


def _payload_summary(payload_json: str) -> str:
    try:
        p = json.loads(payload_json or "{}")
    except json.JSONDecodeError:
        return ""
    if not isinstance(p, dict):
        return ""
    parts: list[str] = []
    for k in ("share_id", "relative_path", "local_path", "source_path"):
        v = p.get(k)
        if v is not None and str(v).strip():
            parts.append(f"{k}={str(v).strip()}")
    s = " ".join(parts)
    return s[:300]


def list_tasks_recent(
    limit: int = 50,
    offset: int = 0,
    *,
    sort_mode: str = "created_desc",
) -> tuple[list[dict[str, Any]], int]:
    """История задач.

    sort_mode:
      - created_desc — по времени создания (новые сверху), для журналов и offset.
      - priority — сначала processing, затем pending, затем завершённые по свежести;
        внутри групп: выполняется по started_at ASC, очередь по created_at ASC,
        архив по finished_at DESC.
    """
    lim = max(1, min(int(limit), 200))
    off = max(0, int(offset))
    conn = _conn()
    total = int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])
    if sort_mode == "priority":
        order_sql = """
            ORDER BY
              CASE status WHEN 'processing' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
              CASE WHEN status = 'processing' THEN COALESCE(NULLIF(started_at, ''), created_at) END ASC,
              CASE WHEN status = 'pending' THEN created_at END ASC,
              CASE WHEN status NOT IN ('processing', 'pending')
                THEN COALESCE(NULLIF(finished_at, ''), created_at) END DESC
        """
    else:
        order_sql = "ORDER BY created_at DESC"
    rows = conn.execute(
        f"SELECT * FROM tasks {order_sql} LIMIT ? OFFSET ?",
        (lim, off),
    ).fetchall()
    out = [_task_row_public(dict(r)) for r in rows]
    return out, total


def claim_next_pending() -> dict[str, Any] | None:
    conn = _conn()
    with _lock:
        row = conn.execute(
            "SELECT * FROM tasks WHERE status='pending' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        tid = row["task_id"]
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn.execute(
            "UPDATE tasks SET status='processing', started_at=? WHERE task_id=?",
            (now, tid),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM tasks WHERE task_id=?", (tid,)).fetchone())


def update_progress(
    task_id: str,
    *,
    progress_done: int,
    progress_total: int,
    phase: str = "",
) -> None:
    conn = _conn()
    with _lock:
        conn.execute(
            "UPDATE tasks SET progress_done=?, progress_total=?, phase=? WHERE task_id=?",
            (progress_done, progress_total, phase[:200], task_id),
        )
        conn.commit()


def mark_done(task_id: str) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = _conn()
    with _lock:
        conn.execute(
            "UPDATE tasks SET status='done', finished_at=?, error='' WHERE task_id=?",
            (now, task_id),
        )
        conn.commit()


def mark_error(task_id: str, err: str) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = _conn()
    with _lock:
        conn.execute(
            "UPDATE tasks SET status='error', error=?, finished_at=? WHERE task_id=?",
            (err[:800], now, task_id),
        )
        conn.commit()


def _worker_loop(data_root: str, stop: threading.Event) -> None:
    from libs.tasks import handlers

    log.info("unified task worker started")
    while not stop.is_set():
        task = claim_next_pending()
        if task is None:
            time.sleep(0.35)
            continue
        tid = task["task_id"]
        kind = task["kind"]
        try:
            payload = json.loads(task["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        try:
            handlers.dispatch_task(
                task,
                data_root=data_root,
                payload=payload,
            )
            mark_done(tid)
        except Exception as e:
            log.exception("task %s %s failed", tid, kind)
            mark_error(tid, str(e))


def start_worker(data_root: str, _repo_root: str | None = None) -> tuple[threading.Thread, threading.Event]:
    global _worker_started
    if _worker_started:
        stop = threading.Event()
        return threading.Thread(), stop
    stop = threading.Event()
    n = _task_worker_count()
    first: threading.Thread | None = None
    for i in range(n):
        t = threading.Thread(
            target=_worker_loop,
            args=(data_root, stop),
            name=f"node-tasks-worker-{i + 1}",
            daemon=True,
        )
        t.start()
        if first is None:
            first = t
    log.info("unified task workers started count=%s", n)
    _worker_started = True
    return first or threading.Thread(), stop
