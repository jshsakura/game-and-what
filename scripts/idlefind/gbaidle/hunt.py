"""Find the wait loop — including the ones mGBA's detector can never see — and prove it.

Two ways in, tried in order. Both end at the same gate: `verify.judge()`.

1. **Ask the detector.** mGBA re-walks a backward branch and records the loop only if it
   can prove the body has no side effects. When it answers, the answer comes with a proof
   attached, so it is the one to try first.

2. **Ask the frame where its cycles went.** The detector is silent on plenty of real wait
   loops — it wants the same jump target twice in a row (memory.c:263), and Super Mario
   Advance's loop hops three times before it comes back:

       0x8001cde  poll the flag the VBlank IRQ sets
       0x8001cf2  beq  #0x8001cfc      <- what libretro and ReGBA both ship
       0x8001cfc  b    #0x8001cbc
       0x8001cbc  b    #0x8001cde

   gpSP skips that happily (cpu.cc:3063 is a bare PC compare, run after EVERY instruction)
   while our probe called the game 175% and unmeasurable. So: take the addresses the frame
   is actually burning, and force each in turn. If it is a landing point of the wait, mGBA
   halts there and the work collapses; if not, nothing happens.

**No shape assumptions.** Reading a "body + backward branch" out of the disassembly missed
the hopping loops twice, and starting a Thumb disassembly at the loop's ENTRY branch puts
the decoder out of phase so everything after it reads as garbage. Forcing a hot address
needs no shape at all — and the A/B, not the ranking, is what decides.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from . import runner
from .rom import ROM_BASE, region_of
from .verify import Verdict, judge

log = logging.getLogger(__name__)

MAX_TRIES = 20           # the hottest 20 addresses; a wait loop is never colder than that
GOOD_ENOUGH = 0.40       # a real wait gives up far more than the bar: take it and move on
NEAR = 96                # how far around a hot pc we look for the branch that closes it

_BRANCHES = {"b", "beq", "bne", "bcs", "bcc", "bmi", "bpl", "bhi", "bls",
             "bge", "blt", "bgt", "ble"}


@dataclass(frozen=True)
class Found:
    """A proven address. `pc` is what gpSP is given."""
    pc: int
    exec_cycles: int          # the game's real work per frame WITH the skip
    exec_off: int             # …and without it, which is what the device would pay
    verdict: Verdict
    how: str                  # "detector" | "histogram"

    @property
    def pc_hex(self) -> str:
        return hex(self.pc)


def _disasm(code: bytes, addr: int):
    try:
        from capstone import CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB, Cs
    except ImportError:      # pragma: no cover - capstone is a hard dep of the tool
        log.warning("capstone missing: cannot read a branch out of the loop")
        return
    for mode in (CS_MODE_THUMB, CS_MODE_ARM):
        yield from Cs(CS_ARCH_ARM, mode).disasm(code, addr)


def closing_branch(mem: dict[int, bytes], start: int, hot: set[int]) -> int | None:
    """The branch that jumps back into the loop — gpSP's conventional key, and what the
    other 121 addresses are.

    None is not a failure: a landing point is a valid key too, because gpSP compares the
    PC after every instruction and the loop lands there every iteration. We prefer the
    branch only to stay in step with upstream's table (libretro/ReGBA).
    """
    bytemap: dict[int, int] = {}
    for base, blob in mem.items():
        for i, byte in enumerate(blob):
            bytemap[base + i] = byte

    for anchor in sorted(pc for pc in hot if abs(pc - start) <= NEAR):
        window = bytearray()
        for addr in range(anchor, anchor + NEAR):
            if addr not in bytemap:
                break
            window.append(bytemap[addr])
        if not window:
            continue
        for ins in _disasm(bytes(window), anchor):
            if ins.mnemonic not in _BRANCHES:
                continue
            try:
                target = int(ins.op_str.lstrip("#"), 16)
            except ValueError:
                continue
            if target <= ins.address and target in hot:
                return ins.address
    return None


def _try(rom: Path, off, pc: int, how: str) -> Found | None:
    on = runner.run(rom, forced_pc=hex(pc), want_frames=True)
    if not on:
        return None
    v = judge(off, on)
    log.info("%s  %s  drop=%.1f%% screens=%.1f%%  %s",
             rom.name, hex(pc), v.drop * 100, v.shared * 100, v.why or "OK")
    if not v.ok:
        return None
    return Found(pc, on.exec_cycles, off.exec_cycles, v, how)


def find(rom: Path | str) -> tuple[Found | None, int | None]:
    """Hunt this rom. Returns (the proven address or None, the cost of a frame with no
    skip — which is what the device pays when there is nothing to skip)."""
    rom = Path(rom)

    off, hot, mem = runner.hot_pcs(rom)
    if not off:
        return None, None

    # 1. The detector, first: its answer carries a proof.
    _reading, start, _raw = runner.detect(rom)
    if start:
        found = _try(rom, off, start, "detector")
        if found:
            # Ship the branch where we can read one — that is upstream's convention and
            # what the rest of the table is — else the landing point, which works too.
            branch = closing_branch(mem, start, {pc for pc, _ in hot})
            return (Found(branch or start, found.exec_cycles, found.exec_off,
                          found.verdict, "detector"), off.exec_cycles)

    # 2. The frame's own cycle histogram, hottest first. No shape assumptions.
    best: Found | None = None
    for pc, _cycles in hot[:MAX_TRIES]:
        found = _try(rom, off, pc, "histogram")
        if not found:
            continue
        if best is None or found.verdict.drop > best.verdict.drop:
            branch = closing_branch(mem, pc, {p for p, _ in hot})
            best = Found(branch or pc, found.exec_cycles, found.exec_off,
                         found.verdict, "histogram")
        if found.verdict.drop >= GOOD_ENOUGH:
            break

    return best, off.exec_cycles


def summarise(found: Found | None, exec_off: int | None) -> str:
    """One line a human can read, for the CLI and the logs."""
    if found:
        return (f"{found.pc_hex} ({region_of(found.pc)})  "
                f"{found.exec_off:,} -> {found.exec_cycles:,} cy/frame  "
                f"({found.verdict.drop * 100:.0f}% less work, "
                f"{'identical frames' if found.verdict.exact else f'{found.verdict.shared * 100:.1f}% same screens'})")
    if exec_off is None:
        return "no reading (the rom did not run)"
    return (f"no wait loop to skip — the frame goes into real work "
            f"({exec_off:,} cy/frame)")
