#!/usr/bin/env bash
# Скачать статические ffmpeg/ffprobe для Windows (essentials) и Linux (amd64),
# положить в vendor/ffmpeg/{windows,linux}/ — затем tools/build_ffmpeg_channel.py
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
W="$ROOT/vendor/ffmpeg/windows"
L="$ROOT/vendor/ffmpeg/linux"
mkdir -p "$W" "$L"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> Windows (Gyan ffmpeg-release-essentials, ffmpeg.exe + ffprobe.exe)"
WIN_ZIP="$TMP/ffmpeg-win.zip"
curl -fsSL -o "$WIN_ZIP" "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
unzip -q -j "$WIN_ZIP" "bin/ffmpeg.exe" "bin/ffprobe.exe" -d "$W"
echo "    -> $W/ffmpeg.exe"

echo "==> Linux amd64 static (johnvansickle)"
LIN_TAR="$TMP/fflinux.tar.xz"
curl -fsSL -o "$LIN_TAR" "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
tar -xJf "$LIN_TAR" -C "$TMP"
D="$(find "$TMP" -maxdepth 1 -type d -name 'ffmpeg-*-amd64-static' | head -1)"
if [[ -z "$D" || ! -d "$D" ]]; then
  echo "ERROR: unexpected archive layout under $TMP" >&2
  exit 1
fi
cp -f "$D/ffmpeg" "$D/ffprobe" "$L/"
chmod +x "$L/ffmpeg" "$L/ffprobe"
echo "    -> $L/ffmpeg"

echo "OK. Запустите: python3 tools/build_ffmpeg_channel.py (и deploy)."
