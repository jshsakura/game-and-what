"""Work out whether a GBA rom can run on the real hardware.

Two things decide it, and the cart header carries neither.

1. **Where is the game's VBlank idle loop?** gpSP has no automatic detection — it
   defaults `idle_loop_target_pc` to 0xFFFFFFFF and only overrides it when the cart's
   4-char code is in its hand-maintained table. A game absent from that table
   busy-waits through the whole frame and cannot reach full speed on the M7.

2. **How much work does the game actually do per frame?** Knowing the loop only says
   the skip is *available*, not that it is *enough*.

Neither can be read off the rom: a spin loop and an ordinary polling loop are the same
shape in a disassembly. So we run the game — see `scripts/idlefind`, which drives mGBA
headless with its idle-loop detector on and counts the cycles actually executed.

Two paths, in order:

* **Look it up.** `scripts/gba_idle_loop_db.json` holds everything already measured.
  Free, instant, and covers the games we have.
* **Measure it.** Only for a rom we have never seen. ~15s of one core, so callers run
  it in the background and behind a semaphore.

If the `idlefind` binary is not in the image (a plain dev checkout, say), measurement
is skipped and lookup still works. Never raises: a probe that fails leaves the rom
unmeasured, which the UI shows honestly.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# GBA cartridge header (GBATEK).
GAME_CODE_OFFSET = 0xAC
GAME_CODE_LENGTH = 4
FIXED_BYTE_OFFSET = 0xB2
FIXED_BYTE_VALUE = 0x96
HEADER_LENGTH = 0xC0

ROM_BASE = 0x8000000
FRAME_CYCLES = 280896
PROBE_FRAMES = "1500"          # ~25s of play: past the intro, into the game
PROBE_TIMEOUT = 300            # seconds; a hung rom must not wedge the queue

BINARY = shutil.which("idlefind")
DB_PATH = Path(__file__).resolve().parents[3] / "scripts" / "gba_idle_loop_db.json"

# One at a time. Measuring is a full core for ~15s, and a bulk upload would otherwise
# bury the box under a rom-per-core stampede while someone is trying to browse.
_probe_lock = asyncio.Semaphore(1)

_BRANCHES = {"b", "beq", "bne", "bcs", "bcc", "bmi", "bpl", "bhi", "bls",
             "bge", "blt", "bgt", "ble"}


@dataclass(frozen=True)
class Probe:
    """What we learned about a rom. `idle_pc` is the backward BRANCH that closes the
    wait loop — the PC gpSP compares against — not the loop's start, which is what
    mGBA reports."""
    game_code: str
    idle_pc: str | None
    exec_cycles: int | None
    source: str            # "db" | "measured"


def game_code(path: Path) -> str | None:
    """The 4-char code from the cart header, or None if this is not a GBA rom."""
    try:
        header = path.open("rb").read(HEADER_LENGTH)
    except OSError:
        return None
    if len(header) < HEADER_LENGTH or header[FIXED_BYTE_OFFSET] != FIXED_BYTE_VALUE:
        return None
    return header[GAME_CODE_OFFSET:GAME_CODE_OFFSET + GAME_CODE_LENGTH].decode("ascii", "replace")


def _load_db() -> dict[str, dict]:
    try:
        rows = json.loads(DB_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("gba idle-loop db unreadable (%s); measurement only", exc)
        return {}
    return {r["game_code"]: r for r in rows}


def lookup(code: str) -> Probe | None:
    """A rom we have already measured. Only run-verified rows count: an address that
    was guessed and never executed is worse than none, because gpSP would jump out of
    the frame somewhere that is not the wait loop."""
    row = _load_db().get(code)
    if not row or not row.get("exec_median"):
        return None
    idle_pc = row.get("idle_verified") if row.get("verify_tier") == "R" else None
    return Probe(code, idle_pc, row["exec_median"], "db")


def _branch_pc(rom: Path, loop_start: int) -> str | None:
    """mGBA reports the loop's START; gpSP wants the branch that jumps back to it."""
    if loop_start < ROM_BASE:
        return None   # some games copy the loop into IWRAM — not readable off disk
    try:
        from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
    except ImportError:
        log.warning("capstone missing; cannot convert the loop start to a branch pc")
        return None

    with rom.open("rb") as handle:
        handle.seek(loop_start - ROM_BASE)
        window = handle.read(64)

    for ins in Cs(CS_ARCH_ARM, CS_MODE_THUMB).disasm(window, loop_start):
        if ins.mnemonic not in _BRANCHES:
            continue
        try:
            target = int(ins.op_str.lstrip("#"), 16)
        except ValueError:
            continue
        if target == loop_start:
            return hex(ins.address)
    return None


async def measure(rom: Path) -> Probe | None:
    """Run the game. None if we have no binary, or the rom would not boot."""
    code = game_code(rom)
    if not code or not BINARY:
        return None

    async with _probe_lock:
        try:
            proc = await asyncio.create_subprocess_exec(
                BINARY, str(rom), PROBE_FRAMES,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            raw, _ = await asyncio.wait_for(proc.communicate(), timeout=PROBE_TIMEOUT)
        except (asyncio.TimeoutError, OSError) as exc:
            log.warning("gba probe failed for %s: %s", rom.name, exc)
            return None

    try:
        data = json.loads(raw.decode().strip().splitlines()[-1])
    except (ValueError, IndexError, UnicodeDecodeError):
        log.warning("gba probe returned nothing usable for %s", rom.name)
        return None

    cycles = data.get("exec_median")
    if not cycles:
        return None

    start = data.get("loop_start")
    idle_pc = _branch_pc(rom, int(start, 16)) if start else None

    # A rom whose loop was never found reports a full frame of work. That is not a
    # heavy game — it is a rom we failed to measure — so do not record it as an idle
    # loop, and let the cycle count stand as the (pessimistic) truth it is.
    if not idle_pc and cycles > 0.9 * FRAME_CYCLES:
        log.info("gba probe: no idle loop found for %s (%d cy/frame)", rom.name, cycles)

    return Probe(code, idle_pc, cycles, "measured")


async def probe(rom: Path) -> Probe | None:
    """Look it up; measure only if we have never seen it."""
    code = game_code(rom)
    if not code:
        return None
    hit = lookup(code)
    return hit if hit else await measure(rom)
