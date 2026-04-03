#!/usr/bin/env bash
# Снимок памяти: RAM/swap, сумма RSS процессов Cursor remote, топ процессов, нода (node_main).
# Использование:
#   ./tools/watch_memory.sh              # один снимок
#   ./tools/watch_memory.sh 30           # каждые 30 с (Ctrl+C стоп)
#
# На сервере с 6–8 GiB RAM типичная нагрузка: Cursor (несколько окон Remote) ~1.5–2.5 GiB RSS;
# нода (waitress + Python) обычно десятки–сотни MiB. Если падает OOM — смотрите journalctl -k | grep -i oom
set -euo pipefail

snap() {
  echo "=== $(date -Is) ==="
  free -h | head -2
  echo "--- cursor-server (remote IDE) RSS ---"
  ps -eo rss=,cmd --no-headers 2>/dev/null | awk '/\.cursor-server\/bin\// {s+=$1; n++} END {if (n) printf "~%.0f MiB (%d процессов)\n", s/1024, n; else print "нет"}'
  echo "--- node (node_main / waitress) RSS ---"
  # [p]ython — чтобы pgrep не матчил сам себя; не матчим bash-обёртки Cursor с текстом node_main в cmdline
  ps -eo rss=,args= -ww --no-headers 2>/dev/null | awk '
    /python.*node_main\.py/ && !/cursor-server|extglob.*node_main/ { s+=$1; n++ }
    END { if (n) printf "~%.0f MiB (%d процессов)\n", s/1024, n; else print "нет" }'
  pgrep -af -- '[p]ython.*node_main\.py' 2>/dev/null || true
  echo "--- top 8 по RSS (MiB) ---"
  ps -eo pid,rss,cmd --sort=-rss --no-headers | head -8 | awk '{printf "%6s %8.1f MiB %s\n", $1, $2/1024, substr($0, index($0,$3))}'
  echo ""
}

if [[ "${1:-}" =~ ^[0-9]+$ ]] && [[ "${1:-0}" -gt 0 ]]; then
  echo "watch_memory: интервал ${1}s (Ctrl+C выход)"
  while true; do
    snap
    sleep "$1"
  done
else
  snap
fi
