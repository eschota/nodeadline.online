#!/usr/bin/env bash
# Мгновенно подложить public/site/ в активный каталог бандла (путь из site/active.json).
# После этого /site/ на ноде совпадает с репозиторием без ожидания торрента.
#
#   cd ~/nodeadline.online
#   ./tools/apply_public_site_to_runtime.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="${NODEADLINE_RUNTIME_DIR:-$ROOT/data}"
ACTIVE_JSON="$RUNTIME/site/active.json"
if [[ ! -f "$ACTIVE_JSON" ]]; then
  echo "Нет $ACTIVE_JSON — канал ещё не синкался. Дождитесь sync или задайте NODEADLINE_SITE_ROOT." >&2
  exit 1
fi
TARGET="$(python3 -c "import json;print(json.load(open('$ACTIVE_JSON')).get('root','').strip())" 2>/dev/null || true)"
if [[ -z "$TARGET" || ! -d "$TARGET" ]]; then
  echo "Некорректный root в $ACTIVE_JSON" >&2
  exit 1
fi
echo "rsync $ROOT/public/site/ -> $TARGET"
rsync -a --delete "$ROOT/public/site/" "$TARGET/"
echo "OK. Обновите страницу (Ctrl+F5)."
