"""Aggregated dashboard stats: site channel bytes, torrent announce, master tracker ping."""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

from libs.site_sync.channel import channel_state_dict, site_status
from libs.site_sync import torrent_sync
from libs.site_sync.ffmpeg_sync import ffmpeg_vendor_status
from libs.torrent import worker as torrent_worker


def _tracker_ping(master_base: str) -> dict[str, Any]:
    url = f"{master_base.rstrip('/')}/api/torrent/v1/list"
    req = urllib.request.Request(url, headers={"User-Agent": "nodeadline-node/2-stats"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        n = len(data) if isinstance(data, list) else 0
        return {"ok": True, "registered_on_master": n}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def torrent_summary() -> dict[str, Any]:
    states = torrent_worker.all_states()
    out = []
    for s in states:
        row = dict(s)
        ts = row.get("last_announce")
        if isinstance(ts, (int, float)):
            row["last_announce_age_sec"] = max(0, int(time.time() - ts))
        else:
            row["last_announce_age_sec"] = None
        out.append(row)
    return {
        "announce": torrent_worker.announce_stats(),
        "shares": out,
        "peer_wire_accounting": False,
    }


def build_dashboard_stats(runtime_dir: str, master_base: str) -> dict[str, Any]:
    return {
        "ok": True,
        "site_channel": site_status(runtime_dir),
        "site_channel_state": channel_state_dict(runtime_dir),
        "ffmpeg_vendor": ffmpeg_vendor_status(runtime_dir),
        "libtorrent_session": torrent_sync.session_stats(),
        "torrent": torrent_summary(),
        "tracker_master": _tracker_ping(master_base),
    }
