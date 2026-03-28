#!/usr/bin/env bash
set -euo pipefail
EXPECTED="${NODEADLINE_SERVER_IP:-147.45.169.78}"
DOMAIN="${NODEADLINE_DOMAIN:-nodeadline.online}"
EMAIL="${CERTBOT_EMAIL:-}"

act="$(dig +short "$DOMAIN" A @8.8.8.8 | tail -1)"
if [[ -z "$act" ]]; then
  echo "Нет A-записи для $DOMAIN — сначала DNS (provision_nodeadline.py)." >&2
  exit 1
fi
if [[ "$act" != "$EXPECTED" ]]; then
  echo "Сейчас $DOMAIN A=$act, ожидается $EXPECTED. Подождите распространения DNS." >&2
  exit 1
fi

if [[ -z "$EMAIL" ]]; then
  echo "Задайте CERTBOT_EMAIL=you@example.com для Let's Encrypt." >&2
  exit 1
fi

certbot --nginx \
  -d "$DOMAIN" -d "www.$DOMAIN" \
  --non-interactive --agree-tos -m "$EMAIL" \
  --redirect

echo "Готово. Проверьте: curl -sI https://$DOMAIN/"
