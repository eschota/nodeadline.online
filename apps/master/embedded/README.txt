Шифрованные учётные данные Namecheap для мастера
================================================

1. Сгенерируйте ключ Fernet (храните только на сервере, не в git):
     python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

2. Подготовьте JSON с полями namecheap (как в master.example.json), например:
     { "namecheap": { "api_user": "...", "username": "...", "api_key": "...", "client_ip": "ВАШ_IPV4_ДЛЯ_WHITELIST_NAMECHEAP", "apex_domain": "nodeadline.online", "sandbox": false } }

3. Зашифруйте в файл namecheap.fernet:
     python3 tools/encrypt_namecheap_embedded.py --key "$KEY" --in secrets.json --out apps/master/embedded/namecheap.fernet

4. На сервере в systemd / окружении:
     export NODEADLINE_FERNET_KEY='<тот же ключ>'

Клиент IP в Namecheap: в панели Namecheap → Profile → Tools → API Access — whitelist IPv4 сервера мастера (запросы API идут с этого IP).
