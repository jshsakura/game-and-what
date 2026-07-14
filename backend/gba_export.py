"""Fold roms measured live (by the upload prober) back into the shared table.

The prober runs a freshly-uploaded GBA rom and writes what it found onto that rom's
row. That is enough for the library's badge, but the address it found is exactly what
the firmware needs — and it would be stranded on one row in one deployment's database.

This walks the library, picks up anything measured that the table does not have, and
writes it into `scripts/gba_idle_loop_db.json`, which is what `scripts/gen_gba_over.py`
turns into the C table for game-and-watch-retro-go-sd.

    python3 gba_export.py            # show what is new
    python3 gba_export.py --write    # merge it in
"""
import argparse
import json
from pathlib import Path

from app import db
from app.services import gba_probe, storage

SESSION = "public"
SYSTEM = "gba"
DB_PATH = Path(__file__).resolve().parent.parent / "scripts" / "gba_idle_loop_db.json"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="merge into the table")
    args = ap.parse_args()

    table = {r["game_code"]: r for r in json.loads(DB_PATH.read_text(encoding="utf-8"))}
    root = storage.session_root(SESSION)

    added: list[dict] = []
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT stored_name, rom_path, idle_pc, exec_cycles FROM roms "
            "WHERE session_id=? AND system_key=? AND probe_status='ok' AND exec_cycles IS NOT NULL",
            (SESSION, SYSTEM),
        ).fetchall()

    for row in rows:
        code = gba_probe.game_code(root / row["rom_path"])
        if not code or table.get(code, {}).get("exec_median"):
            continue    # unknown file, or the table already has it
        entry = {
            "game_code": code,
            "lib_name": row["stored_name"].rsplit(".", 1)[0],
            "exec_median": row["exec_cycles"],
            "has_idle": bool(row["idle_pc"]),
            # R = confirmed by RUNNING the rom. The only tier that may be shipped: an
            # address that was guessed and never executed would have gpSP jump out of
            # the frame somewhere that is not the wait loop.
            "verify_tier": "R" if row["idle_pc"] else None,
            "verify_how": "upload probe",
        }
        if row["idle_pc"]:
            entry["idle_verified"] = row["idle_pc"]
        added.append(entry)

    for entry in added:
        print(f"  + {entry['game_code']}  {entry.get('idle_verified') or 'no loop':>12}  "
              f"{entry['exec_median']:>7} cy  {entry['lib_name'][:40]}")

    if not added:
        print("nothing new — the table already has every measured rom")
        return

    if not args.write:
        print(f"\n{len(added)} new. Re-run with --write to merge.")
        return

    for entry in added:
        table[entry["game_code"]] = {**table.get(entry["game_code"], {}), **entry}
    DB_PATH.write_text(
        json.dumps(sorted(table.values(), key=lambda r: r["game_code"]), indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n{len(added)} merged into {DB_PATH.name}. "
          "Regenerate the firmware table: python3 scripts/gen_gba_over.py --c")


if __name__ == "__main__":
    main()
