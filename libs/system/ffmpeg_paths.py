"""Пути к ffmpeg/ffprobe: runtime vendor (торрент-синк) → payload vendor/ → PATH."""
from __future__ import annotations

import os
import shutil
import sys


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _runtime_dir() -> str:
    return os.environ.get("NODEADLINE_RUNTIME_DIR", "").strip()


def _bin_paths(kind: str) -> list[str]:
    """kind: ffmpeg | ffprobe"""
    win = sys.platform == "win32" or os.name == "nt"
    sub = "windows" if win else "linux"
    ext = ".exe" if win else ""
    name = f"{kind}{ext}"
    out: list[str] = []
    rt = _runtime_dir()
    if rt:
        out.append(os.path.join(rt, "vendor", "ffmpeg", sub, name))
    out.append(os.path.join(_repo_root(), "vendor", "ffmpeg", sub, name))
    return out


def _first_existing(candidates: list[str]) -> str | None:
    for p in candidates:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
        if os.path.isfile(p):
            return p
    return None


def ffmpeg_executable() -> str | None:
    hit = _first_existing(_bin_paths("ffmpeg"))
    if hit:
        return hit
    return shutil.which("ffmpeg")


def ffprobe_executable() -> str | None:
    hit = _first_existing(_bin_paths("ffprobe"))
    if hit:
        return hit
    return shutil.which("ffprobe")
