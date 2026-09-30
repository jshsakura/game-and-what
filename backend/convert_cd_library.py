"""Convert existing Sega CD / PC Engine CD CHDs and remove redundant originals.

Run with GNW_DATA_DIR pointing at the library root. Defaults to listing candidates;
--apply converts them, preserving row IDs and metadata, and backs up SQLite first.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from app import config, db
from app.services.cdrom import convert_library_chd


async def main(apply: bool) -> int:
    if not config.DB_PATH.exists():
        raise SystemExit(f"Database does not exist: {config.DB_PATH}")
    with db.connect() as conn:
        rows = conn.execute("SELECT id, session_id, system_key, stored_name FROM roms "
                            "WHERE system_key IN ('segacd','pcecd') AND lower(rom_path) LIKE '%.chd'").fetchall()
        if apply and rows:
            backup = config.DATA_DIR / "_backups" / ("before-cd-conversion-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".db")
            backup.parent.mkdir(parents=True, exist_ok=True)
            import sqlite3
            with sqlite3.connect(backup) as destination:
                conn.backup(destination)
            print(f"DB backup: {backup}", flush=True)
    print(f"CHD entries: {len(rows)}", flush=True)
    failed = 0
    for row in rows:
        print(f"{row['system_key']}: {row['stored_name']}", flush=True)
        if not apply:
            continue
        try:
            result = await convert_library_chd(row["session_id"], row["id"])
            print(f"  DONE: {result['rom_path']} ({result['tracks']} tracks); CHD removed", flush=True)
        except Exception as exc:
            failed += 1
            print(f"  FAILED: {getattr(exc, 'detail', str(exc))}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="convert and remove successfully converted CHDs")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.apply)))
