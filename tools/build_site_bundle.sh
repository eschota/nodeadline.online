#!/usr/bin/env bash
# Обёртка: public/site/ → бандл (см. build_site_channel.py).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/tools/build_site_channel.py"
