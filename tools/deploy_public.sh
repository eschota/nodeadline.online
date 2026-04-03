#!/usr/bin/env bash
# Выгрузка public/ на сервер, откуда nodeadline.online отдаёт version.json, downloads/* и статику.
# Установщик на ПК пользователя качает оттуда version.json + core-manifest.json + payload.
#
# На том же сервере, где nginx (без SSH):
#   export NODEADLINE_LOCAL_DEST="/var/www/nodeadline/public"
#   ./tools/deploy_public.sh --release
#
# Поднять семвер (patch) и выложить payload (имена установщиков в SHA256SUMS — из url/linux_url/darwin_url):
#   export NODEADLINE_LOCAL_DEST="/var/www/nodeadline/public"
#   ./tools/deploy_public.sh --release --bump-version
# Новый набор .exe/без расширения под другой semver — publish_installer_build.sh после build_installers.
#
# Каждый --release вызывает release_payload: +1 к deploy_seq в version.json и новый build.json
# (нужен актуальный tools/release_payload.sh в репозитории).
#
# Новый номер установщика (0015→0016) и URL в version.json:
#   ./tools/publish_installer_build.sh
#   ./tools/deploy_public.sh --release
#
# С другой машины по SSH (если задан NODEADLINE_LOCAL_DEST, он имеет приоритет — сначала unset NODEADLINE_LOCAL_DEST):
#   export NODEADLINE_RSYNC_DEST="user@host:/var/www/nodeadline/public/"
#   ./tools/deploy_public.sh
#
# С пересборкой payload (после правок apps/, libs/):
#   ./tools/deploy_public.sh --release
#   ./tools/deploy_public.sh --release --bump-version
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DO_RELEASE=0
BUMP=0
for a in "$@"; do
  case "$a" in
    --release) DO_RELEASE=1 ;;
    --bump-version) BUMP=1 ;;
    *) echo "Unknown arg: $a (use --release, --bump-version)" >&2; exit 1 ;;
  esac
done

# --bump-version подразумевает пересборку артефактов
if [[ "$BUMP" -eq 1 ]]; then
  DO_RELEASE=1
fi

if [[ "$DO_RELEASE" -eq 1 ]]; then
  if [[ "$BUMP" -eq 1 ]]; then
    "$ROOT/tools/release_payload.sh" --bump-version
  else
    "$ROOT/tools/release_payload.sh"
  fi
fi

# Канал /site/ для нод: tar.gz + site_channel.json + revision. Иначе локальная нода держит старый UI
# (статика в public/site/ после rsync на nodeadline.online не подставляется в процесс — только бандл по SHA).
if [[ "${NODEADLINE_SKIP_SITE_BUNDLE:-0}" != "1" ]]; then
  echo "==> Канал /site/ (tools/build_site_channel.py)"
  python3 "$ROOT/tools/build_site_channel.py"
fi
# vendor/ffmpeg/{windows,linux} — отдельные торренты (tools/fetch_vendor_ffmpeg.sh)
if [[ "${NODEADLINE_SKIP_FFMPEG_CHANNEL:-0}" != "1" ]]; then
  if [[ -f "$ROOT/vendor/ffmpeg/windows/ffmpeg.exe" && -f "$ROOT/vendor/ffmpeg/linux/ffmpeg" ]]; then
    echo "==> Канал ffmpeg (tools/build_ffmpeg_channel.py)"
    python3 "$ROOT/tools/build_ffmpeg_channel.py"
  else
    echo "==> Канал ffmpeg: пропуск (нет vendor/ffmpeg — см. tools/fetch_vendor_ffmpeg.sh)"
  fi
fi

# Короткие URL /downloads/nodeadline-installer-*.exe|linux|darwin — копии из builds/NNNN/… (см. version.json)
SYNC_RC=0
ROOT="$ROOT" python3 << 'PY' || SYNC_RC=$?
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

root = Path(os.environ["ROOT"])
vj = root / "public" / "version.json"
if not vj.is_file():
    sys.exit(1)
try:
    data = json.loads(vj.read_text(encoding="utf-8"))
except OSError:
    sys.exit(1)
url = data.get("url")
if not url or not isinstance(url, str) or "/builds/" not in url:
    sys.exit(1)
rel = urlparse(url).path.lstrip("/")
if not (root / "public" / rel).is_file():
    sys.exit(2)
sys.exit(0)
PY
if [[ "$SYNC_RC" -eq 0 ]]; then
  echo "==> Стабильные имена в public/downloads/ (tools/sync_stable_download_aliases.sh)"
  "$ROOT/tools/sync_stable_download_aliases.sh"
elif [[ "$SYNC_RC" -eq 2 ]]; then
  echo "WARN: нет файла установщика из version.json (builds/…) — пропускаю стабильные алиасы. Нужны бинарники или publish_installer_build.sh" >&2
fi

LOCAL="${NODEADLINE_LOCAL_DEST:-}"
DEST="${NODEADLINE_RSYNC_DEST:-}"

if [[ -n "$LOCAL" ]]; then
  echo "rsync public/ -> $LOCAL (локально)"
  _uname_s="$(uname -s 2>/dev/null || true)"
  if [[ "${NODEADLINE_RSYNC_NO_SUDO:-0}" == "1" ]] || [[ "$_uname_s" == MINGW* ]] || [[ "$_uname_s" == MSYS* ]]; then
    rsync -a --delete --info=stats2 "$ROOT/public/" "$LOCAL/"
  else
    sudo rsync -a --delete --info=stats2 "$ROOT/public/" "$LOCAL/"
  fi
  unset _uname_s
elif [[ -n "$DEST" ]]; then
  echo "rsync public/ -> $DEST"
  rsync -a --delete --info=stats2 "$ROOT/public/" "$DEST"
else
  echo "Укажи куда копировать:" >&2
  echo "  На этом сервере:  export NODEADLINE_LOCAL_DEST=/var/www/nodeadline/public" >&2
  echo "  Удалённо по SSH: export NODEADLINE_RSYNC_DEST=user@host:/var/www/nodeadline/public/" >&2
  exit 1
fi

echo ""
echo "OK. Важно: nginx должен отдавать /version.json и /downloads/* с диска (см. deploy/nginx-nodeadline.online.conf),"
echo "     иначе весь сайт уходит в proxy на :8765 и rsync не виден снаружи."
echo "Проверка:  $ROOT/tools/verify_public_deploy.sh"
echo "На клиенте Windows: ~30–90 с — фоновый sync payload; после смены bundle_sha256 в site_channel.json — новый /site/ (дашборд)."
