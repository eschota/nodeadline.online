#!/usr/bin/env bash
# Запуск из корня репозитория: ./deploy_site.sh
# (эквивалент ./tools/deploy_site.sh)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/tools/deploy_site.sh" "$@"
