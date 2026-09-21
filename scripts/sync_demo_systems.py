#!/usr/bin/env python3
"""Regenerate demo.js's static /api/systems payload from backend/app/systems.py."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO_JS = ROOT / "frontend" / "src" / "demo.js"
sys.path.insert(0, str(ROOT / "backend"))

from app.systems import SYSTEMS  # noqa: E402


payload = [
    {
        "key": system.key,
        "name": system.name,
        "dirname": system.dirname,
        "exts": list(system.exts),
        "pico8": system.pico8,
        "experimental": system.experimental,
    }
    for system in SYSTEMS
]

source = DEMO_JS.read_text(encoding="utf-8")
replacement = "const SYSTEMS = " + json.dumps(
    payload, ensure_ascii=False, separators=(",", ":")
) + ";"
updated, count = re.subn(r"const SYSTEMS = \[.*?\];", replacement, source, count=1)
if count != 1:
    raise SystemExit("demo.js does not contain exactly one static SYSTEMS array")
DEMO_JS.write_text(updated, encoding="utf-8")
