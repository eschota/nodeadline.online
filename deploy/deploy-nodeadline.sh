#!/bin/bash
set -euo pipefail
ROOT="${NODEADLINE_ROOT:-/var/www/nodeadline}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
echo "Deploy from $REPO to $ROOT"
sudo mkdir -p "$ROOT"
sudo rsync -a --delete \
  --exclude '.venv' --exclude 'data' --exclude '__pycache__' \
  "$REPO/" "$ROOT/"
cd "$ROOT"
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export NODEADLINE_VERSION="${NODEADLINE_VERSION:-2.0.0}"
export NODEADLINE_DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# Конфиг мастера не в git: /root/master.json или $ROOT/master.json на сервере.
if [[ -z "${NODEADLINE_CONFIG:-}" ]]; then
  if [[ -f /root/master.json ]]; then
    export NODEADLINE_CONFIG="/root/master.json"
  elif [[ -f "$ROOT/master.json" ]]; then
    export NODEADLINE_CONFIG="$ROOT/master.json"
  else
    export NODEADLINE_CONFIG="/root/master.json"
  fi
fi
sudo mkdir -p "$ROOT/data"
sudo chown -R www-data:www-data "$ROOT/data" 2>/dev/null || true
echo "Restart master (systemd example):"
echo "  sudo systemctl restart nodeadline-master"
