"""
Systems usable in game-and-watch-retro-go-sd.

AUTHORITATIVE source: the SD firmware's own registration in
`Core/Src/retro-go/rg_emulators.c` (add_emulator(system, dirname, ext, ...)).
The device shows "Place roms in folder: /roms/<dirname>" + accepted extensions,
so dirname/exts below are taken verbatim from that file — only systems the SD
build actually registers appear here (Homebrew tab is excluded: it's for the
bundled apps, not user uploads).

`lzma` is a cross-system compression wrapper the firmware also accepts; it is
not a per-system format, so it's tracked separately, not in each row.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class System:
    key: str               # internal id (== dirname)
    name: str              # label as shown by the firmware
    dirname: str           # /roms/<dirname> and /covers/<dirname>
    exts: tuple[str, ...]  # accepted rom extensions (lowercase, no dot)
    pico8: bool = False    # special cover handling (.p8 / .p8.png label)
    square: bool = False   # 1:1 label-style art instead of 3:4 box art


# Cover aspect policy. The firmware grid (gui_draw_coverflow_v) sizes the
# selection frame from ONE cover per system, then centers every other cover
# inside that frame — so covers of differing sizes overflow or float. We pin a
# single size per system: portrait 3:4 box art for game consoles, 1:1 square for
# label-style art (homebrew apps, PICO-8 cart labels). Both fit the 186x100 box.
COVER_GAME: tuple[int, int] = (75, 100)     # 3:4 portrait, fills the 100px height
COVER_SQUARE: tuple[int, int] = (100, 100)  # 1:1


# Firmware also accepts these as a compression wrapper on any rom.
COMPRESSED_EXT = "lzma"

# Verbatim from Core/Src/retro-go/rg_emulators.c (SD build).
# `name` = short common label for UI buttons. `dirname` = exact firmware folder.
SYSTEMS: tuple[System, ...] = (
    System("nes", "NES", "nes", ("nes", "fds", "nsf")),
    System("gb", "Game Boy", "gb", ("gb", "gbc")),
    System("gbc", "GB Color", "gbc", ("gb", "gbc")),
    System("gg", "Game Gear", "gg", ("gg",)),
    System("sms", "Master System", "sms", ("sms",)),
    System("md", "Genesis", "md", ("md", "gen", "bin")),
    System("sg", "SG-1000", "sg", ("sg",)),
    System("pce", "PC Engine", "pce", ("pce",)),
    System("col", "ColecoVision", "col", ("col",)),
    System("msx", "MSX", "msx", ("dsk", "rom", "mx1", "mx2", "cdk")),
    System("a2600", "Atari 2600", "a2600", ("a26", "bin")),
    System("a7800", "Atari 7800", "a7800", ("a78", "bin")),
    System("amstrad", "Amstrad CPC", "amstrad", ("dsk", "cdk")),
    System("wsv", "Watara", "wsv", ("wsv", "sv", "bin")),
    # Neo Geo Pocket (mono + Color share one core). NOT yet in rg_emulators.c —
    # added for library collection (original No-Intro names, no Korean conversion);
    # all NGP/NGPC exts go in the single /roms/ngp/ folder. On-device play needs a
    # firmware build that includes the core. Few ROMs each, so mono+Color are kept
    # as ONE combined folder per family (NOT split like gb/gbc).
    System("ngp", "Neo Geo Pocket", "ngp", ("ngp", "ngc", "ngpc")),
    System("ws", "WonderSwan", "ws", ("ws", "wsc")),
    # Atari Lynx. The SD build ships the handy-go core (external/handy-go), so a
    # firmware that registers it can play these on-device; added here for library
    # collection with original No-Intro names. Standard extension is ".lnx".
    System("lynx", "Atari Lynx", "lynx", ("lnx",)),
    System("tama", "Tamagotchi", "tama", ("b",)),
    System("mini", "Pokémon Mini", "mini", ("min",)),
    # Firmware registers ext "gw"; many G&W rom packs ship as ".mgw" — accept both.
    System("gw", "Game & Watch", "gw", ("gw", "mgw")),
    # "bin" = homebrew app payload; "dat" = the assets file some ports need at
    # /roms/homebrew/ (SMW → smw_assets.dat, Zelda3 → zelda3_assets.dat), uploaded
    # as its own item + cover. Both ride along when opted into the SD ZIP.
    System("homebrew", "Homebrew", "homebrew", ("bin", "dat"), square=True),
    System("pico8", "PICO-8", "pico8", ("p8", "png"), pico8=True, square=True),
)
# NOTE: "videopac" is commented out (disabled) in rg_emulators.c, so it is NOT a
# usable SD folder — intentionally excluded.

_BY_KEY: dict[str, System] = {s.key: s for s in SYSTEMS}
_BY_DIRNAME: dict[str, System] = {s.dirname: s for s in SYSTEMS}


def get_system(key: str) -> System:
    """Look up a system by its key. Raises KeyError if unknown."""
    return _BY_KEY[key]


def cover_target(system: "System | str") -> tuple[int, int]:
    """Fixed (width, height) every cover of this system is normalized to, so the
    firmware grid frame fits them all. Square for label art, 3:4 for box art."""
    s = system if isinstance(system, System) else _BY_KEY[system]
    return COVER_SQUARE if s.square else COVER_GAME


def get_by_dirname(dirname: str) -> System | None:
    return _BY_DIRNAME.get(dirname)


def accepts_extension(system: System, filename: str) -> bool:
    """True if filename's extension is valid for this system (or lzma-wrapped)."""
    lower = filename.lower()
    if system.pico8:
        return lower.endswith(".p8") or lower.endswith(".p8.png") or lower.endswith(".png")
    suffix = lower.rsplit(".", 1)[-1] if "." in lower else ""
    return suffix in system.exts or suffix == COMPRESSED_EXT
