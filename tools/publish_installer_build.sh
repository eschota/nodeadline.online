#!/usr/bin/env bash
# Bump sequential installer build (0001, 0002, …), copy binaries into public/downloads/builds/NNNN/,
# update public/version.json URLs so each release has a unique URL (cache-busting).
# Filenames include semver from version.json, e.g. nodeadline-installer-windows-amd64-v2.0.6.exe.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT_PY="$ROOT"
if command -v cygpath >/dev/null 2>&1; then
	ROOT_PY="$(cygpath -w "$ROOT" 2>/dev/null | sed 's|\\|/|g' || echo "$ROOT")"
fi
DL="$ROOT/public/downloads"
BF="$DL/installer_build.txt"
LAST=$(cat "$BF" 2>/dev/null || echo 0)
LAST=$((10#${LAST:-0}))
NEXT=$((LAST + 1))
PAD=$(printf '%04d' "$NEXT")
DEST="$DL/builds/$PAD"
mkdir -p "$DEST"

readarray -t NAMES < <(python3 << PY | tr -d '\r'
import json
from pathlib import Path
root = Path("$ROOT_PY")
v = json.loads((root / "public/version.json").read_text(encoding="utf-8"))["version"]
ver = v.split("-")[0].strip().replace("/", "-")
print(f"nodeadline-installer-windows-amd64-v{ver}.exe")
print(f"nodeadline-installer-linux-amd64-v{ver}")
print(f"nodeadline-installer-darwin-arm64-v{ver}")
PY
)
WIN="${NAMES[0]}"
LIN="${NAMES[1]}"
DAR="${NAMES[2]}"

for f in "$WIN" "$LIN" "$DAR"; do
  if [[ ! -f "$DL/$f" ]]; then
    echo "ERROR: missing $DL/$f - run tools/build_installers.sh first" >&2
    exit 1
  fi
  cp -a "$DL/$f" "$DEST/$f"
done
(
  cd "$DEST"
  sha256sum "$WIN" "$LIN" "$DAR" > SHA256SUMS
)
echo "$PAD" > "$BF"
BASE="${NODEADLINE_PUBLIC_BASE:-https://nodeadline.online}"
VJ="$ROOT/public/version.json"
export PAD BASE VJ WIN LIN DAR
python3 << 'PY'
import json, os
pad = os.environ["PAD"]
base = os.environ["BASE"].rstrip("/")
path = os.environ["VJ"]
win, lin, dar = os.environ["WIN"], os.environ["LIN"], os.environ["DAR"]
with open(path, encoding="utf-8") as f:
    d = json.load(f)
d["installer_build"] = pad
d["url"] = f"{base}/downloads/builds/{pad}/{win}"
d["linux_url"] = f"{base}/downloads/builds/{pad}/{lin}"
d["darwin_url"] = f"{base}/downloads/builds/{pad}/{dar}"
if not d.get("manifest_url"):
    d["manifest_url"] = f"{base}/downloads/core-manifest.json"
if not d.get("requirements_mirror"):
    d["requirements_mirror"] = f"{base}/Nodeadline/Core/requirements/"
with open(path, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
(
  cd "$DL"
  sha256sum \
    "builds/$PAD/$WIN" \
    "builds/$PAD/$LIN" \
    "builds/$PAD/$DAR" \
    core-node-payload.tar.gz > SHA256SUMS
)
# Стабильные имена в корне downloads/ — букмарки и install-nodeadline-linux.sh без смены URL при каждом билде.
cp -a "$DEST/$WIN" "$DL/nodeadline-installer-windows-amd64.exe"
cp -a "$DEST/$LIN" "$DL/nodeadline-installer-linux-amd64"
cp -a "$DEST/$DAR" "$DL/nodeadline-installer-darwin-arm64"
echo "Published installer build $PAD -> $DEST"
echo "Stable aliases: nodeadline-installer-windows-amd64.exe, nodeadline-installer-linux-amd64, nodeadline-installer-darwin-arm64"
echo "Updated $VJ"
