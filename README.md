# nodeadline.online (V2)

Monorepo: **master** (public site + OAuth + tracker + DNS API), **node** (local dashboard), **installer** (Go agent).

## Quick start (development)

**Master** (copy `master.example.json` → `master.json`, add secrets):

```bash
cd /root/nodeadline.online
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export NODEADLINE_CONFIG=./master.json
PORT=8765 python3 apps/master/main.py
```

**Node** (copy `nodeadline.example.json` → `nodeadline.json`):

```bash
export NODEADLINE_CONFIG=./nodeadline.json
python3 apps/node/main.py
```

**Installer** (build):

```bash
cd apps/installer && go build -o nodeadline-installer .
```

Windows `.exe` with **system tray** (`-silent`): cross-compile needs **CGO** and **MinGW** (`x86_64-w64-mingw32-gcc`). Use `tools/build_installers.sh` (sets `CC` automatically) or:  
`GOOS=windows GOARCH=amd64 CGO_ENABLED=1 CC=x86_64-w64-mingw32-gcc go build -o nodeadline-installer.exe .`  
Runtime: `-silent` hides the console and shows the tray (left click = open dashboard, right = menu). `-no-tray` keeps console behavior without tray.

## Config

- Server secrets: `master.json` (not in git). Example: `master.example.json`.
- Node: `nodeadline.json`. Example: `nodeadline.example.json`.
- Production credentials may live in `/root/nodeadline.json` on the VPS; point `NODEADLINE_CONFIG` there.
- OAuth (Google): в `master.json` → `oauth.google`, либо переменные `NODEADLINE_GOOGLE_CLIENT_ID` и `NODEADLINE_GOOGLE_CLIENT_SECRET` (если в JSON пусто). В Google Cloud для redirect URI укажите `https://nodeadline.online/oauth/google/callback` (см. `oauth.callback_base`).
- Публичный URL в дашборде ноды: по умолчанию **`http://`** для прямого доступа по IP:порту. Если перед нодой стоит HTTPS reverse-proxy, задайте `NODEADLINE_PUBLIC_URL_SCHEME=https`.

## Docs

- [docs/PROJECT.md](docs/PROJECT.md) — устройство проекта, компоненты, каналы обновлений, ссылки на остальную документацию
- [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)

## Deploy

See `deploy/deploy-nodeadline.sh` and `deploy/nginx-nodeadline.online.conf`.

Production: `export NODEADLINE_CONFIG=/root/nodeadline.json` (or copy secrets into `master.json` beside the repo).

### Payload release (local node auto-updates from this)

**На прод-сервере, где уже лежит репозиторий** — одна команда (пересборка payload + rsync в nginx + проверка):

```bash
cd ~/nodeadline.online && ./tools/ship.sh
```

С поднятием patch в `public/version.json`: `./tools/ship.sh --bump-version`

1. Build Go installers into `public/downloads/` (or run `tools/publish_installer_build.sh` after placing binaries). Скрипт также кладёт стабильные имена (`nodeadline-installer-windows-amd64.exe` и т.д.) в корень `downloads/`, чтобы старые ссылки и `install-nodeadline-linux.sh` не отдавали 404. Если билды уже в `builds/NNNN/`, но алиасов нет: `./tools/sync_stable_download_aliases.sh`.
2. Rebuild the Python payload tarball, `core-manifest.json`, and `SHA256SUMS`:

```bash
./tools/release_payload.sh              # or: ./tools/release_payload.sh --bump-version
```

3. Ship `public/` to the live site (served as static files by master):

```bash
export NODEADLINE_REMOTE=user@host:/var/www/nodeadline/public
./tools/push_public_release.sh
```

On user machines, the installer polls `version.json` + manifest; when the payload hash changes it restarts the node. The **dashboard** (`/site/`) updates when `site_channel.json` changes (background sync compares `bundle_sha256`); `ship.sh` / `deploy_public.sh` run `tools/build_site_channel.py` before rsync so both payload and UI ship together.

### Namecheap DNS API

`POST /api/dns/v1/claim-subdomain` (authenticated session) calls `setHosts` with a **single** A record for the label. This can **replace** all DNS hosts for the apex domain in some accounts; prefer a dedicated subdomain zone or extend the client to `getHosts` + merge before release.

### Wheel mirror

Populate `public/Nodeadline/Core/requirements/` with wheels for target Python/OS so the installer can run `pip install` with `--find-links` (see V2 installer).

## Legacy bootstrap (ранний репозиторий)

В корне сохранены каталоги **`namecheap/`** и **`scripts/`** из первых коммитов (отдельный минимальный клиент Namecheap и провижн DNS). В продакшене мастер использует **`libs/dns/namecheap_api.py`** и конфиг из `master.json`. Старые скрипты можно не трогать — они не мешают сборке V2.
