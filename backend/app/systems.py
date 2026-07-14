"""
Systems usable in game-and-watch-retro-go-sd.

AUTHORITATIVE source: the SD firmware's own registration in
`Core/Src/retro-go/rg_emulators.c` (add_emulator(system, dirname, ext, ...)).
The device shows "Place roms in folder: /roms/<dirname>" + accepted extensions,
so dirname/exts below are taken verbatim from that file — only systems the SD
build actually registers appear here (Homebrew tab is excluded: it's for the
bundled apps, not user uploads).

Systems the UPSTREAM sylverb firmware does not register (fork-only additions)
carry `experimental=True` and are hidden unless GNW_EXPERIMENTAL_MODE is on —
see `available_systems()`.

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
    experimental: bool = False  # NOT in upstream sylverb rg_emulators.c — needs the fork firmware


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
    # PC Engine CD (a.k.a. TurboGrafx-CD). Upstream took it from this fork into main
    # on 2026-07-05, but the newest upstream RELEASE (v1.3.2, 2026-06-13) predates
    # that — so no firmware anyone can flash registers /roms/pcecd yet, and it stays
    # experimental until upstream cuts a release with it. CD images live in the
    # single /roms/pcecd/ folder as .chd (preferred) or .cue (+ .bin sidecars tracked
    # as extra_files); the firmware registers ".cue" only. Booting needs a
    # user-uploaded System Card BIOS (syscard3.pce). Browser play uses beetle-pce-fast:
    # single-file .chd boots, .cue/.bin sets need their track sidecars so they're
    # not browser-playable (see emulator.jsx).
    System("pcecd", "PC Engine CD", "pcecd", ("chd", "cue"), experimental=True),
    System("col", "Coleco Vision", "col", ("col",)),
    System("msx", "MSX", "msx", ("dsk", "rom", "mx1", "mx2", "cdk")),
    System("a2600", "Atari 2600", "a2600", ("a26", "bin")),
    System("a7800", "Atari 7800", "a7800", ("a78", "bin")),
    System("amstrad", "Amstrad CPC", "amstrad", ("dsk", "cdk")),
    System("wsv", "Supervision", "wsv", ("wsv", "sv", "bin")),
    # Neo Geo Pocket (mono + Color share one core). NOT yet in rg_emulators.c —
    # added for library collection (original No-Intro names, no Korean conversion);
    # all NGP/NGPC exts go in the single /roms/ngp/ folder. On-device play needs a
    # firmware build that includes the core. Few ROMs each, so mono+Color are kept
    # as ONE combined folder per family (NOT split like gb/gbc).
    System("ngp", "NEOGEO Pocket", "ngp", ("ngp", "ngc", "ngpc"), experimental=True),
    System("ws", "WonderSwan", "ws", ("ws", "wsc"), experimental=True),
    # Atari Lynx (handy-go core). Same story as pcecd: registered in upstream main
    # on 2026-07-05, but not in the newest upstream RELEASE (v1.3.2), so a stock
    # firmware still ignores /roms/lynx. Experimental until that release lands.
    # Standard extension is ".lnx".
    System("lynx", "Atari Lynx", "lynx", ("lnx",), experimental=True),
    # Nintendo Virtual Boy — NOT in rg_emulators.c (no SD core); added as a
    # library-collection system with original No-Intro names. Standard extension
    # is ".vb". Browser play works via the mednafen_vb (beetle-vb) core; .vb files
    # are headerless but the core boots them HLE, so no BIOS is needed.
    System("vb", "Virtual Boy", "vb", ("vb",), experimental=True),
    # Game Boy Advance — NOT in rg_emulators.c. The firmware would need a gpSP
    # port, and gpSP only reaches full speed on a game whose VBlank busy-wait it
    # can skip; that skip is driven by a hand-maintained table of loop addresses
    # (gba_over.h), keyed on the 4-char code in the cart header. A game missing
    # from that table never skips at all. scripts/gba_idle_match.py reads the
    # header of each ROM and reports which ones the table covers — that is what
    # the idle_loop flag records. Browser play uses mGBA (see emulator.jsx).
    System("gba", "Game Boy Advance", "gba", ("gba",), experimental=True),
    # Magnavox Odyssey² / Philips Videopac (same hardware). The firmware has a
    # videopac core (main_videopac.c) but its add_emulator is commented out, so
    # it's library-collection only for now (TOSEC .bin names). dirname "videopac"
    # matches the firmware folder so it lines up if that core is ever enabled.
    System("videopac", "Odyssey²", "videopac", ("bin",), experimental=True),
    # ZX Spectrum & Commodore 64 — library-collection only (no firmware/web core
    # yet). Z80/6502 home computers with huge libraries; common emulator formats.
    System("zxs", "ZX Spectrum", "zxs", ("z80", "tap", "tzx", "sna", "szx"), experimental=True),
    System("c64", "Commodore 64", "c64", ("d64", "t64", "prg", "crt", "g64", "tap"), experimental=True),
    # Tiger Game.com — cartridge handheld (Sharp SM8500). dirname "gamecom"
    # matches the firmware /roms/gamecom folder; carts are ".bin"/".tgc".
    System("gamecom", "Tiger Game.com", "gamecom", ("bin", "tgc"), experimental=True),
    System("tama", "Tamagotchi", "tama", ("b",)),
    System("mini", "Pokémon Mini", "mini", ("min",)),
    # Device-only: the firmware plays LCD-Game-Shrinker ".gw" files. The MADrigal
    # ".mgw" format (web gw-libretro only) was dropped — it can't run on hardware
    # and can't be converted to .gw (it carries a behavioural script, not the SM510
    # CPU dump that .gw needs). See the gw-format-device-only note.
    System("gw", "Game & Watch", "gw", ("gw",)),
    # "bin" = homebrew app payload; "dat" = the assets file some ports need at
    # /roms/homebrew/ (SMW → smw_assets.dat, Zelda3 → zelda3_assets.dat), uploaded
    # as its own item + cover. Both ride along when opted into the SD ZIP.
    # "xip"/"smc" = Super Metroid's two extra files. It does not have an assets
    # file: the port reads the original SNES ROM at runtime (sm.smc), and its cold
    # banks plus rodata execute out of QSPI flash from sm.xip. Neither is a ".bin",
    # so both always ship — which is what the port needs; it will not boot without
    # them. Zelda3's zelda3.ro rides along the same way.
    System("homebrew", "Homebrew", "homebrew", ("bin", "dat", "xip", "smc"), square=True),
    System("pico8", "PICO-8", "pico8", ("p8", "png"), pico8=True, square=True),
)
# NOTE: "videopac" is commented out (disabled) in rg_emulators.c, so it is NOT a
# usable SD folder — intentionally excluded.

_BY_KEY: dict[str, System] = {s.key: s for s in SYSTEMS}
_BY_DIRNAME: dict[str, System] = {s.dirname: s for s in SYSTEMS}

# /roms + /covers dirnames that exist only on the fork firmware — used to keep
# them out of the SD ZIP when experimental mode is off.
EXPERIMENTAL_DIRNAMES: frozenset[str] = frozenset(s.dirname for s in SYSTEMS if s.experimental)


def available_systems() -> tuple[System, ...]:
    """Systems this deploy exposes: everything in experimental ("personal lab")
    mode, otherwise only what the upstream sylverb firmware officially registers
    (up to Atari Lynx)."""
    from . import config
    if config.EXPERIMENTAL_MODE:
        return SYSTEMS
    return tuple(s for s in SYSTEMS if not s.experimental)


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
