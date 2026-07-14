#!/usr/bin/env python3
"""idlefind — the GBA idle-loop tool. One entry point; the rules live in gbaidle/verify.py.

    ./idlefind.py measure  ROM…            what does this game cost, and can we skip its wait?
    ./idlefind.py sweep    ROM_DIR         the same, over a directory, in parallel
    ./idlefind.py table    ROM_DIR --write hunt, then fold the results into the shared table
    ./idlefind.py show     [CODE…]         what the table already knows

Every address it reports has been proven by A/B: the game was run with the skip off and
with the address, the work has to measurably drop, AND the game has to still be drawing
what it drew. See gbaidle/verify.py — each of those rules is there because something got
through without it.

Needs the `idlefind` binary (patched mGBA). `make` builds it; without it, `show` still
works and everything else says so plainly instead of pretending.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gbaidle import hunt, rom, runner, table   # noqa: E402

CPU_BUDGET = 90000        # what the M7 can emulate per frame — timed on the device
FRAME_CYCLES = 280896


def _verdict(exec_cycles: int) -> str:
    return f"CPU {round(100 * exec_cycles / CPU_BUDGET)}% of the device's budget"


def _measure_one(path: Path) -> tuple[str, Path, object, int | None]:
    code = rom.game_code(path)
    found, exec_off = hunt.find(path)
    return code or "????", path, found, exec_off


def _report(code: str, path: Path, found, exec_off) -> None:
    line = hunt.summarise(found, exec_off)
    cycles = found.exec_cycles if found else exec_off
    verdict = f"  [{_verdict(cycles)}]" if cycles else ""
    print(f"  {code}  {path.name[:38]:<40} {line}{verdict}", flush=True)


def cmd_measure(args) -> int:
    if not runner.available():
        print("no `idlefind` binary — run `make` first (see README)", file=sys.stderr)
        return 2
    for path in args.roms:
        _report(*_measure_one(Path(path)))
    return 0


def cmd_sweep(args) -> int:
    if not runner.available():
        print("no `idlefind` binary — run `make` first (see README)", file=sys.stderr)
        return 2
    roms = sorted(Path(args.rom_dir).glob("*.gba"))
    print(f"{len(roms)} rom(s), {args.jobs} at a time\n")

    found_n = busy_n = 0
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for code, path, found, exec_off in pool.map(_measure_one, roms):
            _report(code, path, found, exec_off)
            found_n += bool(found)
            busy_n += bool(not found and exec_off)

    print(f"\nwait loop found and proven : {found_n}")
    print(f"nothing to skip (real work): {busy_n}")
    return 0


def cmd_table(args) -> int:
    """Hunt a directory and fold what it finds into the shared table.

    Only ADDS. A row that is already measured is left alone — re-measuring a game we have
    already proven would just be a slower way to get the same answer, and a worse way to
    lose it if a run goes wrong.
    """
    if not runner.available():
        print("no `idlefind` binary — run `make` first (see README)", file=sys.stderr)
        return 2

    path = Path(args.table) if args.table else table.DEFAULT_PATH
    known = table.load(path)
    rows = list(known.values())
    todo = [p for p in sorted(Path(args.rom_dir).glob("*.gba"))
            if (c := rom.game_code(p)) and not table.measured(known.get(c, {}))]
    print(f"{len(todo)} rom(s) the table has never seen\n")

    added = 0
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for code, romfile, found, exec_off in pool.map(_measure_one, todo):
            _report(code, romfile, found, exec_off)
            if not exec_off:
                continue
            rows = table.upsert(rows, code, **table.row_for(
                code, name=romfile.stem,
                exec_cycles=found.exec_cycles if found else exec_off,
                idle_pc=found.pc_hex if found else None,
                idle_drop=round(found.verdict.drop, 3) if found else None,
                how=("hunt: %s + A/B" % found.how) if found else "hunt: no wait loop exists",
            ))
            added += 1

    if args.write:
        table.save(rows, path)
        print(f"\n{added} row(s) written to {path}")
    else:
        print(f"\n{added} row(s) would be written — pass --write to save")
    return 0


def cmd_show(args) -> int:
    known = table.load(Path(args.table) if args.table else None)
    codes = args.codes or sorted(known)
    for code in codes:
        row = known.get(code)
        if not row or not table.measured(row):
            print(f"  {code}  not in the table")
            continue
        pc = table.shippable_pc(row)
        drop = row.get("idle_drop")
        print(f"  {code}  {str(pc or '-'):>10}  {row['exec_median']:>7} cy  "
              f"{f'skip {drop * 100:.0f}%' if drop else '':<9} "
              f"{_verdict(row['exec_median']):<28} {(row.get('lib_name') or '')[:30]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true", help="log every A/B attempt")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("measure", help="one or more roms")
    m.add_argument("roms", nargs="+")
    m.set_defaults(fn=cmd_measure)

    s = sub.add_parser("sweep", help="a whole directory")
    s.add_argument("rom_dir")
    s.add_argument("-j", "--jobs", type=int, default=4)
    s.set_defaults(fn=cmd_sweep)

    t = sub.add_parser("table", help="hunt, and fold the results into the shared table")
    t.add_argument("rom_dir")
    t.add_argument("-j", "--jobs", type=int, default=4)
    t.add_argument("--table", help="a different table file")
    t.add_argument("--write", action="store_true", help="actually save")
    t.set_defaults(fn=cmd_table)

    sh = sub.add_parser("show", help="what the table already knows")
    sh.add_argument("codes", nargs="*")
    sh.add_argument("--table")
    sh.set_defaults(fn=cmd_show)

    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="    %(message)s")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
