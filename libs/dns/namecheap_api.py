"""
Minimal Namecheap domains.dns.setHosts client (XML over HTTPS).
"""
from __future__ import annotations

import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

PRODUCTION = "https://api.namecheap.com/xml.response"


class NamecheapError(Exception):
    pass


class NamecheapClient:
    def __init__(
        self,
        *,
        api_user: str,
        username: str,
        api_key: str,
        client_ip: str,
        sandbox: bool = False,
    ) -> None:
        self.api_user = api_user
        self.username = username
        self.api_key = api_key
        self.client_ip = client_ip
        self.base = "https://api.sandbox.namecheap.com/xml.response" if sandbox else PRODUCTION

    def _common_params(self) -> dict[str, str]:
        return {
            "ApiUser": self.api_user,
            "ApiKey": self.api_key,
            "UserName": self.username,
            "ClientIp": self.client_ip,
        }

    def call(self, command: str, extra: dict[str, str]) -> ET.Element:
        params = {**self._common_params(), **extra, "Command": command}
        q = urllib.parse.urlencode(params)
        url = f"{self.base}?{q}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=45) as resp:
            text = resp.read().decode()
        root = ET.fromstring(text)
        status = root.attrib.get("Status", "")
        if status.upper() != "OK":
            raise NamecheapError(f"API status={status}")
        return root

    def get_hosts_records(self, domain: str) -> list[dict[str, str]]:
        sld, _, tld = domain.partition(".")
        if not tld:
            raise NamecheapError("apex_domain must be like example.com")
        root = self.call("namecheap.domains.dns.getHosts", {"SLD": sld, "TLD": tld})
        out: list[dict[str, str]] = []
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag.lower() != "host":
                continue
            out.append({
                "HostId": str(elem.attrib.get("HostId", "")),
                "Name": str(elem.attrib.get("Name", "")),
                "Type": str(elem.attrib.get("Type", "")),
                "Address": str(elem.attrib.get("Address", "")),
                "MXPref": str(elem.attrib.get("MXPref", "10")),
                "TTL": str(elem.attrib.get("TTL", "300")),
            })
        return out

    def set_hosts_bulk(self, domain: str, hosts: list[dict[str, str]]) -> None:
        sld, _, tld = domain.partition(".")
        if not tld:
            raise NamecheapError("apex_domain must be like example.com")
        if len(hosts) > 50:
            raise NamecheapError("too many DNS hosts (max 50)")
        params: dict[str, str] = {"SLD": sld, "TLD": tld}
        for i, h in enumerate(hosts, start=1):
            sn = str(i)
            params[f"HostName{sn}"] = h.get("Name", "")
            params[f"RecordType{sn}"] = h.get("Type", "A")
            params[f"Address{sn}"] = h.get("Address", "")
            params[f"MXPref{sn}"] = h.get("MXPref", "10")
            params[f"TTL{sn}"] = h.get("TTL", "300")
        self.call("namecheap.domains.dns.setHosts", params)

    def set_hosts_a(self, *, domain: str, subdomain: str, address: str, ttl: int = 300) -> None:
        """Одна A-запись (устар.; лучше set_hosts_merged)."""
        self.set_hosts_merged(domain=domain, subdomain=subdomain, address=address, ttl=ttl)

    def set_hosts_merged(self, *, domain: str, subdomain: str, address: str, ttl: int = 300) -> None:
        """getHosts → заменить/добавить A для поддомена → setHosts, остальные записи сохраняются."""
        sub = str(subdomain).strip().lower()
        if not sub:
            raise NamecheapError("subdomain required")
        hosts = self.get_hosts_records(domain)
        kept = [
            h
            for h in hosts
            if not (h.get("Name", "").strip().lower() == sub and h.get("Type", "").upper() == "A")
        ]
        kept.append({
            "HostId": "",
            "Name": sub,
            "Type": "A",
            "Address": address,
            "MXPref": "10",
            "TTL": str(ttl),
        })
        self.set_hosts_bulk(domain, kept)


def client_from_config(cfg: dict[str, Any]) -> NamecheapClient | None:
    nc = cfg.get("namecheap") or {}
    if os.environ.get("NAMECHEAP_API_USER", "").strip():
        nc = dict(nc)
        nc["api_user"] = os.environ["NAMECHEAP_API_USER"].strip()
    if os.environ.get("NAMECHEAP_API_KEY", "").strip():
        nc = dict(nc)
        nc["api_key"] = os.environ["NAMECHEAP_API_KEY"].strip()
    if os.environ.get("NAMECHEAP_CLIENT_IP", "").strip():
        nc = dict(nc)
        nc["client_ip"] = os.environ["NAMECHEAP_CLIENT_IP"].strip()
    need = ("api_user", "username", "api_key", "client_ip")
    if any(not str(nc.get(k, "")).strip() for k in need):
        return None
    return NamecheapClient(
        api_user=str(nc["api_user"]).strip(),
        username=str(nc.get("username") or nc["api_user"]).strip(),
        api_key=str(nc["api_key"]).strip(),
        client_ip=str(nc["client_ip"]).strip(),
        sandbox=bool(nc.get("sandbox")),
    )
