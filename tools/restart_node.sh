#!/usr/bin/env bash
# Перезапуск локальной ноды (node_main.py / waitress) и проверка /health + /api/site/status.
# Запуск из корня репозитория (где лежит node_main.py) или из каталога установки ноды.
#
#   cd ~/nodeadline.online
#   export NODEADLINE_RUNTIME_DIR=/var/lib/nodeadline-node   # опционально
#   export NODEADLINE_CONFIG=/root/nodeadline.json
#   ./tools/restart_node.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export NODEADLINE_CONFIG="${NODEADLINE_CONFIG:-$ROOT/nodeadline.example.json}"
RUNTIME="${NODEADLINE_RUNTIME_DIR:-$ROOT/data}"
export NODEADLINE_RUNTIME_DIR="$RUNTIME"
LOG="${NODEADLINE_NODE_LOG:-/tmp/nodeadline-node.log}"

PORT="${PORT:-}"
if [[ -z "$PORT" && -f "$RUNTIME/runtime_state.json" ]]; then
  PORT="$(python3 -c "import json;print(json.load(open('$RUNTIME/runtime_state.json')).get('listen_port')or '')" 2>/dev/null || true)"
fi
PORT="${PORT:-28473}"

if pgrep -f "node_main.py" >/dev/null 2>&1; then
  echo "restart_node: останавливаю node_main.py"
  pkill -f "node_main.py" || true
  sleep 1
fi

echo "restart_node: стартую ноду (PORT=$PORT, runtime=$RUNTIME, лог: $LOG)"
export PORT="$PORT"
nohup python3 node_main.py >>"$LOG" 2>&1 &
disown || true
sleep 2

if curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo "restart_node: OK /health"
else
  echo "restart_node: /health не ответил — смотрите $LOG" >&2
  exit 1
fi

ACTUAL_PORT="$(python3 -c "import json;print(json.load(open('$RUNTIME/runtime_state.json')).get('listen_port')or '')" 2>/dev/null || true)"
ACTUAL_PORT="${ACTUAL_PORT:-$PORT}"

echo "restart_node: /api/site/status"
curl -fsS --max-time 5 "http://127.0.0.1:${ACTUAL_PORT}/api/site/status" | python3 -m json.tool || true
echo ""
echo "restart_node: готово — нода слушает порт ${ACTUAL_PORT} (не путайте со старым портом из другого запуска)."
echo "  PORT=${ACTUAL_PORT} ./tools/verify_node_server.sh"
echo "  curl -fsS -X POST http://127.0.0.1:${ACTUAL_PORT}/api/site/sync-now"
