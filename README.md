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

Windows `.exe`: **on Windows the installer defaults to hidden console + system tray** (no need for `-silent`). Cross-compile needs **CGO** and **MinGW** (`x86_64-w64-mingw32-gcc`). Use `tools/build_installers.sh` (sets `CC` automatically) or:  
`GOOS=windows GOARCH=amd64 CGO_ENABLED=1 CC=x86_64-w64-mingw32-gcc go build -o nodeadline-installer.exe .`  
Runtime: tray = left click opens dashboard, right = menu. **`-console`** / **`NODEADLINE_CONSOLE=1`** — show console (debug). **`-no-tray`** / **`NODEADLINE_NO_TRAY=1`** — no tray. **`-silent`** still forces quiet mode on any OS.

After a successful node start, the installer creates a **Start Menu** shortcut: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Nodeadline\Nodeadline.lnk` → current `.exe` with `-silent` (explicit; default on Windows is already silent). Set `NODEADLINE_NO_STARTMENU=1` to skip creating it.

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

### Локально (eschota / эта машина, без SSH)

Если мастер и nginx уже подняты у вас (например **eschota.nodeadline.online**), достаточно пересобрать и залить `public/` **здесь** — остальные ноды подтянут payload с master по обычному каналу. SSH на «главный» VPS для этого не нужен.

1. Скопируйте [`deploy_local.env.example`](deploy_local.env.example) → **`deploy_local.env`** (в `.gitignore`), задайте **`NODEADLINE_LOCAL_DEST`** — Windows-путь к каталогу, который отдаёт nginx как docroot для этого хоста. При необходимости **`NODEADLINE_VERIFY_BASE`** (по умолчанию `https://eschota.nodeadline.online`).
2. Из корня репозитория: **`deploy_local.bat`** — локально выполняется [`tools/ship.sh`](tools/ship.sh) (release + rsync в ваш каталог + проверка по HTTPS).
3. Patch в `public/version.json`: **`deploy_local.bat --bump-version`**.

### Одна кнопка на удалённый VPS по SSH (`deploy.bat`)

Когда репозиторий и nginx живут **на другом сервере**, а вы выкладываете с этой Windows-машины через `git push` + SSH:

1. Скопируйте [`deploy.env.example`](deploy.env.example) → **`deploy.env`**, укажите `DEPLOY_SSH`, `DEPLOY_REMOTE_DIR`, `NODEADLINE_LOCAL_DEST`. Опционально **`DEPLOY_SSH_IDENTITY`** — путь к приватному ключу (например `%USERPROFILE%\.ssh\id_ed25519`); если не задан и есть `%USERPROFILE%\.ssh\id_ed25519`, он подставится сам.
2. Нужен **SSH-ключ** к VPS и закоммиченные изменения в git (перед выкладкой выполняется `git push`).
3. Запуск: **`deploy.bat`** — на сервере: `git pull` → [`tools/ship.sh`](tools/ship.sh) → [`tools/restart_master.sh`](tools/restart_master.sh).
4. С поднятием patch-версии в `version.json`: **`deploy.bat --bump-version`**.

**Установщики и `public/downloads/builds/`** в `.gitignore`: после сборки на Windows ([`tools/build_installers.ps1`](tools/build_installers.ps1) + `tools/publish_installer_build.sh` + `tools/release_payload.sh` в Git Bash) залейте каталог `public/` на VPS: **`powershell -NoProfile -File tools/sync_public_scp.ps1`**, затем на сервере без повторного `release_payload`:  
`cd ~/nodeadline.online && export NODEADLINE_LOCAL_DEST=/var/www/nodeadline/public && ./tools/deploy_public.sh`  
и перезапуск мастера. Так `build_site_channel.py` (нужен `libtorrent` на сервере) обновит `/site/`, rsync положит файлы в nginx.

Без нужного `deploy.env` / `deploy_local.env` скрипт подскажет создать его из примера.

Серверный пайплайн вручную: `deploy/deploy-nodeadline.sh`, `deploy/nginx-nodeadline.online.conf`.

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
