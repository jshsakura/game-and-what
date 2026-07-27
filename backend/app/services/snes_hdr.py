"""What a SNES cart carries besides ROM — read from its header, nothing run.

A SNES cartridge could ship its own silicon, and that is the one thing about a SNES
rom that decides whether a device port can run it at all. Star Fox does not merely
run slowly without a GSU: it does not run. So the useful question for `snes` is not
"how many cycles" — it is "what is in the cart".

WHY NOT THE GBA TREATMENT. `gba` gets a measured percentage because gpSP interprets
the same ARM instruction stream the probe counted, so guest cycles convert to device
milliseconds through one calibration constant (GBA_CPU_BUDGET, see components.jsx).
Nothing about that transfers here:

  * A SNES frame's cost is split across the 65816, the PPU (mode 7, HDMA, colour
    math) and the SPC700+DSP. Two games with identical CPU cycles can differ twofold
    on the device, so a single cycle count would libel one and flatter the other.
  * The two levers the GBA verdict leans on have no analogue. There is no idle-loop
    skip to find, and no guest software mixer to replace — SNES audio is a hardware
    DSP the emulator must actually run, so the trick that gives back 40% of a frame
    on Zelda simply does not exist here.
  * And this repository holds no SNES device timings (firmware/ is gba/ only), so
    there is no constant to calibrate a percentage against even if one fit.

So this states a FACT about the cart and stops there. It does not predict speed, and
it must not be dressed up as a verdict: which chips a given firmware supports is the
firmware's business, and that answer is not in this repo.

    read_chip(path) -> str   # 'none' | 'unknown' | 'SuperFX' | 'SA-1' | 'DSP' | …
"""
from __future__ import annotations

from pathlib import Path

# Header candidates, in the cart address space AFTER any copier header is dropped.
# LoROM keeps it at 0x7FC0, HiROM at 0xFFC0, and ExHiROM at 0x40FFC0.
_OFFSETS = (0x7FC0, 0xFFC0, 0x40FFC0)
_HDR_LEN = 0x30

# Byte 0x16 (rom type): the LOW nibble says whether a coprocessor is present at all,
# and only then does the HIGH nibble name it.
_HAS_COPROC = (0x3, 0x4, 0x5, 0x6)
_COPROC = {
    0x0: "DSP",       # Super Mario Kart, Pilotwings — small maths helper
    0x1: "SuperFX",   # Star Fox, Yoshi's Island — a 10/21 MHz RISC that draws the game
    0x2: "OBC1",      # Metal Combat — sprite bookkeeping, trivial
    0x3: "SA-1",      # Kirby Super Star, SMRPG — a SECOND 65816 at 10.74 MHz
    0x4: "S-DD1",     # Star Ocean, SF Alpha 2 — graphics decompression
    0x5: "S-RTC",     # Daikaijuu Monogatari II — a clock
    0xE: "Other",     # Super Game Boy / Satellaview bridging hardware
    0xF: "Custom",    # SPC7110, ST01x, CX4 — distinguished only by subtype byte
}

# Byte 0x15 (map mode). Some carts name their chip HERE and leave the rom-type byte
# looking ordinary; without this they would read as plain carts. The low nibble is the
# layout and bit 4 is the FastROM flag, so each mapping has two spellings:
#
#   0x20 / 0x30  LoROM          0x22 / 0x32  LoROM + S-DD1
#   0x21 / 0x31  HiROM          0x23 / 0x33  SA-1
#   0x25 / 0x35  ExHiROM
#
# 0x32 is the trap: it is S-DD1's fast spelling, one off SA-1's 0x33. Reading it as
# SA-1 files Star Ocean — an S-DD1 cart — as carrying a second 65816.
_MAP_SA1 = (0x23, 0x33)
_MAP_SDD1 = (0x22, 0x32)
_MAP_KNOWN = (0x20, 0x21, 0x22, 0x23, 0x25, 0x30, 0x31, 0x32, 0x33, 0x35)

# The chips that are not merely "extra silicon" but a different order of work: one is a
# RISC drawing every polygon, the other a second main CPU at three times the speed.
HEAVY = ("SuperFX", "SA-1")


def _score(hdr: bytes) -> int:
    """How much this window looks like a real header. The checksum and its complement
    must add up — that is the one test a random stretch of ROM does not pass by luck."""
    if len(hdr) < _HDR_LEN:
        return -1
    complement = int.from_bytes(hdr[0x1C:0x1E], "little")
    checksum = int.from_bytes(hdr[0x1E:0x20], "little")
    score = 0
    if (checksum ^ complement) == 0xFFFF:
        score += 8
    if hdr[0x15] in _MAP_KNOWN:
        score += 2
    if all(0x20 <= c < 0x7F or c >= 0x80 for c in hdr[0x00:0x15]):
        score += 1
    return score


def read_chip(path: str | Path) -> str:
    """The cart's coprocessor, or 'none' when there is none and 'unknown' when the
    header cannot be trusted (a bad dump, an overdump, a hacked ROM).

    'unknown' is deliberately NOT 'none': saying a cart is plain because we failed to
    read it would be inventing an answer, and the two need to stay tellable apart —
    the same reason the GBA probe carries `idle_hunted` (see db.py).
    """
    p = Path(path)
    try:
        size = p.stat().st_size
        # A .smc from a copier carries 512 bytes of its own in front of the cart.
        base = 512 if size % 1024 == 512 else 0
        best, best_hdr = 0, None
        with p.open("rb") as fh:
            for off in _OFFSETS:
                # Seek, never read the whole cart: the startup backfill walks the entire
                # snes library and a read_bytes() per rom would be gigabytes of I/O.
                if base + off + _HDR_LEN > size:
                    continue
                fh.seek(base + off)
                hdr = fh.read(_HDR_LEN)
                sc = _score(hdr)
                if sc > best:
                    best, best_hdr = sc, hdr
    except OSError:
        return "unknown"

    # Below the checksum test we are guessing, and a guessed coprocessor is worse than
    # an admitted blank.
    if best_hdr is None or best < 8:
        return "unknown"

    # The rom-type byte is the primary source; map mode only fills in for carts that
    # leave it blank, so a cart that names its chip properly is never overridden here.
    rom_type = best_hdr[0x16]
    if (rom_type & 0x0F) not in _HAS_COPROC:
        if best_hdr[0x15] in _MAP_SA1:
            return "SA-1"
        if best_hdr[0x15] in _MAP_SDD1:
            return "S-DD1"
        return "none"
    return _COPROC.get(rom_type >> 4, "Custom")


def backfill(conn, session_root: Path) -> int:
    """Stamp `snes_chip` onto snes roms that have never been read. Idempotent: a row
    only qualifies while the column is NULL, so a converged library costs one query at
    startup and nothing else. Returns how many rows were filled."""
    rows = conn.execute(
        "SELECT id, rom_path FROM roms WHERE system_key = 'snes' AND snes_chip IS NULL"
    ).fetchall()
    filled = 0
    for r in rows:
        chip = read_chip(session_root / r["rom_path"])
        conn.execute("UPDATE roms SET snes_chip = ? WHERE id = ?", (chip, r["id"]))
        filled += 1
    return filled
