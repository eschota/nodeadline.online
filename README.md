# nodeadline.online

Пустой стартовый репозиторий.

## Создание репозитория на GitHub через API

Если `scripts/create-github-repo.sh` даёт **403 Resource not accessible by personal access token**, токен **не имеет права создавать репозитории**.

**Проще всего:** [Classic PAT](https://github.com/settings/tokens/new) с scope **`public_repo`** (для публичных реп) или **`repo`** (ещё и приватные). Подставьте токен в `nodeadline.json` → снова:

```bash
chmod +x scripts/create-github-repo.sh
./scripts/create-github-repo.sh
cd /root/nodeadline.online && git push -u origin main
```

**Fine-grained PAT:** при создании токена откройте **Repository access → All repositories** (или нужный уровень) и в **Repository permissions** включите **Administration: Read and write**; при необходимости добавьте связанные права на создание репозитория в блоке **Account permissions** (в интерфейсе GitHub смотрите подсказки к чекбоксам).

## Namecheap API

Модуль: `namecheap/name_cheap_api.py`. Настройки в `nodeadline.json` → секция `namecheap` (файл в `.gitignore`).

Обязательно в панели Namecheap: **API Access** включён, в **Whitelisted IPs** добавлен **IPv4** тот же, что в `client_ip` (часто публичный IP сервера, с которого идут запросы).

Запуск из корня репозитория:

```bash
PYTHONPATH=. python -c "from namecheap import NamecheapClient, load_client_from_json; c=load_client_from_json(); print(c.domains_check('example.com'))"
```

Для **продакшена** в `nodeadline.json` поставьте `"sandbox": false`.

## Сайт и DNS (nodeadline.online)

### Почему «не открывается» с браузера

Пока у домена в DNS **A** стоит **не IP вашего VPS** (часто **парковка Namecheap** `162.255.*` или редирект `namecheap-nginx`), запросы **не попадают** на этот сервер — nginx тут ни при чём. Проверка:

```bash
dig +short nodeadline.online A
# должно быть 147.45.169.78 (или ваш актуальный IP сервера)
```

Исправление: панель Namecheap → **Advanced DNS** (или `scripts/provision_nodeadline.py` с API) → **@** и **www** → **A** на IP сервера. После этого HTTP снаружи дойдёт до nginx; затем **certbot** для HTTPS.

### Статика и «версии»

Один вход на порту **80/443** даёт **nginx**: он по **пути URL** отдаёт разные каталоги (`/`, `/ai_metadata/`, позже можно `/v1/`, `/v2/`). Несколько процессов Python на **одном** порту без прокси не слушают — либо разные порты + nginx `proxy_pass`, либо один приложение с роутингом.

- **Статика:** каталог `public/` — корень сайта; стартовая страница гостя: **`default_user.html`** (директива `index`).
- **Черновик UI:** `/ai_metadata/ai.test.html`
- **Заготовка после логина:** `/nodeadline.html` (позже привязка к Google sub).

- **Nginx на сервере:** `deploy/nginx-nodeadline.online.conf` (копия лежит в `/etc/nginx/sites-available/nodeadline.online`).
- **Продакшен Namecheap:** `sandbox: false`, `client_ip` = публичный IPv4 сервера (тот же в whitelist Namecheap). Логин API: `api_user` в JSON или `export NAMECHEAP_API_USER=...`.

**Уже купленный домен** (как сейчас): скрипт только выставляет **A** для `@` и `www` на `server_ipv4`.

```bash
cd /root/nodeadline.online
export NAMECHEAP_API_USER=ваш_логин_namecheap   # если не заполнено в nodeadline.json
python3 scripts/provision_nodeadline.py
```

**Если домен ещё свободен** — заполните `namecheap.registrant` в `nodeadline.json` (реальные контакты WHOIS), тогда скрипт вызовет `domains.create`.

**HTTPS после того, как `dig nodeadline.online A` вернёт IP сервера:**

```bash
export CERTBOT_EMAIL=ваш@email
./scripts/enable_tls_nodeadline.sh
```
