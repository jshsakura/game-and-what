"""The sound driver: which one the cart links in, and what it costs per frame.

**Why this belongs in a CPU-load tool.** A GBA game does not write its own mixer. It links
in a library — Nintendo's M4A (Sappy) in most carts, Shin'en's GAX in a few — which is
copied into IWRAM at boot and run there every frame, sample by sample, in the guest's ARM
code. The firmware replaces that driver with a native one, so **on the device the guest
never executes it at all.**

Which means an exec_cycles figure that includes it is wrong by however much the game's music
costs — and that is not a rounding error. On Zelda: A Link to the Past it is most of the
frame.

Two questions, and neither needs the emulator:

* **Which driver?** M4A's mixer is a single ARM block sitting verbatim in the rom (the
  library only *copies* it to IWRAM), and it is unmistakable: it opens with `str r8, [sp]`
  and closes with `ldr r8, [sp] / add r0, pc, #1 / bx r0`. Cut it out and hash it, and the
  whole library falls into a handful of variants — the same handful the firmware has to
  implement. GAX is easier still: it prints its own version string into the rom.
* **What does it cost?** THAT one we measure, per game, rather than model. The block's bytes
  are known, so the binary finds where they landed in RAM and adds up the cycles the
  histogram already charged to that range (IDLEFIND_BLOCK). No estimating a share.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

# ARM, little-endian. The mixer's prologue and epilogue.
M4A_START = bytes.fromhex("00808de5")                      # str r8, [sp]
M4A_END = bytes.fromhex("00809de5" "01008fe2" "10ff2fe1")  # ldr r8,[sp]; add r0,pc,#1; bx r0
M4A_MAX = 2048          # the real blocks are 300–510 bytes; further than this is a mismatch

GAX_STRING = re.compile(rb"GAX Sound Engine[ v0-9.,A-Za-z()]*")


# The firmware's names for the M4A builds, keyed by OUR hash of the block.
#
# These are not custom mixers. M4A (Sappy / MusicPlayer2000) is Nintendo's own sound
# library, linked into the cart; the handful of variants are its handful of SDK builds
# (mono, stereo, a couple of later revisions). That is why 633 roms collapse into six —
# and why implementing six natively retires the cost for the whole library, permanently.
#
# game-and-watch-retro-go-sd owns these names; we cross-checked them against our own scan
# (same block sizes, same cart ranking, same representative game) and adopt them, because a
# hash is not a name anybody can act on. Blank = a variant nobody has named yet.
M4A_VARIANTS = {
    "1b020ff71edf": "stereo2",   # 488B/122 instr — the big one (Zelda: ALTTP)
    "572b3042cb43": "mono",      # 412B/103       — (FFTA, Gradius Generation)
    "121ad9cf183a": "stereo3",   # 488B/122       — (Gachinko Pro Yakyuu)
    "2520703b4098": "stereo",    # 508B/127       — every Pokémon (Ruby/Sapphire/Emerald/FR/LG)
    "7e6932218017": "",          # 336B/84        — (Castlevania: CotM, ChuChu Rocket), NOT
                                 #                  implemented natively yet — a game on this
                                 #                  build still pays for its music in full.
}


@dataclass(frozen=True)
class Driver:
    """The sound driver a cart carries."""
    engine: str               # "m4a" | "gax"
    variant: str              # m4a: 12 hex of the block's hash. gax: its version string.
    name: str                 # what the firmware calls it: stereo2 / mono / stereo3 / …
    block: bytes | None       # the code itself, for measuring what it costs at run time
    rom_offset: int | None

    @property
    def size(self) -> int:
        return len(self.block) if self.block else 0

    def __str__(self) -> str:
        where = f", {self.size}B/{self.size // 4} instr" if self.block else ""
        named = f" ({self.name})" if self.name else ""
        return f"{self.engine}:{self.variant}{named}{where}"


def find_m4a(data: bytes) -> Driver | None:
    """Cut the M4A mixer out of the rom and name it by its hash.

    The variant is what matters to the firmware: every cart carrying the same block gets the
    same native implementation. 633 roms collapse into six.
    """
    start = data.find(M4A_START)
    if start < 0:
        return None
    end = data.find(M4A_END, start)
    if end < 0 or end - start > M4A_MAX:
        return None

    block = data[start:end + len(M4A_END)]
    variant = hashlib.sha256(block).hexdigest()[:12]
    return Driver("m4a", variant, M4A_VARIANTS.get(variant, ""), block, start)


def find_gax(data: bytes) -> Driver | None:
    """GAX names itself. `GAX Sound Engine 3.03A (Mar  5 2003)`, right there in the rom."""
    m = GAX_STRING.search(data)
    if not m:
        return None
    version = m.group().decode("ascii", "replace").strip()
    return Driver("gax", version, "", None, m.start())


def detect(rom: Path | str) -> Driver | None:
    """Which sound driver, if any. M4A first: it is the one in 55% of the library."""
    try:
        data = Path(rom).read_bytes()
    except OSError:
        return None
    return find_m4a(data) or find_gax(data)


def measure(rom: Path | str, driver: "Driver | None" = None, frames: int = 1200) -> int | None:
    """What the sound driver costs this game, per frame, in cycles. Measured, not modelled.

    The binary finds where the block landed in RAM (the library copies it to IWRAM at boot)
    and adds up the cycles the per-PC histogram already charged to that range. It runs with
    the idle skip OFF, which does not matter: the wait loop and the mixer are different code,
    so the mixer's cost is the same either way, and this way no address is needed.

    None = no driver, or its block never ran (GAX has no block to cut: it identifies itself
    by a version string, and HLE'ing it is a firmware question, not a measuring one).
    """
    from . import runner

    driver = driver or detect(rom)
    if not driver or not driver.block or not runner.available():
        return None
    data = runner.raw(rom, forced_pc=runner.NO_SKIP, frames=frames,
                      env={"IDLEFIND_BLOCK": driver.block.hex()})
    cycles = (data or {}).get("block_cycles") or 0
    return cycles or None


def loop_start_of(rom: Path | str, gpsp_pc: str) -> str:
    """mGBA halts at the loop's START (a jump target); the table stores gpSP's BRANCH pc.

    They are two ends of the same loop, and the branch's target is the start — so read it
    straight out of the instruction rather than re-hunting the game. Where the stored pc is
    a landing point already (a loop that hops has no single closing branch), it IS the start.
    """
    from .hunt import _disasm

    pc = int(gpsp_pc, 16)
    if pc < 0x8000000:            # a RAM address: we cannot read it off the disk
        return gpsp_pc
    try:
        with Path(rom).open("rb") as fh:
            fh.seek(pc - 0x8000000)
            window = fh.read(8)
    except OSError:
        return gpsp_pc
    for ins in _disasm(window, pc):
        if ins.address != pc:
            continue
        try:
            target = int(ins.op_str.lstrip("#"), 16)
        except ValueError:
            break
        if target < pc:           # backward: this is the branch that closes the loop
            return hex(target)
        break
    return gpsp_pc


def cost(rom: Path | str, gpsp_pc: str | None = None, frames: int = 1200):
    """The sound driver AND the game's real work, from ONE run — which is the only way the
    two numbers can be subtracted from each other.

    Measured separately they disagree: the mixer's cost depends on what music is playing, so
    a run that reached a different scene reports a different number, and Castlevania came out
    with a mixer bill LARGER than its total work. Same run, same scene, same frames.
    """
    from . import runner

    driver = detect(rom)
    if not driver or not driver.block or not runner.available():
        return driver, None, None
    forced = loop_start_of(rom, gpsp_pc) if gpsp_pc else runner.NO_SKIP
    data = runner.raw(rom, forced_pc=forced, frames=frames,
                      env={"IDLEFIND_BLOCK": driver.block.hex()})
    if not data:
        return driver, None, None
    return driver, (data.get("block_cycles") or None), data.get("exec_median")
