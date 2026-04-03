#!/usr/bin/env bash
# Проверка канала /site/: мастер (site_channel.json + bundle) и опционально локальная нода (/api/site/status).
# Использование:
#   ./tools/verify_site_sync.sh
#   MASTER_BASE=https://nodeadline.online ./tools/verify_site_sync.sh
#   NODE_BASE=http://127.0.0.1:37651 ./tools/verify_site_sync.sh
set -euo pipefail
MASTER_BASE="${MASTER_BASE:-https://nodeadline.online}"
NODE_BASE="${NODE_BASE:-}"

echo "=== Master: ${MASTER_BASE}/site_channel.json ==="
CH_JSON="$(mktemp)"
trap 'rm -f "$CH_JSON"' EXIT
if ! curl -fsS -o "$CH_JSON" "${MASTER_BASE}/site_channel.json?cb=$(date +%s)"; then
  echo "ERROR: не удалось скачать site_channel.json" >&2
  exit 1
fi
BUNDLE_URL="$(python3 -c "import json;print((json.load(open('$CH_JSON')).get('bundle_url') or '').strip())")"
python3 << PY
import json
with open("$CH_JSON", encoding="utf-8") as f:
    d = json.load(f)
rev = d.get("revision")
sha = (d.get("bundle_sha256") or "").strip()
print("revision:", rev)
print("bundle_sha256:", sha[:16] + "…" if len(sha) > 16 else sha)
print("bundle_url:", (d.get("bundle_url") or "").strip())
PY
if [[ -n "$BUNDLE_URL" ]]; then
  echo ""
  echo "=== HEAD bundle (доступность) ==="
  if curl -fsSI -o /dev/null "$BUNDLE_URL"; then
    echo "OK: bundle отвечает"
  else
    echo "ERROR: bundle_url недоступен" >&2
    exit 1
  fi
fi

if [[ -n "$NODE_BASE" ]]; then
  echo ""
  echo "=== Node: ${NODE_BASE}/api/site/status ==="
  curl -fsS "${NODE_BASE}/api/site/status" | python3 -m json.tool || true
fi

echo ""
echo "Готово."
