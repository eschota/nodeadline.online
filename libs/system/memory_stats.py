"""Host RAM/swap, CPU, node RSS via psutil (Linux, Windows)."""
from __future__ import annotations

import os
from typing import Any

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None  # type: ignore


def host_memory_snapshot() -> dict[str, Any]:
    """Returns memory, swap, node_rss_bytes; on failure memory_error string and partial/null fields."""
    if psutil is None:
        return {
            "memory": None,
            "swap": None,
            "node_rss_bytes": None,
            "memory_error": "psutil not installed",
        }
    try:
        vm = psutil.virtual_memory()
        sm = psutil.swap_memory()
        proc = psutil.Process(os.getpid())
        rss = proc.memory_info().rss
        swap_pct = round(sm.percent, 1) if sm.total else 0.0
        cpu_pct = round(float(psutil.cpu_percent(interval=0.1)), 1)
        logical = psutil.cpu_count(logical=True) or 0
        physical = psutil.cpu_count(logical=False) or logical
        cpu: dict[str, Any] = {
            "percent": cpu_pct,
            "cores_logical": int(logical),
            "cores_physical": int(physical),
        }
        # getloadavg есть только на Unix; на Windows у os нет атрибута — не ловится как OSError.
        if hasattr(os, "getloadavg"):
            try:
                load1, load5, load15 = os.getloadavg()
                cpu["loadavg"] = [round(load1, 2), round(load5, 2), round(load15, 2)]
            except OSError:
                cpu["loadavg"] = None
        else:
            cpu["loadavg"] = None
        return {
            "memory": {
                "total": int(vm.total),
                "used": int(vm.used),
                "available": int(vm.available),
                "percent": round(vm.percent, 1),
            },
            "swap": {
                "total": int(sm.total),
                "used": int(sm.used),
                "free": int(sm.free),
                "percent": swap_pct,
            },
            "cpu": cpu,
            "node_rss_bytes": int(rss),
        }
    except Exception as e:
        return {
            "memory": None,
            "swap": None,
            "node_rss_bytes": None,
            "memory_error": str(e)[:200],
        }
