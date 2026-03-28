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
