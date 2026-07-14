"""The shared table: `scripts/gba_idle_loop_db.json`, keyed by the cart code.

This is the artifact. Everything else in this package exists to add a row to it, and the
firmware's table (`firmware/gba/gba_idle_loop.c`) is generated FROM it — so a row here is
a claim that will end up in a device's hands, and the only claim allowed is one that was
proven by running the game.

Fields that matter:

    game_code      the 4 chars at rom[0xAC]. The key. Never the filename.
    idle_verified  the pc handed to gpSP. Absent = no address (see idle_hunted).
    idle_drop      how much of the frame the skip took back, measured.
    exec_median    the game's real CPU work per frame WITH the skip, of 280,896.
    idle_hunted    we ran it and searched. A full frame of work with this set is the
                   GAME's answer ("it is this heavy"), not the probe's ("we failed").
    verify_tier    "R" = confirmed by RUNNING the rom. The ONLY tier that ships.
"""
from __future__ import annotations

import json
from pathlib import Path

#: The repo's table: scripts/gba_idle_loop_db.json, one level up from this package. The
#: docker image keeps the same shape (/app/scripts/idlefind/gbaidle + /app/scripts/…json),
#: so this one path is right in both. Overridable — the firmware repo, or a test, points
#: it elsewhere.
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "gba_idle_loop_db.json"

FRAME_CYCLES = 280896


def load(path: Path | None = None) -> dict[str, dict]:
    """The table, keyed by game code. Empty (never an exception) if it is unreadable —
    a missing table must degrade to 'measure it yourself', not take the app down."""
    try:
        rows = json.loads((path or DEFAULT_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {r["game_code"]: r for r in rows}


def measured(row: dict) -> bool:
    return bool(row.get("exec_median"))


def shippable_pc(row: dict) -> str | None:
    """The address, but ONLY from a row that earned it.

    verify_tier "R" is the gate. An address that was guessed and never executed is worse
    than none: gpSP would end the frame slice at somewhere that is not the wait loop.
    """
    if row.get("verify_tier") != "R":
        return None
    return row.get("idle_verified")


def upsert(rows: list[dict], code: str, **fields) -> list[dict]:
    """Add or update one game's row. Returns a NEW list; the input is not touched."""
    out = [dict(r) for r in rows]
    for row in out:
        if row["game_code"] == code:
            row.update(fields)
            return out
    out.append({"game_code": code, **fields})
    return out


def row_for(code: str, *, name: str | None, exec_cycles: int, idle_pc: str | None,
            idle_drop: float | None, how: str) -> dict:
    """The row a hunt produces. `idle_hunted` is the field that lets the UI stop saying
    'not measured' about a game we have actually searched and found nothing in."""
    row = {
        "game_code": code,
        "lib_name": name,
        "exec_median": exec_cycles,
        "has_idle": bool(idle_pc),
        "idle_hunted": True,
        "verify_how": how,
    }
    if idle_pc:
        row["idle_verified"] = idle_pc
        row["idle_drop"] = idle_drop
        row["verify_tier"] = "R"      # ran the rom, and the address demonstrably works
    return row


def save(rows: list[dict], path: Path | None = None) -> None:
    target = path or DEFAULT_PATH
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
