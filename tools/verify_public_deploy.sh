#!/usr/bin/env bash
# Проверка: то, что лежит в /var/www/.../public, совпадает с тем, что отдаёт сайт по HTTPS.
# Если НЕ совпадает — nginx отдаёт не эти файлы (часто: весь трафик уходит в proxy_pass на :8765).
#
# Запуск на сервере:
#   ./tools/verify_public_deploy.sh
#   ./tools/verify_public_deploy.sh /var/www/nodeadline/public https://nodeadline.online
#
# Если на хосте не настроен DNS (curl: Could not resolve host), проверка повторяется с
# --resolve имя:443:127.0.0.1 (nginx на этой же машине). Иначе задайте IP:
#   NODEADLINE_VERIFY_RESOLVE_IP=147.45.169.78 ./tools/verify_public_deploy.sh
#
set -euo pipefail
PUBLIC_DIR="${1:-/var/www/nodeadline/public}"
BASE="${2:-https://nodeadline.online}"
BASE="${BASE%/}"

if [[ ! -f "$PUBLIC_DIR/version.json" ]]; then
  echo "Нет файла $PUBLIC_DIR/version.json — rsync не сюда или неверный путь." >&2
  exit 1
fi

HOST_ONLY="${BASE#https://}"
HOST_ONLY="${HOST_ONLY#http://}"
HOST_ONLY="${HOST_ONLY%%/*}"
RESOLVE_IP="${NODEADLINE_VERIFY_RESOLVE_IP:-127.0.0.1}"

curl_https() {
  local url="$1"
  if out=$(curl -fsS --max-time 15 "$url" 2>/dev/null); then
    printf '%s' "$out"
    return 0
  fi
  # На многих VPS не резолвится своё же имя снаружи — второй запрос с SNI на локальный nginx.
  echo "verify: повтор с --resolve ${HOST_ONLY}:443:${RESOLVE_IP} (первый curl к $url не удался)" >&2
  curl -fsS --max-time 15 --resolve "${HOST_ONLY}:443:${RESOLVE_IP}" "$url"
}

echo "=== Локально на диске ($PUBLIC_DIR/version.json) ==="
cat "$PUBLIC_DIR/version.json"
echo ""
echo "=== По HTTPS ($BASE/version.json) ==="
REMOTE="$(curl_https "$BASE/version.json")"
echo "$REMOTE"
echo ""

if [[ "$(cat "$PUBLIC_DIR/version.json")" == "$REMOTE" ]]; then
  echo "OK: JSON с сайта совпадает с файлом на диске."
else
  echo "ОШИБКА: сайт отдаёт другой version.json, чем лежит в $PUBLIC_DIR"
  echo "Исправь nginx: блоки location = /version.json и /downloads/ ДО location / { proxy_pass }."
  echo "Образец: deploy/nginx-nodeadline.online.conf"
  exit 1
fi

MAN="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['artifacts'][0]['sha256'])" "$PUBLIC_DIR/downloads/core-manifest.json" 2>/dev/null || true)"
if [[ -n "$MAN" ]]; then
  echo ""
  echo "=== core-manifest.json (первые 200 символов) с HTTPS ==="
  curl_https "$BASE/downloads/core-manifest.json" | head -c 200
  echo ""
fi

if [[ -f "$PUBLIC_DIR/downloads/nodeadline-installer-windows-amd64.exe" ]]; then
  echo ""
  echo "=== Стабильный URL Windows-установщика (HEAD) ==="
  if curl -fsS -o /dev/null -I --max-time 15 "$BASE/downloads/nodeadline-installer-windows-amd64.exe" 2>/dev/null \
    || curl -fsS -o /dev/null -I --max-time 15 --resolve "${HOST_ONLY}:443:${RESOLVE_IP}" "$BASE/downloads/nodeadline-installer-windows-amd64.exe"; then
    echo "OK: /downloads/nodeadline-installer-windows-amd64.exe отдаётся по HTTPS."
  else
    echo "ОШИБКА: на диске есть nodeadline-installer-windows-amd64.exe, но HTTPS не отдаёт (nginx / путь)." >&2
    exit 1
  fi
fi
