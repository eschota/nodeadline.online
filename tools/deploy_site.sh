#!/usr/bin/env bash
# Полный цикл «видеть результат на сайте сразу»: payload + public + перезапуск master.
# Канал /site/: правки только в public/site/ → build_site_channel.py кладёт бандл и site_channel.json.
# Запускать на сервере из корня репозитория после серьёзных правок кода, смены версии, дизайна лендинга.
#
#   export NODEADLINE_LOCAL_DEST=/var/www/nodeadline/public
#   ./tools/deploy_site.sh
#   или из корня репозитория: ./deploy_site.sh
#
# Только пересобрать payload и rsync, без рестарта master:
#   NODEADLINE_SKIP_MASTER_RESTART=1 ./tools/deploy_site.sh
#
# С bump версии в version.json (релиз):
#   ./tools/deploy_site.sh --bump-version
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BUMP=0
for a in "$@"; do
  case "$a" in
    --bump-version) BUMP=1 ;;
    *) echo "Unknown arg: $a (use --bump-version)" >&2; exit 1 ;;
  esac
done

if [[ "$BUMP" -eq 1 ]]; then
  "$ROOT/tools/release_payload.sh" --bump-version
else
  "$ROOT/tools/build_payload.sh"
fi

python3 "$ROOT/tools/build_site_channel.py"

LOCAL="${NODEADLINE_LOCAL_DEST:-}"
if [[ -z "$LOCAL" ]]; then
  echo "deploy_site: задайте NODEADLINE_LOCAL_DEST=/var/www/nodeadline/public" >&2
  exit 1
fi
sudo rsync -a --delete --info=stats2 "$ROOT/public/" "$LOCAL/"

"$ROOT/tools/restart_master.sh"

echo ""
echo "deploy_site: готово. Проверка: $ROOT/tools/verify_public_deploy.sh"
