"""Give every GBA rom the measurements we already have.

`scripts/gba_idle_loop_db.json` is a public good: 500-odd game codes hunted on real
runs — the idle-loop address gpSP needs, the cycles a game works per frame, and the
sound driver the firmware replaces with a native mixer. It ships inside the image. But
until now it only reached a rom's row if someone ran `gba_measure.py` by hand, so a
person who pulled the Docker image and dropped their GBA romset in saw cards that said
"측정 중" forever and never the mixer verdict at all — data we HAD and simply were not
handing over.

This stamps the table onto every matching row at startup, keyed by the cart's game code
(never the filename — a library renames those). It is the automatic form of
`gba_measure.py`, which now calls straight through to it.

Two things it will NOT do:
  * Touch a rom the table does not know. A rom this deployment measured live but that has
    not been folded back into the shipped table (see gba_export.py) is the local truth;
    blanking it would throw that measurement away and make the game look unknown again.
  * Rewrite a row that already matches. The comparison keeps startup a no-op once the
    library has converged, so a restart does not churn every card.
"""
from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection

from . import gba_probe, storage
from .. import config

SYSTEM = "gba"


def _entry_columns(entry: dict) -> dict:
    """The rom-row values a measured table entry maps to.

    Only a RUN-verified address (verify_tier 'R', via shippable_pc) becomes an idle loop:
    an unexecuted guess is worse than none — gpSP would end the frame slice at an address
    that is not the wait loop.
    """
    idle_pc = gba_probe._table.shippable_pc(entry)
    return {
        "idle_loop": 1 if idle_pc else 0,
        "idle_pc": idle_pc,
        "exec_cycles": entry["exec_median"],
        "idle_drop": entry.get("idle_drop") if idle_pc else None,
        "idle_hunted": 1 if entry.get("idle_hunted") else 0,
        "audio_cycles": entry.get("audio_cycles"),
        "audio_variant": entry.get("audio_variant"),
        "audio_name": entry.get("audio_name"),
        "probe_status": "ok",
    }


def apply_table(conn: Connection, session_id: str = config.SHARED_SESSION_ID) -> int:
    """Fill in every GBA row the shipped table can speak for. Returns rows changed.

    Idempotent: a row already carrying the table's values is left untouched, so the second
    run (and every startup after) changes nothing.
    """
    table = gba_probe._table.load()
    if not table:
        return 0

    root = storage.session_root(session_id)
    rows = conn.execute(
        "SELECT id, rom_path, idle_loop, idle_pc, exec_cycles, idle_drop, idle_hunted, "
        "audio_cycles, audio_variant, audio_name, probe_status "
        "FROM roms WHERE session_id = ? AND system_key = ?",
        (session_id, SYSTEM),
    ).fetchall()

    updated = 0
    for row in rows:
        code = gba_probe.game_code(root / row["rom_path"])
        entry = table.get(code or "")
        if not entry or not gba_probe._table.measured(entry):
            continue                        # not in the table — leave the row alone
        want = _entry_columns(entry)
        if all(row[col] == val for col, val in want.items()):
            continue                        # already stamped — no write
        conn.execute(
            "UPDATE roms SET idle_loop = ?, idle_pc = ?, exec_cycles = ?, idle_drop = ?, "
            "idle_hunted = ?, audio_cycles = ?, audio_variant = ?, audio_name = ?, "
            "probe_status = ? WHERE id = ?",
            (*(want[c] for c in (
                "idle_loop", "idle_pc", "exec_cycles", "idle_drop", "idle_hunted",
                "audio_cycles", "audio_variant", "audio_name", "probe_status")),
             row["id"]),
        )
        updated += 1

    return updated
