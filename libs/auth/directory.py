"""Публичный каталог пользователей + DNS-привязки (для /api/directory/v1/users на мастере)."""
from __future__ import annotations

from typing import Any

from libs.auth import dns_registry, users


def _urls_for_fqdn(fqdn: str) -> tuple[str, str]:
    fqdn = (fqdn or "").strip()
    if not fqdn:
        return "", ""
    return f"https://{fqdn}/", f"https://{fqdn}/site/"


def build_directory_entries() -> list[dict[str, Any]]:
    """
    Объединяет users.json и dns_bindings.json по google_sub ↔ ключу в bindings.
    Сортировка по username (lower).
    """
    rows: list[dict[str, Any]] = []
    user_list = users.list_users()
    bindings = dns_registry.load_all_bindings()
    subs_with_user: set[str] = set()

    for u in user_list:
        sub = str(u.get("google_sub") or "").strip()
        if sub:
            subs_with_user.add(sub)
        b = bindings.get(sub) if sub else None
        fqdn = str((b or {}).get("fqdn") or "").strip()
        base, site = _urls_for_fqdn(fqdn)
        rows.append(
            {
                "google_sub": sub,
                "username": str(u.get("username") or "").strip(),
                "email": str(u.get("email") or "").strip(),
                "name": str(u.get("name") or "").strip(),
                "picture": str(u.get("picture") or "").strip(),
                "created_at": str(u.get("created_at") or "").strip(),
                "fqdn": fqdn,
                "public_base_url": base,
                "public_site_url": site,
                "wan_ipv4": str((b or {}).get("wan_ipv4") or "").strip(),
                "dns_updated_at": str((b or {}).get("updated_at") or "").strip(),
            }
        )

    for sub, b in bindings.items():
        sub = str(sub).strip()
        if not sub or sub in subs_with_user:
            continue
        if not isinstance(b, dict):
            continue
        fqdn = str(b.get("fqdn") or "").strip()
        base, site = _urls_for_fqdn(fqdn)
        rows.append(
            {
                "google_sub": sub,
                "username": str(b.get("username") or "").strip(),
                "email": str(b.get("email") or "").strip(),
                "name": "",
                "picture": "",
                "created_at": "",
                "fqdn": fqdn,
                "public_base_url": base,
                "public_site_url": site,
                "wan_ipv4": str(b.get("wan_ipv4") or "").strip(),
                "dns_updated_at": str(b.get("updated_at") or "").strip(),
            }
        )

    rows.sort(key=lambda r: (r.get("username") or r.get("email") or r.get("google_sub") or "").lower())
    return rows
