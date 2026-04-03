"""Завершение лишних процессов той же установки ноды (другой PID, тот же корень)."""
from __future__ import annotations

import os
import time

import psutil


def _is_peer_node_process(p: psutil.Process, root_abs: str, me: int) -> bool:
    """Тот же продукт, та же папка установки; не текущий PID."""
    if int(p.pid) == int(me):
        return False
    try:
        cl = p.cmdline() or []
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return False
    if not cl:
        return False
    cmd = " ".join(str(x) for x in cl)
    nc = os.path.normcase
    entry = nc(os.path.join(root_abs, "node_main.py"))
    if entry and entry in nc(cmd):
        return True
    if "-m apps.node.main" not in cmd and "apps.node.main" not in cmd:
        return False
    try:
        cwd = nc(os.path.abspath(os.path.realpath(p.cwd())))
    except (OSError, PermissionError, psutil.Error):
        return False
    root_n = nc(root_abs)
    return cwd == root_n or cwd.startswith(root_n + os.sep)


def terminate_other_node_instances(root: str) -> list[int]:
    """SIGTERM, затем kill для других процессов этой установки (node_main.py или -m apps.node.main при cwd=root)."""
    root_abs = os.path.abspath(os.path.realpath(root))
    me = os.getpid()
    killed: list[int] = []
    for p in psutil.process_iter():
        try:
            if not _is_peer_node_process(p, root_abs, me):
                continue
            p.terminate()
            killed.append(int(p.pid))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    time.sleep(0.25)
    for pid in killed:
        try:
            proc = psutil.Process(pid)
            if proc.is_running():
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return killed
