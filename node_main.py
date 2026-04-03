#!/usr/bin/env python3
"""Payload entry: run local node."""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("NODEADLINE_CONFIG", os.path.join(_ROOT, "nodeadline.json"))
# До импорта приложения: секрет сессии хранится в data/ (как runtime_state), а не только рядом с nodeadline.json.
os.environ.setdefault("NODEADLINE_RUNTIME_DIR", os.path.join(_ROOT, "data"))

from apps.node.main import main

if __name__ == "__main__":
    main()
