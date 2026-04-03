"""Disk volumes and benchmark. Windows: GetLogicalDrives + shutil; иначе psutil; Linux: statvfs+/proc/mounts."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from typing import Any

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None  # type: ignore

_SKIP_FSTYPES = frozenset({
    "proc", "sysfs", "devtmpfs", "tmpfs", "cgroup", "cgroup2", "pstore",
    "bpf", "autofs", "tracefs", "debugfs", "securityfs", "configfs",
    "fusectl", "rpc_pipefs", "binfmt_misc", "hugetlbfs", "mqueue", "squashfs",
})


def _unescape_mount(s: str) -> str:
    return s.replace("\\040", " ").replace("\\011", "\t")


def _list_volumes_psutil() -> list[dict[str, Any]]:
    if psutil is None:
        return []
    for all_part in (False, True):
        out: list[dict[str, Any]] = []
        for p in psutil.disk_partitions(all=all_part):
            try:
                u = psutil.disk_usage(p.mountpoint)
            except (PermissionError, OSError):
                continue
            out.append({
                "device": p.device,
                "mountpoint": p.mountpoint,
                "fstype": p.fstype or "",
                "total": u.total,
                "used": u.used,
                "free": u.free,
                "percent": round(u.percent, 2),
            })
        if out:
            return out
    return []


def _list_volumes_linux_statvfs() -> list[dict[str, Any]]:
    """No psutil or empty: enumerate real mounts from /proc/mounts."""
    rows: list[tuple[str, str, str]] = []
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                device, mnt, fstype = parts[0], _unescape_mount(parts[1]), parts[2]
                if fstype in _SKIP_FSTYPES:
                    continue
                if mnt.startswith("/proc") or mnt.startswith("/sys") or mnt in ("/dev", "/dev/pts"):
                    continue
                rows.append((device, mnt, fstype))
    except OSError:
        return []

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for device, mnt, fstype in rows:
        if mnt in seen:
            continue
        try:
            sv = os.statvfs(mnt)
        except (OSError, PermissionError, FileNotFoundError):
            continue
        fr = sv.f_frsize or sv.f_bsize
        total = fr * sv.f_blocks
        free = fr * sv.f_bavail
        if total <= 0:
            continue
        used = total - free
        pct = round(100.0 * used / total, 2) if total else 0.0
        out.append({
            "device": device,
            "mountpoint": mnt,
            "fstype": fstype,
            "total": int(total),
            "used": int(used),
            "free": int(free),
            "percent": pct,
        })
        seen.add(mnt)
    return out


def _windows_logical_drive_roots() -> list[str]:
    """Список корней C:\\, D:\\, … через GetLogicalDrives() (битовая маска).

    Не использовать GetLogicalDriveStringsW + buf.value: у UnicodeBuffer .value
    обрезается по первому \\0, в ответ попадает только первый том.
    """
    try:
        import ctypes
    except ImportError:
        return []
    try:
        k32 = ctypes.windll.kernel32
    except (AttributeError, OSError):
        return []
    try:
        mask = int(k32.GetLogicalDrives())
    except (AttributeError, OSError):
        return []
    if mask == 0:
        return []
    roots: list[str] = []
    for i in range(26):
        if mask & (1 << i):
            roots.append(f"{chr(ord('A') + i)}:\\")
    return roots


def _windows_drive_roots_letters() -> list[str]:
    """Если API недоступен — те же буквы, что видит Explorer (A:\\ … Z:\\)."""
    return [
        f"{chr(ord('A') + i)}:\\"
        for i in range(26)
        if os.path.exists(f"{chr(ord('A') + i)}:\\")
    ]


def _disk_usage_for_roots(roots: list[str], *, allow_zero_total: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for root in roots:
        root = os.path.normpath(root)
        if not root.endswith(os.sep):
            root = root + os.sep
        try:
            du = shutil.disk_usage(root)
        except OSError:
            continue
        total = du.total
        if total <= 0 and not allow_zero_total:
            continue
        used, free = du.used, du.free
        pct = round(100.0 * used / total, 2) if total > 0 else 0.0
        out.append({
            "device": root,
            "mountpoint": root,
            "fstype": "",
            "total": int(total),
            "used": int(used),
            "free": int(free),
            "percent": pct,
        })
    return out


def _is_windows_os() -> bool:
    return bool(sys.platform == "win32" or os.name == "nt" or str(sys.platform).startswith("cygwin"))


def list_volumes() -> list[dict[str, Any]]:
    # Windows: буквы из GetLogicalDrives(); тома с total=0 (пустой привод) не отбрасываем —
    # иначе при одном таком диске список мог быть пустым.
    if _is_windows_os():
        roots = _windows_logical_drive_roots() or _windows_drive_roots_letters()
        if roots:
            vols = _disk_usage_for_roots(roots, allow_zero_total=True)
            if vols:
                return vols
        out = _list_volumes_psutil()
        if out:
            return out
        return []
    out = _list_volumes_psutil()
    if out:
        return out
    if sys.platform == "linux":
        return _list_volumes_linux_statvfs()
    return []


def _is_windows_drive_root(path: str) -> bool:
    """True for C:\\ (root of a drive); writing files there is often denied for non-admin users."""
    if not _is_windows_os():
        return False
    p = os.path.normcase(os.path.normpath(path))
    if len(p) < 3 or p[1] != ":":
        return False
    return p[3:].strip("\\") == ""


def _bench_directory_for_path(mount_path: str) -> tuple[str, str | None]:
    """Use a writable folder; on Windows avoid creating files directly in C:\\."""
    mp = os.path.abspath(os.path.expanduser(mount_path))
    if not os.path.isdir(mp):
        return mp, None
    if not _is_windows_drive_root(mp):
        return mp, None
    drive = os.path.splitdrive(mp)[0].upper()
    td = tempfile.gettempdir()
    if os.path.splitdrive(td)[0].upper() == drive:
        return td, "temp_same_drive"
    wt = os.path.join(mp.rstrip("\\"), "Windows", "Temp")
    if os.path.isdir(wt):
        return wt, "windows_temp"
    pub = os.path.join(mp.rstrip("\\"), "Users", "Public")
    if os.path.isdir(pub):
        return pub, "users_public"
    return mp, None


def benchmark_mount(mount_path: str, *, size_mb: int = 16) -> dict[str, Any]:
    """Sequential write + read of a temp file under mount_path; returns MB/s."""
    mount_path = os.path.abspath(os.path.expanduser(mount_path))
    if not os.path.isdir(mount_path):
        return {"error": "not_a_directory"}

    bench_dir, bench_where = _bench_directory_for_path(mount_path)
    if not os.path.isdir(bench_dir):
        return {"error": "not_a_directory", "detail": bench_dir}

    size = max(4, min(64, size_mb)) * 1024 * 1024
    data = os.urandom(size)

    path = os.path.join(bench_dir, f".nodeadline_disk_bench_{os.getpid()}_{time.time_ns()}.tmp")
    t0 = time.perf_counter()
    try:
        try:
            with open(path, "wb", buffering=1024 * 1024) as f:
                f.write(data)
            t_write = time.perf_counter()
            with open(path, "rb") as f:
                _ = f.read()
            t_read = time.perf_counter()
        except OSError as e:
            return {
                "error": "bench_io_error",
                "detail": str(e)[:400],
            }
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    write_s = max(t_write - t0, 1e-9)
    read_s = max(t_read - t_write, 1e-9)
    mb = size / (1024 * 1024)
    out: dict[str, Any] = {
        "ok": True,
        "size_bytes": size,
        "write_mbps": round(mb / write_s, 2),
        "read_mbps": round(mb / read_s, 2),
        "duration_write_s": round(write_s, 4),
        "duration_read_s": round(read_s, 4),
    }
    if bench_where:
        out["bench_note"] = bench_where
        _notes = {
            "temp_same_drive": "Тест выполнен во временной папке на этом диске (в корень тома, например C:\\, запись обычно запрещена).",
            "windows_temp": "Использована папка Windows\\Temp.",
            "users_public": "Использована папка Users\\Public.",
        }
        out["bench_note_ru"] = _notes.get(bench_where, bench_where)
    return out
