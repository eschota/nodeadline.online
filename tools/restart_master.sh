#!/usr/bin/env bash
# Перезапуск master (лендинг /, OAuth, трекер на :8765). Вызывать после правок apps/master/ или libs/, используемых мастером.
#
# Гарантия одного процесса: при наличии unit — systemctl restart; иначе flock + SIGTERM/SIGKILL всех
# python-процессов apps/master/main.py этого репо + при необходимости освобождение порта.
#
# Репозиторий: корень nodeadline.online (рядом с tools/).
#   ./tools/restart_master.sh
#
# Пропустить: NODEADLINE_SKIP_MASTER_RESTART=1
# Несколько инстансов (отладка): NODEADLINE_MASTER_ALLOW_MULTIPLE=1 в окружении процесса master
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "${NODEADLINE_SKIP_MASTER_RESTART:-0}" == "1" ]]; then
  echo "restart_master: пропуск (NODEADLINE_SKIP_MASTER_RESTART=1)"
  exit 0
fi

# master.json не в git; на VPS часто кладут в /root/master.json, локально — в корне репо.
if [[ -z "${NODEADLINE_CONFIG:-}" ]]; then
  if [[ -f /root/master.json ]]; then
    export NODEADLINE_CONFIG="/root/master.json"
  elif [[ -f "$ROOT/master.json" ]]; then
    export NODEADLINE_CONFIG="$ROOT/master.json"
  else
    export NODEADLINE_CONFIG="/root/master.json"
  fi
else
  export NODEADLINE_CONFIG
fi
LOG="${NODEADLINE_MASTER_LOG:-/tmp/nodeadline-master.log}"
MP="${PORT:-8765}"

LOCK_DIR="${NODEADLINE_MASTER_LOCK_DIR:-/run/lock}"
LOCK="$LOCK_DIR/nodeadline-master-restart.lock"
mkdir -p "$LOCK_DIR"
exec 200>"$LOCK"
if ! flock -w 120 200; then
  echo "restart_master: не удалось взять lock за 120 с ($LOCK) — другой рестарт?" >&2
  exit 1
fi

_restart_via_systemd() {
  if ! command -v systemctl >/dev/null 2>&1; then
    return 1
  fi
  systemctl cat nodeadline-master.service >/dev/null 2>&1
}

if _restart_via_systemd; then
  echo "restart_master: systemctl restart nodeadline-master"
  systemctl restart nodeadline-master
  sleep 1
  if curl -fsS --max-time 5 "http://127.0.0.1:${MP}/health" >/dev/null 2>&1; then
    echo "restart_master: OK /health"
    exit 0
  fi
  echo "restart_master: /health не ответил после systemd — см. journalctl -u nodeadline-master" >&2
  exit 1
fi

_kill_all_master_py() {
  local sig="$1"
  pkill "$sig" -f "[p]ython3.*apps/master/main.py" 2>/dev/null || true
  pkill "$sig" -f "[p]ython.*apps/master/main.py" 2>/dev/null || true
}

echo "restart_master: останавливаю все apps/master/main.py (TERM)"
_kill_all_master_py -TERM
sleep 1
_kill_all_master_py -KILL
sleep 0.5

if command -v fuser >/dev/null 2>&1; then
  if fuser "${MP}/tcp" >/dev/null 2>&1; then
    echo "restart_master: освобождаю порт ${MP}/tcp (fuser -k)"
    fuser -k "${MP}/tcp" 2>/dev/null || true
    sleep 0.5
  fi
fi

for _ in $(seq 1 30); do
  if ! ss -tlnp 2>/dev/null | grep -q ":${MP} "; then
    break
  fi
  sleep 0.2
done
if ss -tlnp 2>/dev/null | grep -q ":${MP} "; then
  echo "restart_master: внимание: порт ${MP} всё ещё занят — проверьте вручную (ss -tlnp)" >&2
fi

echo "restart_master: стартую master (лог: $LOG)"
nohup python3 apps/master/main.py >>"$LOG" 2>&1 &
disown || true
sleep 1

MC="$(pgrep -f 'apps/master/main.py' 2>/dev/null | wc -l | tr -d ' ')"
if [[ "${MC:-0}" =~ ^[0-9]+$ ]] && [[ "${MC:-0}" -gt 1 ]]; then
  echo "restart_master: внимание: найдено процессов master: $MC (ожидался 1)" >&2
fi

if curl -fsS --max-time 5 "http://127.0.0.1:${MP}/health" >/dev/null 2>&1; then
  echo "restart_master: OK /health"
else
  echo "restart_master: /health пока не ответил — смотрите $LOG" >&2
  exit 1
fi
