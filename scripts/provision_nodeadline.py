#!/usr/bin/env python3
"""
Namecheap production: проверка домена, при необходимости регистрация,
затем A-записи @ и www на server_ipv4.

Запуск из корня репозитория:
  cd /root/nodeadline.online
  export NAMECHEAP_API_USER=логин_namecheap   # если пусто в nodeadline.json
  python3 scripts/provision_nodeadline.py

В панели Namecheap: API включён, IPv4 сервера в whitelist (тот же, что client_ip).
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.chdir(ROOT)

from namecheap.name_cheap_api import (  # noqa: E402
    DNSRecord,
    NamecheapError,
    load_client_from_json,
    whois_contact_from_dict,
)

REQUIRED_REGISTRANT = (
    "first_name",
    "last_name",
    "address1",
    "city",
    "state_province",
    "postal_code",
    "country",
    "phone",
    "email",
)


def _registrant_ready(reg: dict) -> list[str]:
    return [k for k in REQUIRED_REGISTRANT if not str(reg.get(k, "")).strip()]


def _dns_get_hosts_retry(client, apex: str, attempts: int = 8, delay: float = 4.0):
    last: NamecheapError | None = None
    for i in range(attempts):
        try:
            return client.dns_get_hosts(apex)
        except NamecheapError as e:
            last = e
            if i + 1 < attempts:
                time.sleep(delay)
    assert last is not None
    raise last


def main() -> int:
    cfg_path = os.environ.get("NODEADLINE_CONFIG", os.path.join(ROOT, "nodeadline.json"))
    with open(cfg_path, encoding="utf-8") as f:
        data = json.load(f)
    nc = data.get("namecheap") or {}
    apex = str(nc.get("apex_domain", "nodeadline.online")).strip()
    server_ip = str(nc.get("server_ipv4") or nc.get("client_ip") or "").strip()
    if not server_ip:
        print("Укажите namecheap.server_ipv4 или client_ip (IPv4 этого сервера).", file=sys.stderr)
        return 1

    try:
        client = load_client_from_json(cfg_path)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    print(f"Endpoint: {client.base_url}")
    print(f"Домен: {apex}  ->  A {server_ip} (@ и www)")

    chk = client.domains_check(apex)
    print("domains.check:", chk)
    avail = chk.get(apex)

    if avail is True:
        reg = nc.get("registrant") or {}
        miss = _registrant_ready(reg)
        if miss:
            print(
                "Домен свободен для покупки. Заполните в nodeadline.json → namecheap.registrant поля: "
                + ", ".join(miss),
                file=sys.stderr,
            )
            return 1
        whois = whois_contact_from_dict(reg)
        years = int(nc.get("registration_years", 1))
        print(f"Регистрация {apex} на {years} г. …")
        result = client.domains_create(apex, years, whois)
        print("domains.create:", result)
        time.sleep(5)

    try:
        current = _dns_get_hosts_retry(client, apex)
    except NamecheapError as e:
        print(
            f"dns.getHosts не удался: {e}\n"
            "Если домен уже куплен не на этом аккаунте Namecheap — перенесите DNS/домен.\n"
            "Если только что зарегистрировали — подождите и запустите скрипт снова.",
            file=sys.stderr,
        )
        return 2

    print(f"Текущих host-записей: {len(current)}")
    keep: list[DNSRecord] = []
    for r in current:
        if r.name in ("@", "www") and r.type in ("A", "CNAME", "ALIAS", "URL"):
            continue
        keep.append(r)
    keep.append(DNSRecord(name="@", type="A", address=server_ip, ttl="300"))
    keep.append(DNSRecord(name="www", type="A", address=server_ip, ttl="300"))
    out = client.dns_set_hosts(apex, keep)
    print("dns.setHosts:", out)
    print("\nДальше: дождаться DNS (TTL), проверить: dig +short", apex, "A")
    print("Затем TLS: ./scripts/enable_tls_nodeadline.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
