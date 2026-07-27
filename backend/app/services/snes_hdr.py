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

import re
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

# The low nibble names the layout; S-DD1 and SA-1 carts reuse the LoROM/HiROM shapes,
# so they map back to those rather than to a fourth name.
_MAP_LAYOUT = {0x0: "LoROM", 0x1: "HiROM", 0x2: "LoROM", 0x3: "LoROM", 0x5: "ExHiROM"}

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


def read_header(path: str | Path) -> dict:
    """What the cart declares about itself:

        {"chip": str, "map": str | None, "rom_kb": int | None}

    `chip` is the coprocessor, 'none' when there is none, and 'unknown' when the header
    cannot be trusted (a bad dump, an overdump, a hacked ROM). 'unknown' is deliberately
    NOT 'none': saying a cart is plain because we failed to read it would be inventing an
    answer, and the two need to stay tellable apart — the same reason the GBA probe
    carries `idle_hunted` (see db.py). When chip is 'unknown' the rest is None, because
    it came off the same bytes we just said we do not trust.

    `map` is the memory layout the cart wants — 'LoROM', 'HiROM', 'ExHiROM', each with
    ' · FastROM' appended when the cart asks for 3.58 MHz access. It matters for the same
    reason the chip does: a port implements a mapper or it does not.
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
        return {"chip": "unknown", "map": None, "rom_kb": None, "title": None}

    # Below the checksum test we are guessing, and a guessed coprocessor is worse than
    # an admitted blank.
    if best_hdr is None or best < 8:
        return {"chip": "unknown", "map": None, "rom_kb": None, "title": None}

    # The rom-type byte is the primary source; map mode only fills in for carts that
    # leave it blank, so a cart that names its chip properly is never overridden here.
    rom_type = best_hdr[0x16]
    if (rom_type & 0x0F) in _HAS_COPROC:
        chip = _COPROC.get(rom_type >> 4, "Custom")
    elif best_hdr[0x15] in _MAP_SA1:
        chip = "SA-1"
    elif best_hdr[0x15] in _MAP_SDD1:
        chip = "S-DD1"
    else:
        chip = "none"

    # Byte 0x15 again, this time for the layout. Bit 4 is the FastROM flag, so each
    # layout has a slow and a fast spelling and the low nibble is what names it.
    mode = best_hdr[0x15]
    layout = _MAP_LAYOUT.get(mode & 0x0F)
    mapping = f"{layout} · FastROM" if layout and (mode & 0x10) else layout

    # Byte 0x17 is log2 of the size in KB. Sane carts land between 256 KB and 48 Mbit;
    # anything outside that is a header we should not be quoting figures from.
    exp = best_hdr[0x17]
    rom_kb = (1 << exp) if 8 <= exp <= 13 else None

    return {"chip": chip, "map": mapping, "rom_kb": rom_kb,
            "title": _internal_title(best_hdr)}


# A cart title has to be worth searching for. Two letters and a digit is not a game
# name, and neither is a row of padding.
_TITLE_MIN_LETTERS = 3


def _internal_title(hdr: bytes) -> str | None:
    """The 21-byte name the cart calls itself, at offset 0x00.

    This is the only LATIN name a Korean-titled rom carries. A file named
    '혼두라 스피릿츠.smc' gives a cover search nothing to work with — IGDB and
    TheGamesDB index English and romaji, and asking them in Korean returns nothing at
    all (measured: five such titles, five misses). The header answers in ASCII:
    'R-타입III' is 'R-TYPE 3' in here, 'GP-1 래피드 스트림' is 'GP-1 Rapid Stream'.

    Japanese carts often fill this field with Shift-JIS, which is not a search term in
    any useful sense, so anything that does not survive as ASCII is dropped. So is
    padding and boilerplate too short to be a name — several SD Gundam data carts all
    say 'ADD-ON BASE CASSETE', which would search as confidently as it is useless.
    Nothing downstream trusts this blindly: it is one more candidate term, and the
    title-match guard still has to agree before any art is stamped.
    """
    raw = hdr[0x00:0x15]
    text = raw.decode("ascii", "ignore")
    # \x00 padding, and the 0x20-padded field's trailing run.
    text = re.sub(r"[^\x20-\x7E]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if sum(c.isalpha() for c in text) < _TITLE_MIN_LETTERS:
        return None
    return text


def read_chip(path: str | Path) -> str:
    """Just the coprocessor. Kept because that is what the roms table stores and what
    the upload path and backfill below both want."""
    return read_header(path)["chip"]


def backfill(conn, session_root: Path) -> int:
    """Stamp the header fields onto snes roms that have never been read. Idempotent: a
    row only qualifies while snes_chip is NULL, so a converged library costs one query at
    startup and nothing else. Returns how many rows were filled."""
    rows = conn.execute(
        "SELECT id, rom_path FROM roms WHERE system_key = 'snes' AND snes_chip IS NULL"
    ).fetchall()
    filled = 0
    for r in rows:
        h = read_header(session_root / r["rom_path"])
        conn.execute(
            "UPDATE roms SET snes_chip = ?, snes_map = ?, snes_rom_kb = ?, "
            "snes_title = ? WHERE id = ?",
            (h["chip"], h["map"], h["rom_kb"], h["title"], r["id"]),
        )
        filled += 1
    return filled
