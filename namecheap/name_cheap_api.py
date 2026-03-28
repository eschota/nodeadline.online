"""
Namecheap API client (XML over HTTPS).

Global query params on every call:
  ApiUser, ApiKey, UserName, ClientIp, Command

Docs: https://www.namecheap.com/support/api/intro/

Requires in Namecheap panel: API enabled + ClientIp whitelisted (IPv4 only).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Mapping

PRODUCTION_URL = "https://api.namecheap.com/xml.response"
SANDBOX_URL = "https://api.sandbox.namecheap.com/xml.response"

# Second-level TLDs for split_sld_tld (extend as needed)
_COMPOUND_TLDS: tuple[str, ...] = (
    "co.uk",
    "org.uk",
    "me.uk",
    "com.au",
    "net.au",
    "org.au",
    "co.nz",
    "com.br",
    "co.jp",
    "com.mx",
)


class NamecheapError(Exception):
    def __init__(self, message: str, *, errors: list[tuple[str, str]] | None = None):
        super().__init__(message)
        self.errors = errors or []


def split_sld_tld(domain: str) -> tuple[str, str]:
    """
    Split a registered domain into (SLD, TLD) for DNS commands.
    Example: example.com -> ("example", "com"); foo.co.uk -> ("foo", "co.uk").
    """
    d = domain.lower().strip().rstrip(".")
    if not d or "." not in d:
        raise ValueError(f"invalid domain: {domain!r}")
    for suf in sorted(_COMPOUND_TLDS, key=len, reverse=True):
        if d.endswith("." + suf):
            stem = d[: -len(suf) - 1]
            if not stem or "." in stem:
                break
            return stem, suf
    i = d.rfind(".")
    return d[:i], d[i + 1 :]


def _strip_ns(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[-1]
    return tag


def _xml_root(xml_bytes: bytes) -> ET.Element:
    return ET.fromstring(xml_bytes)


def _api_status(root: ET.Element) -> tuple[str, list[tuple[str, str]]]:
    status = root.attrib.get("Status", "")
    errors: list[tuple[str, str]] = []
    for el in root.iter():
        if _strip_ns(el.tag) != "Error":
            continue
        num = el.attrib.get("Number", "0")
        text = (el.text or "").strip()
        errors.append((num, text))
    return status, errors


@dataclass
class WhoisContact:
    first_name: str
    last_name: str
    address1: str
    city: str
    state_province: str
    postal_code: str
    country: str
    phone: str
    email: str
    organization: str = ""
    address2: str = ""
    job_title: str = ""
    phone_ext: str = ""
    fax: str = ""
    state_province_choice: str = ""

    def to_params(self, prefix: str) -> dict[str, str]:
        p = {
            f"{prefix}FirstName": self.first_name,
            f"{prefix}LastName": self.last_name,
            f"{prefix}Address1": self.address1,
            f"{prefix}City": self.city,
            f"{prefix}StateProvince": self.state_province,
            f"{prefix}PostalCode": self.postal_code,
            f"{prefix}Country": self.country,
            f"{prefix}Phone": self.phone,
            f"{prefix}EmailAddress": self.email,
        }
        if self.organization:
            p[f"{prefix}OrganizationName"] = self.organization
        if self.address2:
            p[f"{prefix}Address2"] = self.address2
        if self.job_title:
            p[f"{prefix}JobTitle"] = self.job_title
        if self.phone_ext:
            p[f"{prefix}PhoneExt"] = self.phone_ext
        if self.fax:
            p[f"{prefix}Fax"] = self.fax
        if self.state_province_choice:
            p[f"{prefix}StateProvinceChoice"] = self.state_province_choice
        return p


@dataclass
class DNSRecord:
    """One row for namecheap.domains.dns.setHosts (HostName*, RecordType*, Address*, ...)."""

    name: str
    type: str
    address: str
    ttl: str = "1800"
    mx_pref: str = ""
    associated_app_title: str = ""
    friendly_name: str = ""


def load_client_from_json(path: str | None = None) -> NamecheapClient:
    cfg_path = path or os.environ.get("NODEADLINE_CONFIG", "nodeadline.json")
    with open(cfg_path, encoding="utf-8") as f:
        data = json.load(f)
    nc = data.get("namecheap") or {}
    missing = [k for k in ("api_user", "api_key", "client_ip") if not str(nc.get(k, "")).strip()]
    if missing:
        raise ValueError(
            f"In {cfg_path} fill namecheap fields: {', '.join(missing)} (see nodeadline.example.json)"
        )
    api_user = str(nc["api_user"]).strip()
    return NamecheapClient(
        api_user=api_user,
        api_key=str(nc["api_key"]).strip(),
        username=str(nc.get("username") or api_user).strip(),
        client_ip=str(nc["client_ip"]).strip(),
        sandbox=bool(nc.get("sandbox", False)),
    )


class NamecheapClient:
    def __init__(
        self,
        api_user: str,
        api_key: str,
        username: str,
        client_ip: str,
        *,
        sandbox: bool = False,
        base_url: str | None = None,
        timeout: int = 120,
    ):
        self.api_user = api_user
        self.api_key = api_key
        self.username = username
        self.client_ip = client_ip
        self.base_url = base_url or (SANDBOX_URL if sandbox else PRODUCTION_URL)
        self.timeout = timeout

    def _global_params(self) -> dict[str, str]:
        return {
            "ApiUser": self.api_user,
            "ApiKey": self.api_key,
            "UserName": self.username,
            "ClientIp": self.client_ip,
        }

    def call(
        self,
        command: str,
        params: Mapping[str, Any] | None = None,
        *,
        method: str = "GET",
    ) -> ET.Element:
        merged: dict[str, str] = {**self._global_params(), "Command": command}
        if params:
            for k, v in params.items():
                if v is None:
                    continue
                merged[k] = str(v)
        data = urllib.parse.urlencode(merged).encode("utf-8")
        url = self.base_url
        if method.upper() == "GET":
            full = f"{url}?{data.decode()}"
            req = urllib.request.Request(full, method="GET")
        else:
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read()
        root = _xml_root(body)
        status, errors = _api_status(root)
        if status != "OK":
            msg = "; ".join(f"[{n}] {t}" for n, t in errors) or "Namecheap API error"
            raise NamecheapError(msg, errors=errors)
        return root

    def domains_check(self, *domain_names: str) -> dict[str, bool]:
        """namecheap.domains.check — returns {domain: available}."""
        if not domain_names:
            return {}
        root = self.call(
            "namecheap.domains.check",
            {"DomainList": ",".join(domain_names)},
        )
        out: dict[str, bool] = {}
        for el in root.iter():
            if _strip_ns(el.tag) != "DomainCheckResult":
                continue
            d = el.attrib.get("Domain", "")
            avail = (el.attrib.get("Available", "") or "").lower() == "true"
            out[d] = avail
        return out

    def domains_create(
        self,
        domain_name: str,
        years: int,
        registrant: WhoisContact,
        *,
        tech: WhoisContact | None = None,
        admin: WhoisContact | None = None,
        aux_billing: WhoisContact | None = None,
        promotion_code: str = "",
        nameservers: str = "",
        add_free_whoisguard: str = "no",
        wg_enabled: str = "no",
        extra: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """
        namecheap.domains.create (HTTP POST recommended).
        Replicates contact to Tech/Admin/AuxBilling if omitted.
        """
        tech = tech or registrant
        admin = admin or registrant
        aux_billing = aux_billing or registrant
        params: dict[str, str] = {
            "DomainName": domain_name,
            "Years": str(years),
            **registrant.to_params("Registrant"),
            **tech.to_params("Tech"),
            **admin.to_params("Admin"),
            **aux_billing.to_params("AuxBilling"),
            "AddFreeWhoisguard": add_free_whoisguard,
            "WGEnabled": wg_enabled,
        }
        if promotion_code:
            params["PromotionCode"] = promotion_code
        if nameservers:
            params["Nameservers"] = nameservers
        if extra:
            params.update({k: str(v) for k, v in extra.items()})
        root = self.call("namecheap.domains.create", params, method="POST")
        for el in root.iter():
            if _strip_ns(el.tag) != "DomainCreateResult":
                continue
            return dict(el.attrib)
        raise NamecheapError("domains.create: no DomainCreateResult in response")

    def dns_get_hosts(self, domain: str) -> list[DNSRecord]:
        """namecheap.domains.dns.getHosts"""
        sld, tld = split_sld_tld(domain)
        root = self.call(
            "namecheap.domains.dns.getHosts",
            {"SLD": sld, "TLD": tld},
        )
        records: list[DNSRecord] = []
        for el in root.iter():
            if _strip_ns(el.tag) != "host":
                continue
            a = el.attrib
            records.append(
                DNSRecord(
                    name=a.get("Name", "@"),
                    type=a.get("Type", "A"),
                    address=a.get("Address", ""),
                    ttl=a.get("TTL", "1800"),
                    mx_pref=a.get("MXPref", ""),
                    associated_app_title=a.get("AssociatedAppTitle", ""),
                    friendly_name=a.get("FriendlyName", ""),
                )
            )
        return records

    def dns_set_hosts(
        self,
        domain: str,
        records: list[DNSRecord],
        *,
        email_type: str = "",
    ) -> dict[str, str]:
        """
        namecheap.domains.dns.setHosts
        WARNING: records not included in the call are removed. Use dns_merge_record or pass full list.
        """
        sld, tld = split_sld_tld(domain)
        params: dict[str, str] = {"SLD": sld, "TLD": tld}
        if email_type:
            params["EmailType"] = email_type
        for i, r in enumerate(records, start=1):
            params[f"HostName{i}"] = r.name
            params[f"RecordType{i}"] = r.type
            params[f"Address{i}"] = r.address
            params[f"TTL{i}"] = r.ttl
            if r.mx_pref:
                params[f"MXPref{i}"] = r.mx_pref
            if r.associated_app_title:
                params[f"AssociatedAppTitle{i}"] = r.associated_app_title
        root = self.call(
            "namecheap.domains.dns.setHosts",
            params,
            method="POST",
        )
        for el in root.iter():
            if _strip_ns(el.tag) != "DomainDNSSetHostsResult":
                continue
            return dict(el.attrib)
        raise NamecheapError("setHosts: no DomainDNSSetHostsResult in response")

    def dns_merge_record(
        self,
        domain: str,
        new: DNSRecord,
        *,
        replace_if_same_host_and_type: bool = True,
    ) -> dict[str, str]:
        """
        Load current hosts, optionally drop rows with same HostName+RecordType as ``new``,
        append ``new``, then setHosts. Namecheap removes any host row not sent — always send full list.
        """
        current = self.dns_get_hosts(domain)
        if replace_if_same_host_and_type:
            kept = [r for r in current if not (r.name == new.name and r.type == new.type)]
        else:
            kept = list(current)
        kept.append(new)
        return self.dns_set_hosts(domain, kept)

    def ensure_subdomain(
        self,
        registered_domain: str,
        host_label: str,
        address: str,
        *,
        record_type: str = "A",
        ttl: str = "300",
    ) -> dict[str, str]:
        """
        Add or replace DNS for `host_label` on `registered_domain` (apex domain you own).
        Example: host_label='api', registered_domain='example.com' -> api.example.com
        """
        rec = DNSRecord(name=host_label, type=record_type, address=address, ttl=ttl)
        return self.dns_merge_record(registered_domain, rec, replace_if_same_host_and_type=True)

