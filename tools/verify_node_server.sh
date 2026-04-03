#!/usr/bin/env bash
# Проверка ноды на сервере: health, статус канала /site/, опционально форс-синк (loopback).
# Порт по умолчанию читается из runtime_state.json (тот же каталог, что у запущенной ноды).
#
#   ./tools/verify_node_server.sh
#   NODEADLINE_RUNTIME_DIR=/var/lib/nodeadline-node ./tools/verify_node_server.sh
#   PORT=37651 ./tools/verify_node_server.sh          # только если уверены в порте
#   SYNC=1 ./tools/verify_node_server.sh
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME="${NODEADLINE_RUNTIME_DIR:-$REPO_ROOT/data}"

if [[ -z "${PORT:-}" && -f "$RUNTIME/runtime_state.json" ]]; then
  PORT="$(python3 -c "import json;print(json.load(open('$RUNTIME/runtime_state.json')).get('listen_port')or '')" 2>/dev/null || true)"
fi
PORT="${PORT:?Задайте PORT= или положите runtime_state.json в $RUNTIME (NODEADLINE_RUNTIME_DIR)}"
BASE="http://127.0.0.1:${PORT}"

echo "=== GET $BASE/health (runtime=$RUNTIME) ==="
if ! curl -fsS --max-time 5 "$BASE/health" | python3 -m json.tool; then
  echo "" >&2
  echo "Ошибка: порт $PORT не отвечает. Актуальный listen_port смотрите в:" >&2
  echo "  $RUNTIME/runtime_state.json" >&2
  echo "или в выводе ./tools/restart_node.sh" >&2
  exit 1
fi
echo ""
echo "=== GET $BASE/api/site/status ==="
curl -fsS --max-time 5 "$BASE/api/site/status" | python3 -m json.tool
echo ""
if [[ "${SYNC:-0}" == "1" ]]; then
  echo "=== POST $BASE/api/site/sync-now (фоновая подтяжка с мастера) ==="
  curl -fsS --max-time 5 -X POST "$BASE/api/site/sync-now" | python3 -m json.tool
  echo "(подождите и снова проверьте /api/site/status или /site/)"
fi
echo "Готово."
