# Деплой nodeadline.online

Цель: **не валидировать файлы по одному**. Всё, что относится к ноде и сайту, попадает в выкладку через **скрипты** и **rsync целых деревьев**.

## Один шаг: сайт + payload + перезапуск лендинга

Чтобы **сразу** видеть результат на **nodeadline.online** и обновить payload для клиентов:

```bash
export NODEADLINE_LOCAL_DEST=/var/www/nodeadline/public
./tools/deploy_site.sh
```

Скрипт: `build_payload.sh` → синхронизация **всего** `public/` → **`restart_master.sh`** (иначе главная страница не обновится). Подробнее — **`.cursor/skills/deployrule/SKILL.md`** в проекте с правилами для агента или копия логики в репозитории.

Релиз с bump версии: `./tools/deploy_site.sh --bump-version` (нужны установщики в `downloads/builds/...`).

## Главная страница сайта (/) и payload ноды — это разное

| Что | Где код | Как обновляется |
|-----|---------|-----------------|
| **`https://nodeadline.online/`** (лендинг, OAuth, трекер) | **master** — `apps/master/`, процесс на сервере (обычно **waitress** на `:8765` за nginx) | На сервере: актуальный репозиторий (`git pull` или rsync) и **перезапуск процесса master**. Сюда **не** попадает автоматически то, что скачал установщик на ПК. |
| **`http://127.0.0.1:<порт>/`** (дашборд ноды) | **node** — в основном `apps/node/` из **`core-node-payload.tar.gz`** | Установщик на Windows/Linux тянет payload с сайта и перезапускает ноду — вы видите обновления **только здесь**. |

Логи **waitress** на вашем ПК относятся к **локальной ноде**, а не к сайту в интернете.

После правок **`apps/master/download_page.py`** обязательно: выкатить код на сервер и перезапустить master (или один процесс, который слушает `8765`).

## Что вообще видят пользователи и установщик

По HTTPS с `nodeadline.online` раздаётся каталог **`public/`** (после сборки): `version.json`, `downloads/*`, статика.  
Клиентский установщик качает оттуда манифест и `core-node-payload.tar.gz` — в архив попадает **всё**, что кладёт `tools/build_payload.sh`: целиком `apps/` и `libs/` плюс корневые файлы ноды (см. скрипт). Новые модули в этих деревьях **не нужно прописывать вручную**. Сам **HTML главной страницы домена** генерирует master из `download_page.py`, а не отдельный файл из `public/` (если вы не вынесли лендинг в статику отдельно).

## Быстрый деплой с сервера (рекомендуется)

Репозиторий уже лежит на машине, nginx смотрит на `/var/www/nodeadline/public`:

```bash
cd ~/nodeadline.online
git pull   # или rsync всего репо — см. ниже

export NODEADLINE_LOCAL_DEST=/var/www/nodeadline/public
./tools/deploy_public.sh --release
```

- **`--release`** — вызывает `release_payload.sh` (манифест, SHA256SUMS, payload) и копирует **весь** `public/` на сайт.
- **`--release --bump-version`** — то же плюс инкремент patch в `public/version.json`.

Проверка без ручного сравнения файлов:

```bash
./tools/verify_public_deploy.sh
```

### Канал `/site/` (статический дашборд на ноде)

Источник правок — **`public/site/`** в репозитории. Нода **не** читает его из git: она отдаёт файлы из распакованного бандла (`runtime…/site/rev-*`, путь в `active.json`). Пока **не** вырос `revision` в **`site_channel.json`** на мастере и нода **не** скачала новый `.tar.gz`, в браузере остаётся старый HTML.

Полный цикл на сервере (payload + бандл сайта + rsync `public/` + перезапуск master):

```bash
cd ~/nodeadline.online
git pull
export NODEADLINE_LOCAL_DEST=/var/www/nodeadline/public
./tools/deploy_site.sh
# или из корня репозитория: ./deploy_site.sh
```

Проверка мастера и опционально локальной ноды:

```bash
./tools/verify_site_sync.sh
NODE_BASE=http://127.0.0.1:37651 ./tools/verify_site_sync.sh
```

Сравните `revision` и `bundle_sha256` из вывода с тем, что отдаёт **`GET /api/site/status`** на ноде. Если revision на ноде отстаёт — синк ещё не завершился или мастер не обновлён; смотрите логи ноды (`site sync`).

**Локальная разработка без ожидания торрента:** задайте абсолютный путь к дереву статики (клон репозитория: `…/nodeadline.online/public/site`):

```bash
export NODEADLINE_SITE_ROOT=/path/to/nodeadline.online/public/site
```

Тогда нода отдаёт `/site/` из этого каталога; в **`/api/site/status`** будет поле **`"dev_site_override": true`**.

**Ручная подкладка распакованного канала** (как раньше): скопируйте содержимое `public/site/` в каталог из `active.json` → `root`, либо обновите `NODEADLINE_SITE_ROOT`.

Одной командой из корня репозитория на машине с нодой:

```bash
./tools/apply_public_site_to_runtime.sh
```

Если `release_payload.sh` ругается на отсутствие установщиков в `public/downloads/builds/<build>/`, см. раздел «Только код ноды» ниже.

## Деплой с ноутбука (два уровня)

### 1) Только выкладка на прод (что нужно пользователям)

После `git push` на сервере достаточно команд выше.  
Или с локальной машины: скопировать **весь** собранный `public/`:

```bash
export NODEADLINE_RSYNC_DEST='user@сервер:/var/www/nodeadline/public/'
cd /path/to/nodeadline.online
./tools/deploy_public.sh --release
```

`deploy_public.sh` делает `rsync -a --delete` **всего содержимого** `public/` — новые файлы/папки в `public/` подхватываются без списков.

### 2) Синхронизация всего репозитория на сервер (универсально)

Все новые файлы проекта подтягиваются одной командой; исключения только у типичного мусора (`.git`, venv, `__pycache__`, и т.д.):

```bash
export NODEADLINE_RSYNC_DEST='user@сервер:~/nodeadline.online/'
./tools/rsync_project_to_server.sh
```

На сервере затем:

```bash
ssh user@сервер
cd ~/nodeadline.online
export NODEADLINE_LOCAL_DEST=/var/www/nodeadline/public
./tools/deploy_public.sh --release
```

Правила исключений при необходимости дополняйте **только** в `tools/rsync_project_to_server.sh`, а не вручную по файлам.

## Только код ноды (без полного release)

Если `release_payload.sh` недоступен (нет бинарников установщиков в `builds/`):

```bash
./tools/build_payload.sh
sudo rsync -a --delete ./public/ /var/www/nodeadline/public/
```

`build_payload.sh` заново собирает `core-node-payload.tar.gz` и обновляет `core-manifest.json` из **текущего** `public/version.json`.

## Нода на том же сервере, что и nginx

Чтобы **тестировать тот же канал**, что и у клиентов, на VPS можно поднять процесс ноды (`node_main.py`). Она тянет **`site_channel.json`** и бандл с **`https://nodeadline.online`** так же, как ПК: отдельный **`NODEADLINE_RUNTIME_DIR`** (например `/var/lib/nodeadline-node`), **не** смешивать с `data` мастера.

- Пример unit: [`deploy/systemd/nodeadline-node.service.example`](systemd/nodeadline-node.service.example).
- Перезапуск и проверка с машины, где клон репозитория:

```bash
./tools/restart_node.sh
PORT=37651 ./tools/verify_node_server.sh
```

Форсировать одну попытку синка канала `/site/` (только **с localhost**, фоном):

```bash
curl -fsS -X POST http://127.0.0.1:37651/api/site/sync-now
```

После обновления **кода** ноды (`apps/node`, `libs`) всё равно нужен новый **payload** и перезапуск процесса; обновление **только статики** `/site/` на мастере подтягивается синком **без** перезапуска Python.

**Прод:** не задавайте **`NODEADLINE_SITE_ROOT`** — иначе нода отдаёт копию из пути вместо распакованного бандла и перестаёт совпадать с остальными нодами.

## Nginx

Статика должна отдаваться **до** `location / { proxy_pass }`, иначе `version.json` и `downloads/` уйдут в бэкенд и деплой «не будет виден». Образец: `deploy/nginx-nodeadline.online.conf`. После правок: `sudo nginx -t && sudo systemctl reload nginx`.

## Клиенты Windows

После смены SHA в манифесте установщик подтянет payload за ~30 с или после перезапуска; отдельно проверять файлы в клиенте не нужно.
