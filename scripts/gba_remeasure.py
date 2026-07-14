#!/usr/bin/env python3
"""Re-measure GBA games and fold the corrected numbers back into the shared table.

`idlefind.py table` only ever ADDS games the table has never seen — re-running a proven
game would just be a slower way to the same answer. But a FIRST measurement can be wrong,
and then the only fix is to revisit it:

  * The idle hunt found no wait loop where one exists — a false negative counts the wait as
    real work and the badge reads far too heavy (Super Robot Taisen J: 182%, yet it plays).
  * The sound driver was never captured (audio_cycles null), so exec_cycles still carries a
    mixer the device runs natively and never pays. A whole game family can share this hole.

For each target this does the two runs a full verdict needs — hunt the idle loop, then
`audio.cost` for the mixer AND the frame's real work together (same run, the only way the
two can be subtracted) — prints a before/after, and with --write folds idle_*, exec_median
and audio_* into scripts/gba_idle_loop_db.json.

It is honest about what it cannot do. A game whose sound driver is not the M4A block we
fingerprint — compressed in the rom, or a different engine (the older Banpresto Super Robot
Taisen carts carry neither `str r8,[sp]` nor the M4A return sequence anywhere) — comes back
with no driver, and the script says so rather than inventing a zero.

    gba_remeasure.py --codes B6JJ A6SJ ASRJ AJ9J      # specific game codes
    gba_remeasure.py --unmeasured-audio               # every table game with no mixer yet
    gba_remeasure.py --rom-dir DIR --codes …          # where to find the rom files
    gba_remeasure.py … --write                        # actually save

Needs the idlefind binary (IDLEFIND_BIN, or `idlefind` on PATH). Without it every run is a
no-op and the script says so — it never pretends. Meant for the container/probe image, but
runs anywhere the aarch64 binary does.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "idlefind"))

from gbaidle import audio, hunt, rom as rommod, runner, table   # noqa: E402

# The shared library's GBA folder — where the rom files live in a normal deployment. Only a
# default; --rom-dir overrides. Kept here so the common case needs no flag.
DEFAULT_ROM_DIR = (Path(__file__).resolve().parents[1]
                   / "backend" / "data" / "library" / "public" / "roms" / "gba")


def _index_roms(rom_dir: Path) -> dict[str, Path]:
    """game code -> rom file, for every .gba in the directory."""
    out: dict[str, Path] = {}
    for p in sorted(rom_dir.glob("*.gba")):
        code = rommod.game_code(p)
        if code and code not in out:
            out[code] = p
    return out


def _targets(args, known: dict[str, dict], roms: dict[str, Path]) -> list[str]:
    """The game codes to re-measure, filtered to ones whose rom we can actually open."""
    if args.codes:
        wanted = args.codes
    elif args.unmeasured_audio:
        wanted = [c for c, r in known.items()
                  if table.measured(r) and not r.get("audio_cycles")]
    else:                                    # --all, or nothing: every rom on disk
        wanted = list(roms)
    return [c for c in wanted if c in roms]


def _remeasure_one(rom_path: Path) -> dict:
    """Hunt the idle loop, then measure the mixer + real work in one run. Table-shaped."""
    found, exec_off = hunt.find(rom_path)
    idle_pc = found.pc_hex if found else None
    idle_drop = round(found.verdict.drop, 3) if found else None
    exec_cycles = found.exec_cycles if found else exec_off

    row = table.row_for(
        rommod.game_code(rom_path), name=rom_path.stem,
        exec_cycles=exec_cycles or 0, idle_pc=idle_pc, idle_drop=idle_drop,
        how=("hunt: %s + A/B" % found.how) if found else "hunt: no wait loop exists")

    # The mixer, from the SAME kind of run (skip forced at the loop, so exec is comparable).
    # cost() re-reports exec_median from its run; when a driver is measured that paired value
    # is the one to keep, because audio_cycles was subtracted from exactly it.
    driver, block_cycles, exec_paired = audio.cost(rom_path, idle_pc)
    if driver and block_cycles:
        row["exec_median"] = exec_paired or exec_cycles
        row["audio_engine"] = driver.engine
        row["audio_variant"] = driver.variant
        row["audio_name"] = driver.name or None
        row["audio_cycles"] = block_cycles
    elif driver:
        # The block is in the rom but never ran this session — record the engine, no cost.
        row["audio_engine"] = driver.engine
    return row


def _fmt(row: dict) -> str:
    exec_c = row.get("exec_median") or 0
    load = f"{round(100 * exec_c / 90000)}%" if exec_c else "—"
    idle = row.get("idle_verified") or ("hunted-none" if row.get("idle_hunted") else "—")
    aud = (f"{row['audio_cycles']}cy {row.get('audio_name') or row.get('audio_variant') or '?'}"
           if row.get("audio_cycles") else "no mixer")
    return f"exec={exec_c:>7} ({load:>4})  idle={idle:<12}  audio={aud}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--codes", nargs="*", help="game codes to re-measure")
    ap.add_argument("--unmeasured-audio", action="store_true",
                    help="every measured game the table has with no mixer captured")
    ap.add_argument("--all", action="store_true", help="every rom in the directory")
    ap.add_argument("--rom-dir", default=str(DEFAULT_ROM_DIR))
    ap.add_argument("--table", help="a different table file")
    ap.add_argument("--write", action="store_true", help="save the results")
    args = ap.parse_args()

    if not runner.available():
        print("no idlefind binary — set IDLEFIND_BIN or put `idlefind` on PATH", file=sys.stderr)
        return 2

    rom_dir = Path(args.rom_dir)
    if not rom_dir.is_dir():
        print(f"rom dir not found: {rom_dir}", file=sys.stderr)
        return 2

    path = Path(args.table) if args.table else None
    known = table.load(path)
    roms = _index_roms(rom_dir)
    codes = _targets(args, known, roms)
    if not codes:
        print("nothing to re-measure (no matching rom on disk)")
        return 0

    print(f"re-measuring {len(codes)} game(s) from {rom_dir}\n")
    rows = list(known.values())
    changed = 0
    for code in codes:
        before = known.get(code, {})
        after = _remeasure_one(roms[code])
        print(f"  {code}  {roms[code].name[:40]}")
        print(f"       was: {_fmt(before)}")
        print(f"       now: {_fmt(after)}")
        rows = table.upsert(rows, code, **after)
        changed += 1

    if args.write:
        table.save(rows, path)
        print(f"\n{changed} row(s) written to {path or table.DEFAULT_PATH}")
    else:
        print(f"\n{changed} row(s) measured — pass --write to save")
    return 0


if __name__ == "__main__":
    sys.exit(main())
