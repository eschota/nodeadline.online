#!/usr/bin/env bash
# Скачивает Linux-установщик nodeadline и запускает (как curl ... | bash).
set -euo pipefail
BASE="${NODEADLINE_BASE:-https://nodeadline.online}"
URL="${BASE}/downloads/nodeadline-installer-linux-amd64"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$URL" -o "$TMP"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "$TMP" "$URL"
else
  echo "Need curl or wget" >&2
  exit 1
fi
chmod +x "$TMP"
exec "$TMP" "$@"
