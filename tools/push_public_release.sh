#!/usr/bin/env bash
# Rsync public/ (version.json, downloads/*, Nodeadline mirror) to the live master tree.
#
# Required: NODEADLINE_REMOTE — e.g. root@your.vps:/var/www/nodeadline/public
# Optional: NODEADLINE_SSH (extra ssh options)
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE="${NODEADLINE_REMOTE:?Set NODEADLINE_REMOTE=user@host:/path/to/nodeadline/public}"
SSH_OPTS="${NODEADLINE_SSH:-}"
echo "rsync $ROOT/public/ -> $REMOTE"
rsync -avz --delete $SSH_OPTS "$ROOT/public/" "$REMOTE/"
