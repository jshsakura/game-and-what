#!/usr/bin/env python3
"""Emit gpSP idle-loop entries for every GBA game in this library.

Why this exists: gpSP has no automatic idle-loop detection. `gba_memory.c` defaults
`idle_loop_target_pc` to 0xFFFFFFFF and only overrides it when the cart's 4-char code
is in its hand-maintained table. A game absent from that table busy-waits through the
whole frame and cannot reach full speed on the M7.

That table is also **wrong in places**, and a Korean patch defeats it entirely: the
patch keeps the original cart header, so gpSP looks the game up under the original
code and applies the original address, which the patch has moved. Nothing in the
filename, header or region warns you.

Every address here was measured by RUNNING the rom (scripts/idlefind) — only entries
gpSP can be shown to actually skip on. `exec` is the game's real CPU work per frame
with the skip active, out of a 280,896-cycle frame; the M7 leaves the CPU roughly
160,000 of them at a 340MHz OC (an estimate — see docs/GBA_FIRMWARE_HANDOFF.md §5).

    python3 scripts/gen_gba_over.py            # all of them
    python3 scripts/gen_gba_over.py --korean   # just the Korean ones
    python3 scripts/gen_gba_over.py --c        # a C table, for the firmware override
"""
import argparse
import json
from pathlib import Path

DB_PATH = Path(__file__).with_name("gba_idle_loop_db.json")
FRAME_CYCLES = 280896
CPU_BUDGET = 160000

# Korean releases and 한글패치 in this library — confirmed by rendering each rom and
# reading the screen (scripts/idlefind/shot.c), the only place a patch shows up.
# See backend/korean_gba.py for the per-game evidence.
KOREAN = {
    "BPEK": "포켓몬스터 에메랄드 (정식 한국판)",
    "AXVK": "포켓몬스터 루비 (정식 한국판)",
    "AXPK": "포켓몬스터 사파이어 (정식 한국판)",
    "BPRE": "포켓몬스터 파이어레드 (한글패치, 미국판 헤더)",
    "BPGE": "포켓몬스터 리프그린 (한글패치, 미국판 헤더)",
    "AAMJ": "캐슬바니아 - 서클 오브 더 문 (한글패치)",
    "AFXJ": "파이널 판타지 택틱스 어드밴스 (한글패치)",
    "BRIJ": "리듬세상 (한글패치)",
    "AZWJ": "메이드 인 와리오 (한글패치)",
    "BDTE": "다운타운 열혈물어EX (한글패치)",
    "BZ3J": "록맨 제로 3 (한글패치)",
    "B4ZJ": "록맨 제로 4 (한글패치)",
    "AA2C": "슈퍼마리오월드 (한글패치)",
}


def title_of(row: dict) -> str:
    """The library's own name for the game. gpSP's table calls it "PRINCEPERSIA"; the
    person reading the generated file needs to recognise it."""
    code = row["game_code"]
    if code in KOREAN:
        return KOREAN[code]
    return (row.get("lib_name") or row.get("title") or row.get("header_title") or code).strip()


def load(korean_only: bool) -> list[dict]:
    rows = json.loads(DB_PATH.read_text(encoding="utf-8"))
    # Only run-verified rows. A guessed address is worse than none: gpSP would jump out
    # of the frame at somewhere that is not the wait loop. One of ours WAS wrong.
    rows = [r for r in rows if r.get("exec_median")]
    if korean_only:
        rows = [r for r in rows if r["game_code"] in KOREAN]
    return sorted(rows, key=lambda r: r["exec_median"])


def verdict(row: dict) -> str:
    load_pct = round(100 * row["exec_median"] / CPU_BUDGET)
    return f"CPU {load_pct}% of budget"


def emit_h(rows: list[dict]) -> None:
    print("/* gpSP idle-loop entries, measured by RUNNING each rom (scripts/idlefind).")
    print(" * idle_loop_target_pc is the PC gpSP ends the frame slice at: the backward")
    print(" * branch that closes the wait loop, or — where the loop hops rather than")
    print(" * branching straight back — a landing point inside it. cpu.cc:3063 compares")
    print(" * reg[REG_PC] after every instruction, so either does the job, and so does an")
    print(" * address in IWRAM/EWRAM (an emulator-cart runs its wait from RAM).")
    print(" *")
    print(f" * exec = real CPU work per frame with the skip active, out of {FRAME_CYCLES:,}.")
    print(f" * The M7 leaves the CPU roughly {CPU_BUDGET:,} cycles at a 340MHz OC.")
    print(" */")
    print()
    for row in rows:
        pc, med = row.get("idle_verified"), row["exec_median"]
        idle_pct = round(100 * (1 - med / FRAME_CYCLES))
        if not pc:
            print(f"   /* {row['game_code']}  {title_of(row)}")
            if med <= CPU_BUDGET:
                print( "    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP")
                print( "    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.")
            elif row.get("idle_hunted"):
                # Hunted and came up empty. Saying "no entry needed" here would read as
                # "it is fine", and it is not: there is no wait to skip because the game
                # is working the whole frame. An emulator-cart (Classic NES, Hudson) is
                # the clearest case — it spends the frame emulating a NES.
                print( "    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes")
                print( "    * into real work, so no address would make this lighter — it is this heavy.")
            else:
                print( "    * NOT MEASURED — its wait loop was never found, so the spin got counted as")
                print( "    * work. The number below is the probe's failure, not the game's weight.")
            print(f"    * exec {med:,}/{FRAME_CYCLES:,} ({idle_pct}% idle) — {verdict(row)}")
            print("    */")
            print()
            continue
        print("   {")
        print(f"      // {title_of(row)}")
        print(f"      //   exec {med:,}/{FRAME_CYCLES:,} cy/frame ({idle_pct}% idle) — {verdict(row)}")
        print(f'      "{row["game_code"]}",                      /* gamepak_code         */')
        print("      0,                           /* flags (gpSP auto-detects the save type) */")
        print(f"      {pc},                   /* idle_loop_target_pc  */")
        print("      0,                           /* translation_gate_target_1 */")
        print("      0,                           /* translation_gate_target_2 */")
        print("      0,                           /* translation_gate_target_3 */")
        print("   },")
        print()


def emit_c(rows: list[dict]) -> None:
    """A standalone table the firmware can apply WITHOUT forking gpSP.

    gpSP exposes `idle_loop_target_pc` as a plain extern (cpu.h:161), so the porting
    layer can just overwrite it after the rom loads. That also corrects gpSP's own wrong
    entries (FireRed, LeafGreen, APDE) for free.
    """
    with_pc = [r for r in rows if r.get("idle_verified")]
    print("// Generated by scripts/gen_gba_over.py in game-and-what — DO NOT HAND-EDIT.")
    print("// Regenerate there and copy, or the firmware will silently disagree with the")
    print("// measurements. See docs/GBA_FIRMWARE_HANDOFF.md.")
    print("//")
    print("// Every address was measured by running the rom: gpSP demonstrably skips on it.")
    print("// Apply after the rom is loaded:")
    print("//     extern u32 idle_loop_target_pc;")
    print("//     u32 pc = gba_idle_loop_lookup(rom + 0xAC);")
    print("//     if (pc) idle_loop_target_pc = pc;")
    print()
    print('#include "gba_idle_loop.h"')
    print()
    print("#include <string.h>")
    print()
    print("typedef struct {")
    print("    char code[5];      // the 4 chars at rom[0xAC]")
    print("    // The PC gpSP ends the frame slice at. Usually the backward branch that")
    print("    // closes the wait loop; where the loop hops instead of branching straight")
    print("    // back (Super Mario Advance takes three hops), a landing point inside it.")
    print("    // Either works: cpu.cc:3063 compares reg[REG_PC] after EVERY instruction,")
    print("    // so any address the loop runs on every iteration ends the slice. That is")
    print("    // also why a few of these are in IWRAM/EWRAM (0x02.../0x03...) rather than")
    print("    // ROM — an emulator-cart copies its core into RAM and waits there.")
    print("    uint32_t pc;")
    print("    uint32_t exec;     // measured CPU cycles/frame, of 280896, with the skip on")
    print("} gba_idle_entry_t;")
    print()
    print("static const gba_idle_entry_t GBA_IDLE_LOOPS[] = {")
    for row in with_pc:
        print(f'    {{ "{row["game_code"]}", {row["idle_verified"]}, {row["exec_median"]} }},'
              f'   // {title_of(row)}')
    print("};")
    print()
    print("uint32_t gba_idle_loop_lookup(const char *gamepak_code) {")
    print("    for (size_t i = 0; i < sizeof(GBA_IDLE_LOOPS) / sizeof(GBA_IDLE_LOOPS[0]); ++i) {")
    print("        if (memcmp(GBA_IDLE_LOOPS[i].code, gamepak_code, 4) == 0) {")
    print("            return GBA_IDLE_LOOPS[i].pc;")
    print("        }")
    print("    }")
    print("    return 0;   // unknown game: leave gpSP's own table alone")
    print("}")
    print()
    print("uint32_t gba_exec_cycles_lookup(const char *gamepak_code) {")
    print("    for (size_t i = 0; i < sizeof(GBA_IDLE_LOOPS) / sizeof(GBA_IDLE_LOOPS[0]); ++i) {")
    print("        if (memcmp(GBA_IDLE_LOOPS[i].code, gamepak_code, 4) == 0) {")
    print("            return GBA_IDLE_LOOPS[i].exec;")
    print("        }")
    print("    }")
    print("    return 0;")
    print("}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--korean", action="store_true", help="only the Korean games")
    ap.add_argument("--c", action="store_true", help="emit a C table instead of gba_over.h entries")
    args = ap.parse_args()

    rows = load(args.korean)
    (emit_c if args.c else emit_h)(rows)


if __name__ == "__main__":
    main()
