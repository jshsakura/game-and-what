#!/usr/bin/env python3
"""Move CPS-1 romset archives into one folder per game.

CPS-1 entries created before folder support point straight at a loose archive:

    roms/cps1/wof.zip
    roms/cps1/wofj.zip

The card's layout is a folder per game (docs/CPS1_LIBRARY_CONTRACT.md), and the
packager expands roms/cps1/<game>/*.zip into that game's chips. A loose archive
sits outside every game folder and therefore ships nothing at all — the entry is
in the library and the game is not on the card.

This moves each archive under a folder named for the entry, and — because most
CPS-1 romsets are MAME "split sets" — copies whichever OTHER archive supplies
the chips a set is missing into that same folder. A clone and its parent are
two separate playable games, so each ends up with its own complete folder; the
shared archive is duplicated, which costs a few MB and removes an entire class
of "why is this one broken" from the system.

    python3 migrate_cps1_folders.py            # dry run, prints the plan
    python3 migrate_cps1_folders.py --apply    # do it

An older library can also hold a clone and its donor as TWO entries, because
nothing said the donor was not a game. Which one is the game is a judgement no
rule can make — Warriors of Fate (World) and Tenchi wo Kurau II (Japan) really
are two releases — so it is stated rather than guessed:

    python3 migrate_cps1_folders.py --merge wofj wof --title "천지를 먹다 2" [--apply]

keeps `wofj` as the entry, moves `wof`'s archive into its folder as a chip
source, and deletes the `wof` row. Names match the entry's original_name.

Idempotent: an entry already inside a folder is left alone.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import config, db  # noqa: E402
from app.services import cps1, storage  # noqa: E402


def _safe_folder_name(name: str) -> str:
    """A folder name the card and every filesystem in the path will accept.

    The name is cosmetic on the device — the loader identifies chips by content
    hash and never reads it — so it can be the display name, minus the handful
    of characters that would not survive FAT or a zip entry.
    """
    out = "".join("_" if ch in '/\\:*?"<>|' else ch for ch in name).strip().rstrip(".")
    return out or "cps1 game"


def plan(conn):
    """(row, game folder, archives to place) for every entry needing a move."""
    rows = conn.execute(
        "SELECT id, session_id, korean_name, original_name, stored_name, rom_path "
        "FROM roms WHERE system_key = 'cps1'"
    ).fetchall()

    jobs = []
    for row in rows:
        rel = Path(row["rom_path"])
        # Already folder-shaped: roms/cps1/<game>/<file>
        if len(rel.parts) > 3:
            continue
        jobs.append(row)
    return rows, jobs


def merge(conn, keep_name: str, drop_names: list[str], title: str | None, apply: bool) -> int:
    """Fold donor entries into the entry that actually is the game.

    The donor's ARCHIVE is still needed — it holds chips the kept set is missing
    — so it moves into the kept game's folder rather than being deleted. Only
    its library entry goes.
    """
    rows = {r["original_name"]: r for r in conn.execute(
        "SELECT id, session_id, korean_name, original_name, rom_path "
        "FROM roms WHERE system_key = 'cps1'").fetchall()}

    keep = rows.get(keep_name)
    if keep is None:
        print(f"no cps1 entry named {keep_name!r} (have: {', '.join(rows) or 'none'})")
        return 1
    drops = [rows[n] for n in drop_names if n in rows]
    missing = [n for n in drop_names if n not in rows]
    for n in missing:
        print(f"  (no entry named {n!r} — skipping)")

    folder = _safe_folder_name(title or keep["korean_name"] or keep["original_name"])
    base = storage.roms_dir(keep["session_id"], "cps1")
    dest = base / folder
    keep_archive = base / Path(keep["rom_path"]).name
    if not keep_archive.exists():                    # already inside a folder
        keep_archive = storage.session_root(keep["session_id"]) / keep["rom_path"]

    print(f"keep  {keep['korean_name'] or keep_name}")
    print(f"  -> roms/cps1/{folder}/")
    print(f"     move  {keep_archive.name}")
    sources = [keep_archive]
    for d in drops:
        arch = base / Path(d["rom_path"]).name
        if not arch.exists():
            arch = storage.session_root(d["session_id"]) / d["rom_path"]
        sources.append(arch)
        print(f"     move  {arch.name}   (was the entry '{d['original_name']}', now a chip source)")

    ident = cps1.identify([(p.name, p) for p in sources if p.exists()])
    print(f"     -> {ident.message()}")
    if not ident.complete:
        print("     REFUSING: the merged folder would still not be a playable set")
        return 1
    for d in drops:
        print(f"  drop entry '{d['original_name']}' ({d['korean_name']})")

    if not apply:
        return 0

    dest.mkdir(parents=True, exist_ok=True)
    for src in sources:
        target = dest / src.name
        if src.resolve() != target.resolve() and not target.exists():
            shutil.move(str(src), str(target))
    new_rel = f"{config.ROMS_DIR_NAME}/cps1/{folder}/{keep_archive.name}"
    conn.execute(
        "UPDATE roms SET rom_path = ?, korean_name = ?, extra_files = ? WHERE id = ?",
        (new_rel, title or keep["korean_name"],
         __import__("json").dumps([p.name for p in sources[1:]]), keep["id"]))
    for d in drops:
        conn.execute("DELETE FROM roms WHERE id = ?", (d["id"],))
    conn.commit()
    print(f"\n  rom_path -> {new_rel}")
    print(f"  {len(drops)} entr{'y' if len(drops) == 1 else 'ies'} removed")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="perform the move")
    ap.add_argument("--merge", nargs="+", metavar="NAME",
                    help="KEEP DROP... — fold donor entries into the game entry")
    ap.add_argument("--title", help="display name for the merged entry")
    args = ap.parse_args()

    if args.merge:
        if len(args.merge) < 2:
            print("--merge needs at least KEEP and one DROP")
            return 2
        with db.connect() as conn:
            rc = merge(conn, args.merge[0], args.merge[1:], args.title, args.apply)
        if not args.apply and rc == 0:
            print("\ndry run — re-run with --apply to perform it")
        return rc

    with db.connect() as conn:
        rows, jobs = plan(conn)
        if not rows:
            print("no cps1 entries")
            return 0
        if not jobs:
            print(f"{len(rows)} cps1 entries, all already in game folders — nothing to do")
            return 0

        # Every archive in the system folder, so a clone can be completed from
        # whichever other archive happens to hold its parent's chips.
        session_ids = {r["session_id"] for r in rows}
        pool: dict[str, Path] = {}
        for sid in session_ids:
            base = storage.roms_dir(sid, "cps1")
            if base.is_dir():
                for p in sorted(base.iterdir()):
                    if p.is_file() and p.suffix.lower() == ".zip":
                        pool[p.name] = p

        print(f"{len(jobs)} entr{'y' if len(jobs) == 1 else 'ies'} to move; "
              f"{len(pool)} archive(s) available as sources\n")

        for row in jobs:
            name = _safe_folder_name(row["korean_name"] or row["original_name"])
            base = storage.roms_dir(row["session_id"], "cps1")
            dest = base / name
            own = base / Path(row["rom_path"]).name

            # Which archives does this entry need? Its own, plus whatever
            # completes it. identify() picks the set with the fewest missing
            # chips, so a clone is recognised as the clone even on its own.
            wanted = [own]
            ident = cps1.identify([(own.name, own)]) if own.exists() else None
            if ident and not ident.complete:
                for other_name, other in pool.items():
                    if other == own:
                        continue
                    merged = cps1.identify([(own.name, own), (other_name, other)])
                    if merged.complete:
                        wanted.append(other)
                        break

            status = "complete" if ident and ident.complete else (
                ident.message() if ident else "archive missing")
            print(f"  {row['korean_name'] or row['original_name']}")
            print(f"    -> roms/cps1/{name}/")
            for w in wanted:
                print(f"       {'move' if w == own else 'copy'}  {w.name}")
            if len(wanted) == 1 and ident and not ident.complete:
                print(f"       !! still incomplete: {status}")

            if not args.apply:
                continue

            dest.mkdir(parents=True, exist_ok=True)
            for w in wanted:
                target = dest / w.name
                if target.exists():
                    continue
                if w == own:
                    shutil.move(str(w), str(target))
                else:
                    shutil.copy2(str(w), str(target))
            new_rel = f"{config.ROMS_DIR_NAME}/cps1/{name}/{own.name}"
            conn.execute("UPDATE roms SET rom_path = ? WHERE id = ?", (new_rel, row["id"]))
            conn.commit()
            print(f"       rom_path -> {new_rel}")

    if not args.apply:
        print("\ndry run — re-run with --apply to perform it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
