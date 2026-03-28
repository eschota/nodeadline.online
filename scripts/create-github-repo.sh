#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CFG="$ROOT/nodeadline.json"
if [[ ! -f "$CFG" ]]; then
  echo "Нет $CFG — скопируйте nodeadline.example.json и вставьте токен." >&2
  exit 1
fi
TOKEN="$(jq -r '.github.token // empty' "$CFG")"
NAME="$(jq -r '.project.name // "nodeadline.online"' "$CFG")"
if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
  echo "В nodeadline.json пустой github.token" >&2
  exit 1
fi
BODY=$(jq -nc --arg name "$NAME" \
  '{name:$name, description:$name, private:false, auto_init:false}')
RESP=$(curl -sS -w "\n%{http_code}" -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/user/repos \
  -d "$BODY")
CODE=$(echo "$RESP" | tail -n1)
JSON=$(echo "$RESP" | sed '$d')
echo "$JSON" | jq . 2>/dev/null || echo "$JSON"
if [[ "$CODE" != "201" ]]; then
  echo "HTTP $CODE (ожидали 201)" >&2
  exit 1
fi
echo "OK: репозиторий создан."
