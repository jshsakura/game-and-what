#!/usr/bin/env python3
"""Select GBA ROMs that gpSP can idle-loop skip, by reading their headers.

gpSP has no automatic idle-loop detection: gba_memory.c defaults
idle_loop_target_pc to 0xFFFFFFFF and only overrides it when the ROM's
4-char game code is found in the gba_over.h table. So a ROM outside that
table never skips its VBlank wait, and never gets the speedup.

This scans ROMs, reads the game code from the cartridge header, and reports
(or copies out) the ones the database can actually accelerate.

    python3 gba_idle_match.py ~/roms/gba
    python3 gba_idle_match.py ~/roms/gba --copy backend/data/library/gba
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

# GBA cartridge header layout (GBATEK).
TITLE_OFFSET = 0xA0
TITLE_LENGTH = 12
GAME_CODE_OFFSET = 0xAC
GAME_CODE_LENGTH = 4
MAKER_CODE_OFFSET = 0xB0
MAKER_CODE_LENGTH = 2
FIXED_BYTE_OFFSET = 0xB2
FIXED_BYTE_VALUE = 0x96
HEADER_LENGTH = 0xC0

DB_PATH = Path(__file__).with_name("gba_idle_loop_db.json")
ROM_SUFFIXES = (".gba", ".agb", ".bin")


class HeaderError(Exception):
    """The file is not a readable GBA cartridge."""


def read_header(rom_path):
    """Return the header triple (title, game_code, maker_code) of a GBA ROM."""
    try:
        with open(rom_path, "rb") as handle:
            header = handle.read(HEADER_LENGTH)
    except OSError as error:
        raise HeaderError(f"read failed: {error}") from error

    if len(header) < HEADER_LENGTH:
        raise HeaderError(f"too small ({len(header)} bytes)")
    if header[FIXED_BYTE_OFFSET] != FIXED_BYTE_VALUE:
        raise HeaderError("bad magic (0xB2 != 0x96) — not a GBA ROM")

    def field(offset, length):
        raw = header[offset:offset + length]
        return raw.decode("ascii", "replace").rstrip("\x00").strip()

    return {
        "title": field(TITLE_OFFSET, TITLE_LENGTH),
        "game_code": field(GAME_CODE_OFFSET, GAME_CODE_LENGTH),
        "maker_code": field(MAKER_CODE_OFFSET, MAKER_CODE_LENGTH),
    }


def load_database():
    """Return {game_code: entry} for every game with a known idle-loop target."""
    try:
        rows = json.loads(DB_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        sys.exit(f"cannot load {DB_PATH}: {error}")
    return {row["game_code"]: row for row in rows if row.get("has_idle")}


def find_roms(root):
    """Return every ROM-suffixed file under root, sorted."""
    if not root.is_dir():
        sys.exit(f"not a directory: {root}")
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in ROM_SUFFIXES
    )


def classify(rom_paths, idle_db):
    """Split ROMs into idle-loop hits, misses, and unreadable headers."""
    hits, misses, broken = [], [], []
    for path in rom_paths:
        try:
            header = read_header(path)
        except HeaderError as error:
            broken.append((path, str(error)))
            continue

        entry = idle_db.get(header["game_code"])
        record = {"path": path, "header": header, "entry": entry}
        (hits if entry else misses).append(record)
    return hits, misses, broken


def idle_target(entry):
    """The address gpSP jumps out of; libretro's table is what gpSP ships."""
    return entry.get("idle_libretro") or entry.get("idle_regba") or "?"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom_dir", type=Path, help="directory to scan (recursive)")
    parser.add_argument("--copy", type=Path, metavar="DEST",
                        help="copy the idle-loop-capable ROMs into DEST")
    args = parser.parse_args()

    idle_db = load_database()
    roms = find_roms(args.rom_dir)
    hits, misses, broken = classify(roms, idle_db)

    print(f"scanned {len(roms)} ROM(s) under {args.rom_dir}")
    print(f"  idle-loop capable : {len(hits)}")
    print(f"  not in DB         : {len(misses)}")
    print(f"  unreadable header : {len(broken)}\n")

    for record in hits:
        header, entry = record["header"], record["entry"]
        flag = "  [!] libretro/ReGBA addresses disagree" if entry.get("conflict") else ""
        print(f"  {header['game_code']}  idle={idle_target(entry):<12} "
              f"{header['title']:<14} {record['path'].name}{flag}")

    if misses:
        print("\n  -- no idle-loop entry (full-speed unlikely on M7) --")
        for record in misses:
            header = record["header"]
            print(f"  {header['game_code']}  {header['title']:<14} {record['path'].name}")

    for path, reason in broken:
        print(f"  [skip] {path.name}: {reason}", file=sys.stderr)

    if args.copy:
        args.copy.mkdir(parents=True, exist_ok=True)
        for record in hits:
            shutil.copy2(record["path"], args.copy / record["path"].name)
        print(f"\ncopied {len(hits)} ROM(s) -> {args.copy}")


if __name__ == "__main__":
    main()
