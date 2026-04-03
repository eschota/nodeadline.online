#!/usr/bin/env bash
# Cross-compile installers into public/downloads/ with names derived from public/version.json "version"
# (e.g. nodeadline-installer-windows-amd64-v2.0.6.exe).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/apps/installer"
VER=$(python3 << PY
import json
from pathlib import Path
v = json.loads(Path("$ROOT/public/version.json").read_text(encoding="utf-8"))["version"]
print(v.split("-")[0].strip().replace("/", "-"))
PY
)
OUT="$ROOT/public/downloads"
mkdir -p "$OUT"
WIN="nodeadline-installer-windows-amd64-v${VER}.exe"
LIN="nodeadline-installer-linux-amd64-v${VER}"
DAR="nodeadline-installer-darwin-arm64-v${VER}"
export CGO_ENABLED=0
echo "build_installers: version=$VER -> $OUT"

# Windows: system tray (fyne.io/systray) requires CGO + MinGW when cross-compiling from Linux/macOS.
WIN_CC="${NODEADLINE_WINDOWS_CC:-}"
if [[ -z "$WIN_CC" ]]; then
  if command -v x86_64-w64-mingw32-gcc >/dev/null 2>&1; then
    WIN_CC=x86_64-w64-mingw32-gcc
  elif command -v x86_64-w64-mingw32-gcc-posix >/dev/null 2>&1; then
    WIN_CC=x86_64-w64-mingw32-gcc-posix
  fi
fi
if [[ -n "$WIN_CC" ]]; then
  echo "build_installers: Windows exe (CGO + CC=$WIN_CC)"
  GOOS=windows GOARCH=amd64 CGO_ENABLED=1 CC="$WIN_CC" go build -trimpath -ldflags "-s -w" -o "$OUT/$WIN" .
else
  echo "ERROR: Windows installer needs a MinGW compiler for the tray UI (e.g. apt install gcc-mingw-w64-x86-64)." >&2
  echo "       Set NODEADLINE_WINDOWS_CC to the mingw gcc if it is not on PATH." >&2
  exit 1
fi

GOOS=linux GOARCH=amd64 go build -trimpath -ldflags "-s -w" -o "$OUT/$LIN" .
GOOS=darwin GOARCH=arm64 go build -trimpath -ldflags "-s -w" -o "$OUT/$DAR" .
chmod -f a+x "$OUT/$LIN" "$OUT/$DAR" || true
echo "OK: $WIN $LIN $DAR"
