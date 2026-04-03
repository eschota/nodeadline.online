#!/usr/bin/env python3
"""Единый источник канала /site/: public/site/ → tar.gz + torrent + public/site_channel.json."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Правки только здесь — после deploy_site.sh то же дерево на мастере и в бандле для нод.
SRC = ROOT / "public" / "site"
OUT = ROOT / "public" / "downloads" / "site"


def _cleanup_old_bundles(out_dir: Path, keep_tgz: Path, keep_tor: Path) -> None:
    """Оставляем только текущий архив и .torrent — старые копии не копятся."""
    kt = keep_tgz.resolve()
    kto = keep_tor.resolve()
    for pattern in ("nodeadline-site-*.tar.gz", "nodeadline-site-*.torrent"):
        for p in out_dir.glob(pattern):
            try:
                if p.resolve() not in (kt, kto):
                    p.unlink()
            except OSError:
                pass
    stray = out_dir / "site_channel.json"
    if stray.is_file():
        try:
            stray.unlink()
        except OSError:
            pass


def main() -> None:
    if not (SRC / "index.html").is_file():
        print(
            "ERROR: нет public/site/index.html — канал /site/ правьте только в public/site/",
            file=sys.stderr,
        )
        sys.exit(1)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = subprocess.check_output(["date", "-u", "+%Y%m%dT%H%M%SZ"], text=True).strip()
    tgz_name = f"nodeadline-site-{stamp}.tar.gz"
    arc_base = OUT / f"nodeadline-site-{stamp}"
    shutil.make_archive(str(arc_base), "gztar", root_dir=str(SRC))
    tgz = Path(str(arc_base) + ".tar.gz")
    if not tgz.is_file():
        print("ERROR: archive not created", file=sys.stderr)
        sys.exit(1)
    raw = tgz.read_bytes()
    import hashlib

    h = hashlib.sha256(raw).hexdigest()
    sz = len(raw)
    ch_path = ROOT / "public" / "site_channel.json"
    rev = 0
    if ch_path.is_file():
        try:
            rev = int(json.loads(ch_path.read_text(encoding="utf-8")).get("revision", 0))
        except Exception:
            rev = 0
    rev += 1
    ver = json.loads((ROOT / "public" / "version.json").read_text(encoding="utf-8"))["version"]
    tor_name = tgz_name.replace(".tar.gz", ".torrent")
    tor_path = OUT / tor_name
    import libtorrent as lt

    parent = str(tgz.parent)
    fs = lt.file_storage()
    lt.add_files(fs, str(tgz))
    t = lt.create_torrent(fs)
    t.add_tracker("https://nodeadline.online/bt/announce")
    t.set_creator("nodeadline-site")
    try:
        t.add_url_seed(f"https://nodeadline.online/downloads/site/{tgz_name}")
    except Exception:
        pass
    lt.set_piece_hashes(t, parent)
    raw_tor = lt.bencode(t.generate())
    tor_path.write_bytes(raw_tor)
    ti = lt.torrent_info(lt.bdecode(raw_tor))
    magnet = lt.make_magnet_uri(ti)
    ih = str(ti.info_hash()).lower()
    d = {
        "revision": rev,
        "version": ver,
        "distribution_tier": "system_master",
        "sync_origin": "system_master",
        "bundle_url": f"https://nodeadline.online/downloads/site/{tgz_name}",
        "bundle_sha256": h,
        "bundle_bytes": sz,
        "torrent_url": f"https://nodeadline.online/downloads/site/{tor_name}",
        "magnet": magnet,
        "info_hash": ih,
        "built_at_utc": stamp,
    }
    ch_path.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _cleanup_old_bundles(OUT, tgz, tor_path)
    print(f"OK site revision={rev} info_hash={ih}")
    print(f"   source: {SRC}")
    print(f"   bundle: {tgz}")
    print(f"   torrent: {tor_path}")


if __name__ == "__main__":
    main()
