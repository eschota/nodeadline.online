#!/usr/bin/env bash
# Выпуск / расширение Let's Encrypt: apex + *.nodeadline.online (DNS-01 через Namecheap).
# Зависимости ставятся в venv рядом (PEP 668 на Ubuntu).
# На сервере для автопродления certbot.timer нужен тот же плагин в системном Python:
#   sudo pip install --break-system-packages certbot-dns-namecheap
# и постоянный credentials-файл (см. /etc/letsencrypt/renewal/nodeadline.online-0001.conf).
# Переменные окружения (как в master.json → namecheap):
#   NAMECHEAP_API_USER  NAMECHEAP_USERNAME  NAMECHEAP_API_KEY  NAMECHEAP_CLIENT_IP
# Дополнительно:
#   CERTBOT_EMAIL       email для ACME (обязательно для --non-interactive)
#
set -euo pipefail

: "${NAMECHEAP_API_USER:?}"
: "${NAMECHEAP_USERNAME:?}"
: "${NAMECHEAP_API_KEY:?}"
: "${NAMECHEAP_CLIENT_IP:?}"
: "${CERTBOT_EMAIL:?}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv-certbot"
if [[ ! -x "$VENV/bin/certbot" ]]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q certbot certbot-dns-namecheap
fi

CRED="$(mktemp)"
chmod 600 "$CRED"
cleanup() { rm -f "$CRED"; }
trap cleanup EXIT

cat >"$CRED" <<EOF
dns_namecheap_username = ${NAMECHEAP_USERNAME}
dns_namecheap_api_key = ${NAMECHEAP_API_KEY}
dns_namecheap_client_ip = ${NAMECHEAP_CLIENT_IP}
EOF

# www.nodeadline.online входит в *.nodeadline.online (LE не даёт указывать www и wildcard вместе).
"$VENV/bin/certbot" certonly \
  -a dns-namecheap \
  --dns-namecheap-credentials "$CRED" \
  --dns-namecheap-propagation-seconds 90 \
  --non-interactive --agree-tos \
  -m "$CERTBOT_EMAIL" \
  --expand \
  -d nodeadline.online \
  -d '*.nodeadline.online'

echo "OK. Проверка: openssl x509 -in /etc/letsencrypt/live/nodeadline.online/fullchain.pem -noout -text | grep -A2 SAN"
