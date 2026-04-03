#!/usr/bin/env python3
"""vendor/ffmpeg → два tar.gz (win / linux) + торренты + public/ffmpeg_channel.json."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public" / "downloads" / "ffmpeg"
WIN = ROOT / "vendor" / "ffmpeg" / "windows"
LIN = ROOT / "vendor" / "ffmpeg" / "linux"


def _cleanup_old(out_dir: Path, keep: set[Path]) -> None:
    for pattern in ("nodeadline-ffmpeg-win-*.tar.gz", "nodeadline-ffmpeg-linux-*.tar.gz", "*.torrent"):
        for p in out_dir.glob(pattern):
            try:
                if p.resolve() not in keep:
                    p.unlink()
            except OSError:
                pass


def main() -> int:
    if not (WIN / "ffmpeg.exe").is_file() or not (WIN / "ffprobe.exe").is_file():
        print("ERROR: нет vendor/ffmpeg/windows/ffmpeg.exe и ffprobe.exe", file=sys.stderr)
        print("   Запустите: tools/fetch_vendor_ffmpeg.sh", file=sys.stderr)
        return 1
    if not (LIN / "ffmpeg").is_file() or not (LIN / "ffprobe").is_file():
        print("ERROR: нет vendor/ffmpeg/linux/ffmpeg и ffprobe", file=sys.stderr)
        print("   Запустите: tools/fetch_vendor_ffmpeg.sh", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = subprocess.check_output(["date", "-u", "+%Y%m%dT%H%M%SZ"], text=True).strip()
    import hashlib

    import libtorrent as lt

    ch_path = ROOT / "public" / "ffmpeg_channel.json"
    rev = 0
    if ch_path.is_file():
        try:
            rev = int(json.loads(ch_path.read_text(encoding="utf-8")).get("revision", 0))
        except Exception:
            rev = 0
    rev += 1
    ver = json.loads((ROOT / "public" / "version.json").read_text(encoding="utf-8"))["version"]

    def pack_one(name: str, inner: Path, platform_key: str) -> tuple[Path, str, int, str, str, str]:
        """tar.gz с корнем windows/ или linux/."""
        arc_base = OUT / f"nodeadline-ffmpeg-{name}-{stamp}"
        stage = Path(shutil.mkdtemp(prefix="ffpack-"))
        try:
            dest = stage / platform_key
            dest.mkdir(parents=True)
            if platform_key == "windows":
                shutil.copy2(inner / "ffmpeg.exe", dest / "ffmpeg.exe")
                shutil.copy2(inner / "ffprobe.exe", dest / "ffprobe.exe")
            else:
                shutil.copy2(inner / "ffmpeg", dest / "ffmpeg")
                shutil.copy2(inner / "ffprobe", dest / "ffprobe")
        except OSError as e:
            shutil.rmtree(stage, ignore_errors=True)
            raise e
        shutil.make_archive(str(arc_base), "gztar", root_dir=str(stage))
        shutil.rmtree(stage, ignore_errors=True)
        tgz = Path(str(arc_base) + ".tar.gz")
        raw = tgz.read_bytes()
        h = hashlib.sha256(raw).hexdigest()
        sz = len(raw)
        tor_name = tgz.name.replace(".tar.gz", ".torrent")
        tor_path = OUT / tor_name
        parent = str(tgz.parent)
        fs = lt.file_storage()
        lt.add_files(fs, str(tgz))
        t = lt.create_torrent(fs)
        t.add_tracker("https://nodeadline.online/bt/announce")
        t.set_creator("nodeadline-ffmpeg")
        try:
            t.add_url_seed(f"https://nodeadline.online/downloads/ffmpeg/{tgz.name}")
        except Exception:
            pass
        lt.set_piece_hashes(t, parent)
        raw_tor = lt.bencode(t.generate())
        tor_path.write_bytes(raw_tor)
        ti = lt.torrent_info(lt.bdecode(raw_tor))
        magnet = lt.make_magnet_uri(ti)
        ih = str(ti.info_hash()).lower()
        return tgz, h, sz, magnet, ih, tor_name

    w_tgz, w_h, w_sz, w_mag, w_ih, w_tor = pack_one("win", WIN, "windows")
    l_tgz, l_h, l_sz, l_mag, l_ih, l_tor = pack_one("linux", LIN, "linux")

    d = {
        "revision": rev,
        "version": ver,
        "distribution_tier": "system_master",
        "sync_origin": "system_master",
        "built_at_utc": stamp,
        "windows": {
            "bundle_url": f"https://nodeadline.online/downloads/ffmpeg/{w_tgz.name}",
            "bundle_sha256": w_h,
            "bundle_bytes": w_sz,
            "torrent_url": f"https://nodeadline.online/downloads/ffmpeg/{w_tor}",
            "magnet": w_mag,
            "info_hash": w_ih,
        },
        "linux": {
            "bundle_url": f"https://nodeadline.online/downloads/ffmpeg/{l_tgz.name}",
            "bundle_sha256": l_h,
            "bundle_bytes": l_sz,
            "torrent_url": f"https://nodeadline.online/downloads/ffmpeg/{l_tor}",
            "magnet": l_mag,
            "info_hash": l_ih,
        },
    }
    ch_path.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _cleanup_old(OUT, {w_tgz.resolve(), OUT / w_tor, l_tgz.resolve(), OUT / l_tor})
    print(f"OK ffmpeg_channel revision={rev}")
    print(f"   win:  {w_tgz.name} sha256={w_h[:16]}…")
    print(f"   linux: {l_tgz.name} sha256={l_h[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
