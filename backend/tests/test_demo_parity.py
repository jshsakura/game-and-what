# -*- coding: utf-8 -*-
"""frontend/src/demo.js must agree with systems.py about the system list.

The GitHub Pages demo has no backend, so demo.js hard-codes what /api/systems would
return. That array is hand-copied, and it drifted: for a while it carried Atari Lynx as
`experimental: false` while the backend had it true, so the demo's default view offered
a system a default install would not show. Two more fields were stale alongside it.

Nothing catches that by running the app — the demo only breaks in the browser, on a
deploy nobody tests. So it is caught here instead.

When this fails, the fix is to regenerate the array from systems.py rather than to patch
the one field the diff mentions.
"""
import json
import os
import re
from pathlib import Path

DEMO_JS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "demo.js"


def _demo_systems() -> dict:
    src = DEMO_JS.read_text(encoding="utf-8")
    m = re.search(r"const SYSTEMS = (\[.*?\]);", src, re.S)
    assert m, "demo.js no longer declares `const SYSTEMS = [...]` — update this test"
    return {d["key"]: d for d in json.loads(m.group(1))}


def _backend_systems() -> dict:
    # The demo ships the FULL fork set and filters on `experimental` at request time
    # (demo.js: `DEMO_LAB ? SYSTEMS : SYSTEMS.filter(s => !s.experimental)`), so the
    # comparison has to be against every system, not the ones this deploy exposes.
    os.environ["GNW_EXPERIMENTAL_MODE"] = "true"
    from app.systems import SYSTEMS
    return {
        s.key: {
            "key": s.key, "name": s.name, "dirname": s.dirname,
            "exts": list(s.exts), "pico8": s.pico8, "experimental": s.experimental,
        }
        for s in SYSTEMS
    }


def test_demo_lists_exactly_the_backend_systems():
    demo, back = _demo_systems(), _backend_systems()
    assert set(demo) == set(back), (
        f"only in demo.js: {sorted(set(demo) - set(back))}\n"
        f"only in systems.py: {sorted(set(back) - set(demo))}"
    )


def test_demo_system_fields_match():
    """Field-by-field, because the field that drifted last time — `experimental` — is
    the one the demo FILTERS on. A wrong flag there changes which systems the demo
    shows, which is the difference between a preview and a false advertisement."""
    demo, back = _demo_systems(), _backend_systems()
    wrong = {k: {"demo": demo[k], "backend": back[k]}
             for k in set(demo) & set(back) if demo[k] != back[k]}
    assert not wrong, json.dumps(wrong, ensure_ascii=False, indent=2)
