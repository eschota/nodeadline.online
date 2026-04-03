"""Завершение лишних процессов мастера (тот же репозиторий, другой PID)."""
from __future__ import annotations

import os
import time

import psutil


def _peer_port(p: psutil.Process) -> int:
    try:
        env = p.environ()
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
        return int(os.environ.get("PORT", "8765"))
    raw = str(env.get("PORT", "") or "").strip()
    if raw.isdigit():
        return int(raw)
    return 8765


def _is_peer_master_process(p: psutil.Process, root_abs: str, me: int, port: int) -> bool:
    if int(p.pid) == int(me):
        return False
    try:
        cl = p.cmdline() or []
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return False
    if not cl:
        return False
    cmd = " ".join(str(x) for x in cl)
    if "apps/master/main.py" not in cmd:
        return False
    if _peer_port(p) != int(port):
        return False
    try:
        cwd = os.path.normcase(os.path.abspath(os.path.realpath(p.cwd())))
    except (OSError, PermissionError, psutil.Error):
        return False
    root_n = os.path.normcase(root_abs)
    return cwd == root_n or cwd.startswith(root_n + os.sep)


def terminate_other_master_instances(root: str, port: int | None = None) -> list[int]:
    """SIGTERM, затем kill для других master с тем же корнем и тем же PORT (не трогает другой порт)."""
    root_abs = os.path.abspath(os.path.realpath(root))
    if port is None:
        port = int(os.environ.get("PORT", "8765"))
    me = os.getpid()
    killed: list[int] = []
    for p in psutil.process_iter():
        try:
            if not _is_peer_master_process(p, root_abs, me, port):
                continue
            p.terminate()
            killed.append(int(p.pid))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    time.sleep(0.35)
    for pid in killed:
        try:
            proc = psutil.Process(pid)
            if proc.is_running():
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return killed
