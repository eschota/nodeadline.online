from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import time
import uuid
from typing import Any


def _image_stem_key(share_id: str, relative_path: str) -> tuple[str, str, str]:
    """Ключ логического изображения: один jpg и png с тем же стемом — одна карточка."""
    rel = (relative_path or "").replace("\\", "/").strip()
    if not rel:
        return (share_id, "", "")
    d = os.path.dirname(rel)
    stem = os.path.splitext(os.path.basename(rel))[0]
    return (str(share_id), d.lower(), stem.lower())


def _image_ext_rank(relative_path: str) -> int:
    ext = os.path.splitext(relative_path or "")[1].lower()
    if ext in (".jpg", ".jpeg"):
        return 0
    if ext == ".png":
        return 1
    if ext == ".webp":
        return 2
    if ext == ".gif":
        return 3
    return 9


def _pick_best_image_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Среди дублей одного стема: предпочесть jpg/jpeg, затем более свежий indexed_at."""
    if len(rows) == 1:
        return rows[0]
    by_rank: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        rp = str(r.get("relative_path") or "")
        er = _image_ext_rank(rp)
        by_rank.setdefault(er, []).append(r)
    lowest = min(by_rank.keys())
    pool = by_rank[lowest]
    return max(pool, key=lambda r: str(r.get("indexed_at") or ""))


def _dedupe_marketplace_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Видео оставляем все; картинки с одинаковым стемом — одна строка (jpg важнее png)."""
    videos: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    for r in rows:
        if str(r.get("media_type") or "") == "video":
            videos.append(r)
        else:
            images.append(r)
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in images:
        key = _image_stem_key(str(r.get("share_id") or ""), str(r.get("relative_path") or ""))
        groups.setdefault(key, []).append(r)
    picked = [_pick_best_image_row(g) for g in groups.values()]
    merged = videos + picked
    merged.sort(key=lambda r: str(r.get("indexed_at") or ""), reverse=True)
    return merged


def _dedupe_gallery_image_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Галерея шара: только изображения, порядок по relative_path."""
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in rows:
        key = _image_stem_key(str(r.get("share_id") or ""), str(r.get("relative_path") or ""))
        groups.setdefault(key, []).append(r)
    picked = [_pick_best_image_row(g) for g in groups.values()]
    picked.sort(key=lambda r: str(r.get("relative_path") or ""))
    return picked

from libs.protocol import ShareEntry

_lock = threading.Lock()
_DATA_DIR: str | None = None


def set_data_dir(d: str) -> None:
    global _DATA_DIR
    _DATA_DIR = d


def _db_path() -> str:
    base = _DATA_DIR or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
    )
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "shares.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS shares (
            share_id      TEXT PRIMARY KEY,
            local_path    TEXT NOT NULL,
            mount_path    TEXT NOT NULL UNIQUE,
            visibility    TEXT NOT NULL DEFAULT 'public',
            owner_sub     TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL DEFAULT '',
            scan_status   TEXT NOT NULL DEFAULT 'pending',
            public_slug   TEXT NOT NULL DEFAULT '',
            snapshot_id   TEXT NOT NULL DEFAULT '',
            snapshot_revision INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS files (
            file_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            share_id      TEXT NOT NULL REFERENCES shares(share_id) ON DELETE CASCADE,
            relative_path TEXT NOT NULL,
            size_bytes    INTEGER NOT NULL DEFAULT 0,
            modified_at   TEXT NOT NULL DEFAULT '',
            mime_type     TEXT NOT NULL DEFAULT '',
            media_type    TEXT NOT NULL DEFAULT '',
            preview_ready INTEGER NOT NULL DEFAULT 0,
            indexed_at    TEXT NOT NULL DEFAULT '',
            UNIQUE(share_id, relative_path)
        );
        CREATE INDEX IF NOT EXISTS ix_files_share ON files(share_id);
        CREATE INDEX IF NOT EXISTS ix_files_path ON files(share_id, relative_path);
    """)


_local = threading.local()


def _conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = _connect()
        _ensure_schema(_local.conn)
    return _local.conn


def add_share(
    *,
    local_path: str,
    mount_path: str,
    owner_sub: str,
    visibility: str = "public",
) -> ShareEntry:
    slug = secrets.token_urlsafe(8).replace("-", "")[:12]
    entry = ShareEntry(
        share_id=uuid.uuid4().hex[:12],
        local_path=os.path.abspath(local_path),
        mount_path=mount_path.strip("/"),
        visibility=visibility,
        owner_sub=owner_sub,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        scan_status="pending",
        public_slug=slug,
        snapshot_id="",
        snapshot_revision=0,
    )
    c = _conn()
    with _lock:
        c.execute(
            "INSERT INTO shares (share_id, local_path, mount_path, visibility, owner_sub, "
            "created_at, scan_status, public_slug, snapshot_id, snapshot_revision) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                entry.share_id,
                entry.local_path,
                entry.mount_path,
                entry.visibility,
                entry.owner_sub,
                entry.created_at,
                entry.scan_status,
                entry.public_slug,
                entry.snapshot_id,
                entry.snapshot_revision,
            ),
        )
        c.commit()
    return entry


def get_share(share_id: str) -> ShareEntry | None:
    c = _conn()
    row = c.execute("SELECT * FROM shares WHERE share_id=?", (share_id,)).fetchone()
    return ShareEntry.from_dict(dict(row)) if row else None


def get_share_by_slug(slug: str) -> ShareEntry | None:
    c = _conn()
    row = c.execute("SELECT * FROM shares WHERE public_slug=?", (slug,)).fetchone()
    return ShareEntry.from_dict(dict(row)) if row else None


def list_shares(owner_sub: str | None = None, public_only: bool = False) -> list[ShareEntry]:
    c = _conn()
    q = "SELECT * FROM shares WHERE 1=1"
    params: list[Any] = []
    if owner_sub is not None:
        q += " AND owner_sub=?"
        params.append(owner_sub)
    if public_only:
        q += " AND visibility='public'"
    q += " ORDER BY created_at ASC"
    rows = c.execute(q, params).fetchall()
    return [ShareEntry.from_dict(dict(r)) for r in rows]


def list_shares_for_session(google_sub: str | None) -> list[ShareEntry]:
    """Logged-in: own shares plus local (pre-login) shares with owner_sub ''. Anonymous: only ''."""
    c = _conn()
    if google_sub:
        rows = c.execute(
            "SELECT * FROM shares WHERE owner_sub IN (?, '') ORDER BY created_at ASC",
            (google_sub,),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM shares WHERE owner_sub = '' ORDER BY created_at ASC",
        ).fetchall()
    return [ShareEntry.from_dict(dict(r)) for r in rows]


def update_share_visibility(share_id: str, visibility: str) -> bool:
    c = _conn()
    with _lock:
        cur = c.execute("UPDATE shares SET visibility=? WHERE share_id=?", (visibility, share_id))
        c.commit()
    return cur.rowcount > 0


def update_snapshot(share_id: str, snapshot_id: str, revision: int) -> bool:
    c = _conn()
    with _lock:
        cur = c.execute(
            "UPDATE shares SET snapshot_id=?, snapshot_revision=? WHERE share_id=?",
            (snapshot_id, revision, share_id),
        )
        c.commit()
    return cur.rowcount > 0


def update_scan_status(share_id: str, status: str) -> bool:
    c = _conn()
    with _lock:
        cur = c.execute("UPDATE shares SET scan_status=? WHERE share_id=?", (status, share_id))
        c.commit()
    return cur.rowcount > 0


def remove_share(share_id: str) -> bool:
    c = _conn()
    with _lock:
        cur = c.execute("DELETE FROM shares WHERE share_id=?", (share_id,))
        c.commit()
    return cur.rowcount > 0


def add_file(
    *,
    share_id: str,
    relative_path: str,
    size_bytes: int,
    modified_at: str,
    mime_type: str,
    media_type: str,
) -> int:
    c = _conn()
    indexed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _lock:
        cur = c.execute(
            "INSERT OR REPLACE INTO files "
            "(share_id, relative_path, size_bytes, modified_at, mime_type, media_type, indexed_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (share_id, relative_path, size_bytes, modified_at, mime_type, media_type, indexed_at),
        )
        c.commit()
    return cur.lastrowid or 0


def set_preview_ready(file_id: int, ready: int = 1) -> None:
    c = _conn()
    with _lock:
        c.execute("UPDATE files SET preview_ready=? WHERE file_id=?", (ready, file_id))
        c.commit()


def list_jpeg_png_for_posters(share_id: str) -> list[dict[str, Any]]:
    """Изображения для постеров (ffmpeg): jpg/png/webp/gif/…; без синтетических *_poster.jpg."""
    c = _conn()
    rows = c.execute(
        """
        SELECT file_id, relative_path, size_bytes, modified_at FROM files
        WHERE share_id=? AND media_type='image'
        AND lower(relative_path) NOT LIKE '%_poster.jpg'
        ORDER BY relative_path ASC
        """,
        (share_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_files_by_media_type(share_id: str, media_type: str) -> list[dict[str, Any]]:
    c = _conn()
    rows = c.execute(
        "SELECT file_id, relative_path FROM files WHERE share_id=? AND media_type=? ORDER BY relative_path ASC",
        (share_id, media_type),
    ).fetchall()
    return [dict(r) for r in rows]


def count_gallery_images(share_id: str) -> int:
    """jpg/png для веб-галереи — только с готовым постером (индекс завершён для медиа)."""
    c = _conn()
    rows = c.execute(
        """
        SELECT * FROM files WHERE share_id=? AND media_type='image'
        AND (
            lower(relative_path) LIKE '%.jpg' OR lower(relative_path) LIKE '%.jpeg'
            OR lower(relative_path) LIKE '%.png'
        )
        AND lower(relative_path) NOT LIKE '%_poster.jpg'
        AND preview_ready = 1
        ORDER BY relative_path ASC
        """,
        (share_id,),
    ).fetchall()
    deduped = _dedupe_gallery_image_rows([dict(r) for r in rows])
    return len(deduped)


def list_gallery_images(
    share_id: str,
    limit: int = 24,
    offset: int = 0,
) -> list[dict[str, Any]]:
    c = _conn()
    rows = c.execute(
        """
        SELECT * FROM files WHERE share_id=? AND media_type='image'
        AND (
            lower(relative_path) LIKE '%.jpg' OR lower(relative_path) LIKE '%.jpeg'
            OR lower(relative_path) LIKE '%.png'
        )
        AND lower(relative_path) NOT LIKE '%_poster.jpg'
        AND preview_ready = 1
        ORDER BY relative_path ASC
        """,
        (share_id,),
    ).fetchall()
    deduped = _dedupe_gallery_image_rows([dict(r) for r in rows])
    return deduped[offset : offset + limit]


_MARKETPLACE_WHERE = """
(
  (
    f.media_type = 'image'
    AND lower(f.relative_path) NOT LIKE '%_poster.jpg'
    AND f.preview_ready = 1
  )
  OR (f.media_type = 'video' AND f.preview_ready = 1)
)
"""


def count_marketplace_media(share_ids: list[str]) -> int:
    """Картинки и видео с preview_ready=1; после дедупа jpg/png по одному стему."""
    if not share_ids:
        return 0
    ph = ",".join("?" * len(share_ids))
    c = _conn()
    rows = c.execute(
        f"""
        SELECT f.*, s.public_slug AS _public_slug, s.mount_path AS _mount_path
        FROM files f
        JOIN shares s ON s.share_id = f.share_id
        WHERE f.share_id IN ({ph}) AND {_MARKETPLACE_WHERE}
        ORDER BY f.indexed_at DESC
        """,
        tuple(share_ids),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["public_slug"] = str(d.pop("_public_slug", "") or "")
        d["mount_path"] = str(d.pop("_mount_path", "") or "")
        out.append(d)
    return len(_dedupe_marketplace_rows(out))


def list_marketplace_media(
    share_ids: list[str],
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """Все шары сессии: сортировка по indexed_at DESC (дата обработки в индексе); jpg/png-дубли склеены."""
    if not share_ids:
        return []
    ph = ",".join("?" * len(share_ids))
    c = _conn()
    rows = c.execute(
        f"""
        SELECT f.*, s.public_slug AS _public_slug, s.mount_path AS _mount_path
        FROM files f
        JOIN shares s ON s.share_id = f.share_id
        WHERE f.share_id IN ({ph}) AND {_MARKETPLACE_WHERE}
        ORDER BY f.indexed_at DESC
        """,
        tuple(share_ids),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["public_slug"] = str(d.pop("_public_slug", "") or "")
        d["mount_path"] = str(d.pop("_mount_path", "") or "")
        out.append(d)
    deduped = _dedupe_marketplace_rows(out)
    return deduped[offset : offset + limit]


def list_files(
    share_id: str,
    prefix: str = "",
    limit: int = 500,
    offset: int = 0,
) -> list[dict[str, Any]]:
    c = _conn()
    q = "SELECT * FROM files WHERE share_id=?"
    params: list[Any] = [share_id]
    if prefix:
        q += " AND relative_path LIKE ?"
        params.append(prefix.rstrip("/") + "/%")
    q += " ORDER BY relative_path ASC LIMIT ? OFFSET ?"
    params += [limit, offset]
    rows = c.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def list_directory_nodes(
    share_id: str,
    prefix: str = "",
) -> dict[str, Any]:
    """Return immediate child folder names and file entries under prefix."""
    files = list_files(share_id, prefix=prefix, limit=10000, offset=0)
    seen_dirs: set[str] = set()
    out_files: list[dict[str, Any]] = []
    base = prefix.rstrip("/")
    for f in files:
        rel = f["relative_path"]
        rest = rel[len(base) + 1:] if base else rel
        if "/" in rest:
            d = rest.split("/")[0]
            seen_dirs.add(d)
        else:
            out_files.append(f)
    return {"directories": sorted(seen_dirs), "files": out_files}


def share_files_total_stats(share_id: str) -> tuple[int, int]:
    """Все записи после скана диска (строки в files)."""
    c = _conn()
    row = c.execute(
        "SELECT COUNT(*), COALESCE(SUM(size_bytes), 0) FROM files WHERE share_id=?",
        (share_id,),
    ).fetchone()
    if not row:
        return 0, 0
    return int(row[0]), int(row[1])


def share_index_ready_stats(share_id: str) -> tuple[int, int]:
    """Учитываются как проиндексированные: не-медиа файлы или image/video с готовым превью (постер)."""
    c = _conn()
    row = c.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(size_bytes), 0) FROM files WHERE share_id=?
        AND (
            media_type NOT IN ('image', 'video')
            OR (media_type IN ('image', 'video') AND preview_ready = 1)
        )
        """,
        (share_id,),
    ).fetchone()
    if not row:
        return 0, 0
    return int(row[0]), int(row[1])


def count_pending_media(share_id: str) -> int:
    """Медиа без готового превью."""
    c = _conn()
    row = c.execute(
        """
        SELECT COUNT(*) FROM files WHERE share_id=?
        AND media_type IN ('image', 'video') AND preview_ready = 0
        """,
        (share_id,),
    ).fetchone()
    return int(row[0]) if row else 0


def get_share_id_for_file(file_id: int) -> str | None:
    c = _conn()
    row = c.execute("SELECT share_id FROM files WHERE file_id=? LIMIT 1", (file_id,)).fetchone()
    return str(row[0]) if row else None


def share_index_stats(share_id: str) -> tuple[int, int]:
    """Обратная совместимость: то же, что share_files_total_stats."""
    return share_files_total_stats(share_id)


def set_scan_status_after_filesystem_scan(share_id: str) -> None:
    """После обхода диска: без медиа — ready, иначе ждём постеры."""
    c = _conn()
    row = c.execute(
        "SELECT COUNT(*) FROM files WHERE share_id=? AND media_type IN ('image', 'video')",
        (share_id,),
    ).fetchone()
    nmv = int(row[0]) if row else 0
    if nmv == 0:
        update_scan_status(share_id, "ready")
    else:
        update_scan_status(share_id, "posters_pending")


def clear_files(share_id: str) -> int:
    c = _conn()
    with _lock:
        cur = c.execute("DELETE FROM files WHERE share_id=?", (share_id,))
        c.commit()
    return cur.rowcount


def safe_resolve_path(share: ShareEntry, relative: str) -> str | None:
    root = os.path.realpath(share.local_path)
    target = os.path.realpath(os.path.join(root, relative.replace("/", os.sep)))
    if not target.startswith(root + os.sep) and target != root:
        return None
    return target
