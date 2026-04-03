#!/usr/bin/env bash
# Создать в public/downloads/ стабильные имена установщиков из текущего public/version.json
# (копии из builds/NNNN/…). Нужно после rsync, если алиасы ещё не созданы publish_installer_build.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 << PY
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

root = Path("$ROOT")
vj = root / "public" / "version.json"
data = json.loads(vj.read_text(encoding="utf-8"))
dl = root / "public" / "downloads"
pairs = [
    (data.get("url"), dl / "nodeadline-installer-windows-amd64.exe"),
    (data.get("linux_url"), dl / "nodeadline-installer-linux-amd64"),
    (data.get("darwin_url"), dl / "nodeadline-installer-darwin-arm64"),
]
for url, dest in pairs:
    if not url or not isinstance(url, str):
        print("skip (no url)", dest.name)
        continue
    path = urlparse(url).path.lstrip("/")
    if not path.startswith("downloads/"):
        print("skip (bad path)", url)
        continue
    src = root / "public" / path
    if not src.is_file():
        print("ERROR: missing", src, file=__import__("sys").stderr)
        raise SystemExit(1)
    shutil.copy2(src, dest)
    print("OK", dest.name, "<-", src.relative_to(root / "public"))
PY
