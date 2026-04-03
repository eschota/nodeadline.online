#!/usr/bin/env python3
"""Шифрование JSON с namecheap → apps/master/embedded/namecheap.fernet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cryptography.fernet import Fernet


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", help="Fernet key (from Fernet.generate_key())")
    ap.add_argument("--in", dest="in_path", required=True, help="JSON file with namecheap block")
    ap.add_argument("--out", dest="out_path", required=True, help="Output ciphertext file")
    args = ap.parse_args()
    key = (args.key or "").strip().encode("ascii")
    if len(key) < 40:
        print("Use --key from: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"", file=sys.stderr)
        sys.exit(1)
    raw = Path(args.in_path).read_text(encoding="utf-8")
    json.loads(raw)
    f = Fernet(key)
    tok = f.encrypt(raw.encode("utf-8"))
    outp = Path(args.out_path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(tok.decode("ascii") + "\n", encoding="ascii")
    print("OK", outp, "bytes", len(tok))


if __name__ == "__main__":
    main()
