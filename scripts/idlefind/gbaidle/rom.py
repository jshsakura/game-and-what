"""The cart header, and the one rule about it: MATCH ON THE HEADER, NEVER THE FILENAME.

This has bitten the project twice, and both times it produced a wrong address that PASSED
its check. A library renames files, so a name lookup can hand you a different game
entirely — F-Zero Climax's address was A/B'd against another rom and sailed through. And a
Korean patch keeps the ORIGINAL header, which is exactly why the header is the only key
worth trusting: the patch has moved the loop but not the name gpSP looks it up under.
"""
from __future__ import annotations

from pathlib import Path

# GBA cartridge header (GBATEK).
GAME_CODE_OFFSET = 0xAC
GAME_CODE_LENGTH = 4
FIXED_BYTE_OFFSET = 0xB2      # always 0x96 on a real cart; our "is this a GBA rom" check
FIXED_BYTE_VALUE = 0x96
HEADER_LENGTH = 0xC0

ROM_BASE = 0x08000000
ROM_TOP = 0x09FFFFFF
IWRAM_BASE = 0x03000000
EWRAM_BASE = 0x02000000


def game_code(path: Path | str) -> str | None:
    """The 4 chars at rom[0xAC], or None if this is not a GBA rom."""
    try:
        header = Path(path).open("rb").read(HEADER_LENGTH)
    except OSError:
        return None
    if len(header) < HEADER_LENGTH or header[FIXED_BYTE_OFFSET] != FIXED_BYTE_VALUE:
        return None
    return header[GAME_CODE_OFFSET:GAME_CODE_OFFSET + GAME_CODE_LENGTH].decode("ascii", "replace")


def index_by_code(rom_dir: Path | str) -> dict[str, Path]:
    """Every rom in a directory, keyed by its cart code. The ONLY way to find a rom."""
    out: dict[str, Path] = {}
    for path in sorted(Path(rom_dir).glob("*.gba")):
        code = game_code(path)
        if code:
            out.setdefault(code, path)
    return out


def region_of(pc: int) -> str:
    """Which memory a pc lives in. Not academic: the Classic NES / Famicom Mini carts are
    6502 interpreters that copy their core into IWRAM and wait THERE, so their idle loop
    is not in the rom file at all. gpSP does not care — cpu.cc:3063 compares reg[REG_PC]
    after every instruction, whatever region it points at — and neither do we."""
    if ROM_BASE <= pc <= ROM_TOP:
        return "ROM"
    if pc >= IWRAM_BASE:
        return "IWRAM"
    if pc >= EWRAM_BASE:
        return "EWRAM"
    return "?"
