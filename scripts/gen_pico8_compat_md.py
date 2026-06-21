#!/usr/bin/env python3
"""Generate a shareable PICO-8 compatibility table (PICO8_COMPAT.md) from the
bundled compat sheet (backend/app/assets/pico8_compat.json).

The JSON is the source of truth used by the app at runtime; this script renders
it as Markdown so the community list can be browsed and shared on the repo. Run
by hand or daily via .github/workflows/pico8-compat-md.yml.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "backend" / "app" / "assets" / "pico8_compat.json"
OUT = ROOT / "PICO8_COMPAT.md"

# Display order + label/icon for each status. "good" first (most carts), then the
# degraded ones, ending with the ones that don't run.
STATUS_META = [
    ("good", "✅ Good", "Runs on the real Game & Watch."),
    ("partial", "🟡 Partial", "Runs, but with slowdown or occasional out-of-memory."),
    ("broken", "❌ Broken", "Does not run on the device (구동불가 — out of memory, etc.)."),
]


def load() -> dict:
    return json.loads(SRC.read_text(encoding="utf-8"))


def render(data: dict) -> str:
    by_status: dict[str, list[tuple[str, str]]] = {}
    for key, entry in data.items():
        status = (entry or {}).get("status") or "unknown"
        note = (entry or {}).get("note") or ""
        by_status.setdefault(status, []).append((key, note))

    lines: list[str] = []
    lines.append("# PICO-8 Compatibility on the Game & Watch")
    lines.append("")
    lines.append(
        "Community-curated runnability of PICO-8 carts on the Game & Watch z8lua "
        "engine. The device targets PICO-8 0.2.7, so the real limit is RAM "
        "(out-of-memory), not the API version."
    )
    lines.append("")
    lines.append(
        "> Auto-generated from `backend/app/assets/pico8_compat.json` — **do not "
        "edit this file by hand**; edit the JSON and regenerate with "
        "`python scripts/gen_pico8_compat_md.py`."
    )
    lines.append("")

    # Summary line: total + per-status counts.
    total = len(data)
    summary = " · ".join(
        f"{label} {len(by_status.get(key, []))}" for key, label, _ in STATUS_META
    )
    lines.append(f"**{total} carts** — {summary}")
    lines.append("")

    for key, label, desc in STATUS_META:
        carts = sorted(by_status.get(key, []), key=lambda kv: kv[0])
        if not carts:
            continue
        lines.append(f"## {label} ({len(carts)})")
        lines.append("")
        lines.append(f"_{desc}_")
        lines.append("")
        lines.append("| Cart | Note |")
        lines.append("| --- | --- |")
        for name, note in carts:
            lines.append(f"| `{name}` | {note} |")
        lines.append("")

    # Any unexpected status values — surface them rather than dropping silently.
    extra = [s for s in by_status if s not in {k for k, _, _ in STATUS_META}]
    for status in sorted(extra):
        carts = sorted(by_status[status], key=lambda kv: kv[0])
        lines.append(f"## {status} ({len(carts)})")
        lines.append("")
        lines.append("| Cart | Note |")
        lines.append("| --- | --- |")
        for name, note in carts:
            lines.append(f"| `{name}` | {note} |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    md = render(load())
    OUT.write_text(md, encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(md)} bytes)")


if __name__ == "__main__":
    main()
