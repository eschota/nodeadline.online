#!/usr/bin/env bash
# Populate public/Nodeadline/Core/requirements/ with wheels for all platforms the installer supports.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/public/Nodeadline/Core/requirements"
REQ="$ROOT/requirements-node.txt"
mkdir -p "$DEST"
# Do not `pip install` into system Python (PEP 668); pip download works without upgrading pip.
# miniupnpc has no arm64 macOS wheels on PyPI — mac gets deps without it; UPnP on Mac may need manual port.
REQ_NOMINI="$(mktemp)"
grep -v '^miniupnpc' "$REQ" > "$REQ_NOMINI"
trap 'rm -f "$REQ_NOMINI"' EXIT
for PY in 310 311 312 313; do
  python3 -m pip download -r "$REQ" -d "$DEST" \
    --platform win_amd64 --python-version "$PY" --implementation cp --abi "cp${PY}" --only-binary=:all:
  python3 -m pip download -r "$REQ" -d "$DEST" \
    --platform manylinux2014_x86_64 --python-version "$PY" --implementation cp --abi "cp${PY}" --only-binary=:all:
  python3 -m pip download -r "$REQ_NOMINI" -d "$DEST" \
    --platform macosx_11_0_arm64 --python-version "$PY" --implementation cp --abi "cp${PY}" --only-binary=:all:
done
echo "Wheels in $DEST ($(du -sh "$DEST" | cut -f1))"
