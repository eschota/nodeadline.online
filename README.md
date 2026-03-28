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
