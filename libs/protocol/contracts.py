"""
Canonical contracts: master, node, installer, sync.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class RuntimeState:
    listen_host: str = "127.0.0.1"
    listen_port: int = 0
    expose_lan: bool = False
    public_port: int | None = None
    wan_ip: str | None = None
    upnp_status: str = "unknown"
    public_probe_status: str = "unknown"
    last_verified_at: str | None = None
    pid: int | None = None
    network_mode: str = "local"
    upnp_last_error: str | None = None
    port_last_diag: str | None = None
    dns_fqdn: str | None = None
    dns_status: str = "idle"
    dns_error: str | None = None
    dns_claimed_at: str | None = None
    dns_pipeline_stage: str = "idle"
    dns_public_https_url: str | None = None
    oauth_email: str | None = None
    oauth_bound_sub: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RuntimeState:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class ShareEntry:
    share_id: str
    local_path: str
    mount_path: str
    visibility: str = "public"
    owner_sub: str = ""
    created_at: str = ""
    scan_status: str = "pending"
    public_slug: str = ""
    snapshot_id: str = ""
    snapshot_revision: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ShareEntry:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class MediaJob:
    job_id: str
    share_id: str
    source_path: str
    media_type: str
    status: str = "pending"
    error: str = ""
    original_width: int = 0
    original_height: int = 0
    preview_width: int = 0
    preview_height: int = 0
    duration_sec: float = 0.0
    poster_path: str = ""
    preview_path: str = ""
    created_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReleaseManifest:
    version: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_json(cls, raw: str) -> ReleaseManifest:
        d = json.loads(raw)
        return cls(version=str(d.get("version", "")), artifacts=list(d.get("artifacts") or []))


@dataclass
class VersionInfo:
    version: str = ""
    url: str = ""
    linux_url: str = ""
    darwin_url: str = ""
    manifest_url: str = ""
    requirements_mirror: str = ""


@dataclass
class TorrentSnapshot:
    share_id: str
    snapshot_id: str
    revision: int
    infohash: str
    file_count: int
    total_bytes: int
    created_at: str = ""
    published: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UserIdentity:
    google_sub: str
    email: str = ""
    name: str = ""
    picture: str = ""
    username: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> UserIdentity:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class DeployInfo:
    version: str = ""
    deployed_at: str = ""
    role: str = "master"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n"
