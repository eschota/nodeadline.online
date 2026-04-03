#!/usr/bin/env bash
# Синхронизация всего репозитория на сервер одной командой (без перечисления отдельных файлов).
# Новые каталоги и файлы подхватываются автоматически; исключается только мусор сборки.
#
#   export NODEADLINE_RSYNC_DEST="user@host:~/nodeadline.online/"
#   ./tools/rsync_project_to_server.sh
#
# Trailing slash у DEST важен: с slash — содержимое в целевую папку, без — папка внутрь родителя.
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DEST="${NODEADLINE_RSYNC_DEST:-}"
if [[ -z "$DEST" ]]; then
  echo "export NODEADLINE_RSYNC_DEST='user@host:путь/к/клону/'" >&2
  exit 1
fi

rsync -a --delete \
  --exclude='.git/' \
  --exclude='**/__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.venv/' \
  --exclude='venv/' \
  --exclude='node_modules/' \
  --exclude='*.db' \
  --exclude='.cursor/' \
  --exclude='.DS_Store' \
  "$ROOT/" "$DEST"

echo "OK: репозиторий синхронизирован в $DEST"
echo "Дальше на сервере: cd ~/nodeadline.online && ./tools/deploy_public.sh --release (см. deploy/DEPLOY.md)"
