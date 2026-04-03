#!/usr/bin/env bash
# Одна команда на сервере с репозиторием: пересборка Python payload + выкладка в nginx + проверка.
#
#   cd ~/nodeadline.online && ./tools/ship.sh
#
# Поднять patch-версию в version.json (когда нужен новый semver без новых Go-бинарников — см. deploy_public.sh):
#   ./tools/ship.sh --bump-version
#
# Другой каталог под nginx:
#   NODEADLINE_LOCAL_DEST=/var/www/nodeadline/public ./tools/ship.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export NODEADLINE_LOCAL_DEST="${NODEADLINE_LOCAL_DEST:-/var/www/nodeadline/public}"

EXTRA=()
for a in "$@"; do
  case "$a" in
    --bump-version) EXTRA+=(--bump-version) ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Неизвестный аргумент: $a (допустимо: --bump-version)" >&2
      exit 1
      ;;
  esac
done

echo "==> NODEADLINE_LOCAL_DEST=$NODEADLINE_LOCAL_DEST"
"$ROOT/tools/deploy_public.sh" --release "${EXTRA[@]}"
VERIFY_DIR="${NODEADLINE_VERIFY_PUBLIC_DIR:-${NODEADLINE_LOCAL_DEST:-/var/www/nodeadline/public}}"
VERIFY_BASE="${NODEADLINE_VERIFY_BASE:-https://nodeadline.online}"
"$ROOT/tools/verify_public_deploy.sh" "$VERIFY_DIR" "$VERIFY_BASE"
echo ""
echo "OK: nodeadline.online отдаёт свежий public/. Ноды: Python payload по core-manifest; дашборд /site/ по site_channel.json (bundle_sha256)."
