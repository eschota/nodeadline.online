#!/usr/bin/env python3
"""
Serve public/ over HTTP so the Windows/Linux installer can pull version.json + manifest + payload
from your machine (no deploy to nodeadline.online).

Prerequisite: run ./tools/build_payload.sh once (Git Bash / WSL / Linux).

Then set environment variable for the installer process:
  NODEADLINE_BASE_URL=http://127.0.0.1:8099
Optionally delete runtime/last_payload_sha256.txt or set NODEADLINE_FORCE_PAYLOAD_SYNC=1.

Usage:
  python3 tools/serve_public_for_local_installer.py [port]
"""
from __future__ import annotations

import http.server
import os
import socketserver
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    public = root / "public"
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    man = public / "downloads" / "core-manifest.json"
    if not man.is_file():
        print(
            "Missing public/downloads/core-manifest.json — run: ./tools/build_payload.sh",
            file=sys.stderr,
        )
        sys.exit(1)
    os.chdir(public)
    bind = "127.0.0.1"
    print("Serving:", public)
    print("Set for installer: NODEADLINE_BASE_URL=http://127.0.0.1:%d" % port)
    print("Then restart installer or remove runtime/last_payload_sha256.txt")
    with socketserver.ThreadingTCPServer((bind, port), http.server.SimpleHTTPRequestHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
