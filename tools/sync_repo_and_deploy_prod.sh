#!/usr/bin/env bash
# Один пайплайн: синхронизация репозитория на сервер + release + проверка (см. deploy/DEPLOY.md).
#
# С машины разработки (нужен SSH и NODEADLINE_RSYNC_DEST):
#   export NODEADLINE_RSYNC_DEST='user@host:~/nodeadline.online/'
#   ./tools/sync_repo_and_deploy_prod.sh
#
# На сервере, где уже лежит репозиторий:
#   export NODEADLINE_LOCAL_DEST=/var/www/nodeadline/public
#   ./tools/sync_repo_and_deploy_prod.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -n "${NODEADLINE_RSYNC_DEST:-}" ]]; then
  "$ROOT/tools/rsync_project_to_server.sh"
  DEST="${NODEADLINE_RSYNC_DEST}"
  SSH_HOST="${DEST%%:*}"
  REMOTE_DIR="${DEST#*:}"
  REMOTE_DIR="${REMOTE_DIR%/}"
  LOCAL_DEST="${NODEADLINE_LOCAL_DEST:-/var/www/nodeadline/public}"
  ssh "$SSH_HOST" bash -s -- "$REMOTE_DIR" "$LOCAL_DEST" <<'REMOTE'
set -euo pipefail
REL="$1"
LOC="$2"
# Путь после ':' в NODEADLINE_RSYNC_DEST часто вида ~/repo — тильда литеральная, не раскрывается локально.
if [[ "$REL" == '~/'* ]]; then
  cd "${HOME}/${REL:2}"
elif [[ "$REL" == '~' ]]; then
  cd "$HOME"
else
  cd "$REL"
fi
export NODEADLINE_LOCAL_DEST="$LOC"
./tools/deploy_public.sh --release
./tools/verify_public_deploy.sh
REMOTE
elif [[ -n "${NODEADLINE_LOCAL_DEST:-}" ]]; then
  "$ROOT/tools/deploy_public.sh" --release
  "$ROOT/tools/verify_public_deploy.sh"
else
  echo "Укажи NODEADLINE_RSYNC_DEST (синхрон репо + удалённый деплой) или NODEADLINE_LOCAL_DEST (деплой на этой машине)." >&2
  exit 1
fi
