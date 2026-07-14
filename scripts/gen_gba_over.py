#!/usr/bin/env python3
"""Emit gpSP `gba_over.h` entries for the Korean GBA games in this library.

Why this exists: a Korean fan-patch keeps the original cart header, so gpSP looks
the game up under the ORIGINAL code and applies the ORIGINAL idle-loop address —
which the patch has usually moved. The game then busy-waits through the whole
frame and cannot reach full speed, with nothing in the header to warn you. Every
address below was measured by RUNNING the patched ROM (scripts/idlefind), not
copied from gpSP's table.

`exec` is the game's real CPU work per frame with the skip active, out of a
280,896-cycle frame. Compare it against what the hardware leaves the CPU
(~160,000 cycles at a 340MHz OC) to see whether the skip is actually enough.

    python3 scripts/gen_gba_over.py > gba_over_korean.h
"""
import json
from pathlib import Path

DB_PATH = Path(__file__).with_name("gba_idle_loop_db.json")
FRAME_CYCLES = 280896
CPU_BUDGET = 160000

# The Korean games, and how they got that way. Verified by rendering each ROM
# headless and reading the screen — a patch shows up nowhere else.
KOREAN = {
    "BPEK": ("포켓몬스터 에메랄드", "정식 한국 발매판"),
    "AXVK": ("포켓몬스터 루비", "정식 한국 발매판"),
    "AXPK": ("포켓몬스터 사파이어", "정식 한국 발매판"),
    "BPRE": ("포켓몬스터 파이어레드", "한글패치 (헤더는 미국판)"),
    "BPGE": ("포켓몬스터 리프그린", "한글패치 (헤더는 미국판)"),
    "AAMJ": ("캐슬바니아 - 서클 오브 더 문", "한글패치 (헤더는 일본판)"),
    "AFXJ": ("파이널 판타지 택틱스 어드밴스", "한글패치 (헤더는 일본판)"),
    "BRIJ": ("리듬세상", "한글패치 (헤더는 일본판)"),
    "AZWJ": ("메이드 인 와리오", "한글패치 (헤더는 일본판)"),
    "BDTE": ("다운타운 열혈물어EX", "한글패치 (헤더는 미국판)"),
    "BZ3J": ("록맨 제로 3", "한글패치 (헤더는 일본판)"),
    "B4ZJ": ("록맨 제로 4", "한글패치 (헤더는 일본판)"),
    "AA2C": ("슈퍼마리오월드", "한글패치 (헤더는 iQue판)"),
}


def main() -> None:
    rows = {r["game_code"]: r for r in json.loads(DB_PATH.read_text(encoding="utf-8"))}

    print("/* Korean GBA games in this library — idle loops measured by running each ROM.")
    print(" * A Korean patch keeps the original cart header, so gpSP would otherwise apply")
    print(" * the ORIGINAL game's idle-loop address, which the patch has moved. Verified with")
    print(" * scripts/idlefind (mGBA IDLE_LOOP_DETECT + a per-frame cycle counter).")
    print(" *")
    print(f" * exec = real CPU work per frame with the skip active, out of {FRAME_CYCLES:,}.")
    print(f" * The M7 leaves the CPU roughly {CPU_BUDGET:,} cycles at a 340MHz OC.")
    print(" */")
    print()

    for code, (title, origin) in sorted(KOREAN.items()):
        row = rows.get(code, {})
        pc = row.get("idle_verified")
        med = row.get("exec_median")
        idle_pct = round(100 * (1 - med / FRAME_CYCLES)) if med else None
        verdict = "예산 내" if med and med <= CPU_BUDGET else "예산 초과"

        if not pc:
            print(f"   /* {code}  {title} — {origin}")
            print(f"    * busy-wait 루프 자체가 없음: BIOS SWI(IntrWait/Halt)로 대기하므로")
            print(f"    * gpSP의 halt 처리가 이미 건너뜀. 엔트리 불필요.")
            print(f"    * exec {med:,}/{FRAME_CYCLES:,} ({idle_pct}% idle) — {verdict}")
            print(f"    */")
            print()
            continue

        print("   {")
        print(f"      // {title} — {origin}")
        print(f"      //   exec {med:,}/{FRAME_CYCLES:,} cy/frame ({idle_pct}% idle) — {verdict}")
        print(f'      "{code}",                      /* gamepak_code         */')
        print(f"      0,                           /* flags (gpSP auto-detects the save type) */")
        print(f"      {pc},                   /* idle_loop_target_pc  */")
        print("      0,                           /* translation_gate_target_1 */")
        print("      0,                           /* translation_gate_target_2 */")
        print("      0,                           /* translation_gate_target_3 */")
        print("   },")
        print()


if __name__ == "__main__":
    main()
