"""Push the measured GBA numbers into the library.

`scripts/gba_idle_loop_db.json` is the source of truth: it holds, per game code, the
idle-loop address gpSP needs and the cycles the game actually spends working per frame
(measured by running the rom — see scripts/idlefind). This copies both onto the roms
table so the library can show a verdict instead of just "the skip exists".

Reads the game code from each rom's cart header, so it does not care what the file is
called. Idempotent.
"""
import json
from pathlib import Path

from app import db
from app.services import storage

SESSION = "public"
SYSTEM = "gba"

GAME_CODE_OFFSET = 0xAC
FIXED_BYTE_OFFSET = 0xB2
FIXED_BYTE_VALUE = 0x96
HEADER_LENGTH = 0xC0

DB_PATH = Path(__file__).resolve().parent.parent / "scripts" / "gba_idle_loop_db.json"


def game_code(path: Path) -> str | None:
    header = path.open("rb").read(HEADER_LENGTH)
    if len(header) < HEADER_LENGTH or header[FIXED_BYTE_OFFSET] != FIXED_BYTE_VALUE:
        return None
    return header[GAME_CODE_OFFSET:GAME_CODE_OFFSET + 4].decode("ascii", "replace")


def main() -> None:
    table = {r["game_code"]: r for r in json.loads(DB_PATH.read_text(encoding="utf-8"))}
    root = storage.session_root(SESSION)

    updated = unmeasured = 0
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, stored_name, rom_path FROM roms WHERE session_id=? AND system_key=?",
            (SESSION, SYSTEM),
        ).fetchall()

        for row in rows:
            code = game_code(root / row["rom_path"])
            entry = table.get(code or "", {})
            cycles = entry.get("exec_median")
            # Only a RUN-verified address counts as an idle loop here. A guess that was
            # never executed is worse than nothing: gpSP would jump out of the frame at
            # an address that isn't the wait loop.
            idle = 1 if entry.get("verify_tier") == "R" else 0

            if cycles is None:
                unmeasured += 1
            conn.execute(
                "UPDATE roms SET idle_loop = ?, exec_cycles = ? WHERE id = ?",
                (idle, cycles, row["id"]),
            )
            updated += 1

    print(f"{updated} rom(s) updated, {unmeasured} not measured")


if __name__ == "__main__":
    main()
