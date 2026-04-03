#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Git Bash: Windows Python cannot open /r/... — use drive path for Python only.
ROOT_PY="$ROOT"
if command -v cygpath >/dev/null 2>&1; then
	ROOT_PY="$(cygpath -w "$ROOT" 2>/dev/null | sed 's|\\|/|g' || echo "$ROOT")"
fi
STAGING="$ROOT/public/downloads"
mkdir -p "$STAGING"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cp -r apps libs "$TMP/"
rm -rf "$TMP/apps/installer"
find "$TMP" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
cp node_main.py requirements-node.txt nodeadline.example.json "$TMP/"
echo "waitress" > "$TMP/venv_import_probe.txt"
echo "cryptography" >> "$TMP/venv_import_probe.txt"
echo "jwt" >> "$TMP/venv_import_probe.txt"
VER=$(python3 -c "import json;print(json.load(open('$ROOT_PY/public/version.json')).get('version','2.0.0'))")
IB=$(python3 -c "import json;print(json.load(open('$ROOT_PY/public/version.json')).get('installer_build','') or '')")
echo "$VER" > "$TMP/release_version.txt"
echo "$VER" > "$ROOT/release_version.txt"
(
  cd "$TMP"
  tar czf "$STAGING/core-node-payload.tar.gz" \
    apps libs node_main.py requirements-node.txt nodeadline.example.json venv_import_probe.txt release_version.txt
)
HASH=$(sha256sum "$STAGING/core-node-payload.tar.gz" | awk '{print $1}')
SZ=$(stat -c%s "$STAGING/core-node-payload.tar.gz")
cat > "$STAGING/core-manifest.json" <<EOF
{
  "version": "${VER}",
  "artifacts": [
    {
      "path": "staging/core-node-payload.tar.gz",
      "url": "https://nodeadline.online/downloads/core-node-payload.tar.gz",
      "sha256": "${HASH}",
      "size": ${SZ}
    }
  ]
}
EOF
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 << PY
import json
from pathlib import Path

root = Path("$ROOT_PY")
vj = json.loads((root / "public" / "version.json").read_text(encoding="utf-8"))
p = root / "public" / "build.json"
p.write_text(
    json.dumps(
        {
            "version": vj.get("version", "2.0.0"),
            "installer_build": vj.get("installer_build") or "",
            "deploy_seq": int(vj.get("deploy_seq") or 0),
            "deployed_at_utc": str(vj.get("deployed_at_utc") or ""),
            "payload_sha256": "${HASH}",
            "payload_size": ${SZ},
            "built_at_utc": "${STAMP}",
        },
        indent=2,
        ensure_ascii=False,
    )
    + "\\n",
    encoding="utf-8",
)
print("build.json ->", p)
PY
echo "$STAGING/core-node-payload.tar.gz sha256=$HASH size=$SZ"
