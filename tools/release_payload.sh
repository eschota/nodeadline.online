#!/usr/bin/env bash
# Rebuild core-node-payload.tar.gz + core-manifest.json, refresh public/downloads/SHA256SUMS.
# Use after changing apps/node, libs, etc. Then deploy public/ to the master host so installer pulls updates.
#
# Usage:
#   ./tools/release_payload.sh              # rebuild with current public/version.json version field
#   ./tools/release_payload.sh --bump-version   # increment patch (2.0.3 -> 2.0.4) then rebuild
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ROOT_PY="$ROOT"
if command -v cygpath >/dev/null 2>&1; then
	ROOT_PY="$(cygpath -w "$ROOT" 2>/dev/null | sed 's|\\|/|g' || echo "$ROOT")"
fi

if [[ "${1:-}" == "--bump-version" ]]; then
  python3 << PY
import json
from pathlib import Path
p = Path("$ROOT_PY") / "public" / "version.json"
d = json.loads(p.read_text(encoding="utf-8"))
ver = str(d.get("version", "2.0.0")).strip()
base = ver.split("-")[0].strip()
parts = base.split(".")
while len(parts) < 3:
    parts.append("0")
try:
    parts[-1] = str(int(parts[-1]) + 1)
except ValueError:
    parts[-1] = "1"
d["version"] = ".".join(parts)
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("version ->", d["version"])
PY
fi

# Каждый релиз: +1 к deploy_seq и метка времени (видно в version.json / build.json после деплоя).
python3 << PY
import json
from datetime import datetime, timezone
from pathlib import Path

p = Path("$ROOT_PY") / "public" / "version.json"
d = json.loads(p.read_text(encoding="utf-8"))
n = int(d.get("deploy_seq") or 0) + 1
d["deploy_seq"] = n
d["deployed_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("deploy_seq ->", n, "| deployed_at_utc ->", d["deployed_at_utc"])
PY

"$ROOT/tools/build_payload.sh"

readarray -t ART < <(python3 << PY | tr -d '\r'
import json
import os
from pathlib import Path
from urllib.parse import urlparse

root = Path("$ROOT_PY")
d = json.loads((root / "public/version.json").read_text(encoding="utf-8"))
pad = str(d.get("installer_build") or "").strip().replace("\r", "")
if not pad:
    raise SystemExit("ERROR: installer_build missing in public/version.json")

def _basename_from_url(key: str) -> str:
    u = (d.get(key) or "").strip()
    if not u:
        return ""
    return os.path.basename(urlparse(u).path)

win = _basename_from_url("url")
lin = _basename_from_url("linux_url")
dar = _basename_from_url("darwin_url")
# Имена бинарников берём из URL (как в каталоге builds/NNNN/), иначе — из semver в version.
# Так можно поднять version при смене только Python payload, не пересобирая Go под новое имя файла.
if not (win and lin and dar):
    v = str(d.get("version", "2.0.0")).split("-")[0].strip().replace("/", "-")
    win = f"nodeadline-installer-windows-amd64-v{v}.exe"
    lin = f"nodeadline-installer-linux-amd64-v{v}"
    dar = f"nodeadline-installer-darwin-arm64-v{v}"

dl = root / "public/downloads"
for name in (win, lin, dar):
    print(str(dl / "builds" / pad / name))
print(pad)
print(win)
print(lin)
print(dar)
PY
)
F0="${ART[0]}"
F1="${ART[1]}"
F2="${ART[2]}"
PAD="${ART[3]}"
WIN="${ART[4]}"
LIN="${ART[5]}"
DAR="${ART[6]}"
DL="$ROOT/public/downloads"
for f in "$F0" "$F1" "$F2"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: missing $f — copy installers into builds/$PAD/ or run tools/publish_installer_build.sh first" >&2
    exit 1
  fi
done

(
  cd "$DL"
  sha256sum \
    "builds/$PAD/$WIN" \
    "builds/$PAD/$LIN" \
    "builds/$PAD/$DAR" \
    core-node-payload.tar.gz > SHA256SUMS
)

echo "OK: payload + manifest + SHA256SUMS (installer build $PAD). Deploy public/ to production next."
