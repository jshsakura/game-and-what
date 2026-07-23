"""CPS-1 romset identification and folder composition.

A CPS-1 game is not a file. It is a MAME romset: a dozen or so 512 KB chip
dumps that belong together, distributed as a zip, and often as a "split set"
whose clone archive holds only the chips unique to that release. Two facts
drive everything in here.

**Chips are identified by CRC32, never by filename.** A romset's ROM_LOAD order
is not its filename order: in Warriors of Fate, tk2_gfx3.rom belongs in
graphics slot 1 and tk2_gfx2.rom in slot 2, and the Japanese set's upper four
chips are named tk205..tk208, which sort ahead of tk2_gfx1..4 entirely. Fill
the slots by name and every file loads, every size checks out, and two bitplane
pairs are silently cross-wired -- the firmware measured that mistake at 85% of
the graphics region corrupted, with nothing anywhere reporting an error. MAME's
own ROM_LOAD macros bind a chip's hash to an offset for this reason.

**The device needs a folder; the browser would need the zip.** The firmware
caches each chip into external flash and executes/reads it in place (XIP),
which only works on raw chip bytes -- it has neither an inflate in the emulator
path nor anywhere to put 4 MB of decompressed graphics against 724 KB of RAM.
An arcade core in the browser (FBNeo, MAME) is the opposite: it has its own
archive reader and wants the zip. So the zip stays the master artifact in the
library and the folder is COMPOSED for the SD card, rather than one being
converted into the other.

The romset table lives in app/assets/cps1_romsets.json and is shared
byte-for-byte with the firmware repository, which generates its C table from
the same file. Do not hand-edit either side; see docs/CPS1_LIBRARY_CONTRACT.md.
"""
from __future__ import annotations

import json
import shutil
import zipfile
import zlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ASSET_PATH = Path(__file__).resolve().parent.parent / "assets" / "cps1_romsets.json"

#: Every CPS-1 chip in every supported set is 512 KB. A file of any other size
#: cannot be one, which is what lets a PAL dump (279 B) be skipped without being
#: read, and what the firmware's own directory scan filters on.
CHIP_SIZE = 0x80000


class IncompleteRomset(Exception):
    """Raised rather than writing a folder the device cannot boot."""


@lru_cache(maxsize=1)
def _table() -> dict:
    return json.loads(ASSET_PATH.read_text())


def romsets() -> list[dict]:
    return _table()["romsets"]


def romset(name: str) -> dict | None:
    return next((s for s in romsets() if s["name"] == name), None)


def _required(rs: dict) -> list[str]:
    """Every chip CRC a set needs, program chips first."""
    return [c["crc32"] for c in rs["prg"]] + [c["crc32"] for c in rs["gfx"]]


def chips_in_archives(archives) -> dict[str, tuple[str, str]]:
    """CRC32 -> (archive name, member name) for every chip-sized member.

    `archives` is an iterable of (name, zip bytes or path). Members that are not
    exactly one chip long are skipped without being decompressed further than
    the header, so PAL dumps and readmes cost nothing. The first archive to
    supply a given hash wins; a second copy of identical bytes is not a
    conflict, it is the same chip.
    """
    found: dict[str, tuple[str, str]] = {}
    for archive_name, source in archives:
        with _open_zip(source) as zf:
            for info in zf.infolist():
                if info.is_dir() or info.file_size != CHIP_SIZE:
                    continue
                data = zf.read(info)
                crc = "%08x" % (zlib.crc32(data) & 0xFFFFFFFF)
                found.setdefault(crc, (archive_name, info.filename))
    return found


def _open_zip(source):
    if isinstance(source, (bytes, bytearray)):
        import io
        return zipfile.ZipFile(io.BytesIO(source))
    return zipfile.ZipFile(source)


@dataclass
class Identification:
    """What a pile of archives turned out to be."""

    setname: str | None = None
    title: str | None = None
    parent: str | None = None
    missing_crcs: list[str] = field(default_factory=list)
    #: CRC -> (archive, member) for everything that WAS found, chip-sized only.
    found: dict[str, tuple[str, str]] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return self.setname is not None and not self.missing_crcs

    def message(self) -> str:
        """One line a user can act on."""
        if self.setname is None:
            return "No known CPS-1 romset recognised in these files."
        if self.complete:
            return f"{self.setname}: complete ({self.title})."
        total = len(_required(romset(self.setname)))
        msg = (f"{self.setname}: {len(self.missing_crcs)} of {total} chips missing")
        if self.parent:
            msg += f" — add the parent romset ({self.parent})"
        return msg + "."


def identify(archives) -> Identification:
    """Which romset these archives are, and what is still missing.

    Picks the set with the FEWEST missing chips, so a clone archive on its own
    is reported as that clone needing its parent, rather than as nothing at all.
    A tie goes to the set declared first in the table.
    """
    found = chips_in_archives(archives)
    best: Identification | None = None

    for rs in romsets():
        required = _required(rs)
        missing = [c for c in required if c not in found]
        if len(missing) == len(required):
            continue                     # nothing of this set is here at all
        cand = Identification(setname=rs["name"], title=rs.get("title"),
                              parent=rs.get("parent"), missing_crcs=missing,
                              found=found)
        if best is None or len(cand.missing_crcs) < len(best.missing_crcs):
            best = cand

    if best is None:
        return Identification(found=found)
    return best


def match_crcs(crcs: list[str]):
    """The firmware's own matcher, in Python: first fully-satisfied set.

    Returns (setname, prg indices, gfx indices) into `crcs`, or None. Used to
    assert that a composed folder is one the device will accept -- the library
    and the device must agree on that, and the only honest way to know is to
    run the same rule.
    """
    for rs in romsets():
        prg, gfx, ok = [], [], True
        for chip in rs["prg"]:
            if chip["crc32"] not in crcs:
                ok = False
                break
            prg.append(crcs.index(chip["crc32"]))
        if ok:
            for chip in rs["gfx"]:
                if chip["crc32"] not in crcs:
                    ok = False
                    break
                gfx.append(crcs.index(chip["crc32"]))
        if ok:
            return rs["name"], prg, gfx
    return None


def archives_in(game_dir: Path) -> list[tuple[str, Path]]:
    """Every romset archive a game folder holds, oldest name first.

    A CPS-1 game on the server is a FOLDER of zips, not one file: the clone
    archive, and — when the set is a MAME split set — its parent's alongside it.
    Uploading again just adds or replaces a zip in that folder, which is what
    makes re-uploading safe with nothing to invalidate.
    """
    if not game_dir.is_dir():
        return []
    return [(p.name, p) for p in sorted(game_dir.iterdir())
            if p.is_file() and p.suffix.lower() == ".zip"]


@dataclass(frozen=True)
class ChipEntry:
    """One chip on its way to the card, still inside its archive."""

    archive: Path
    member: str
    name: str       # what it is called on the card (its original MAME name)
    size: int


def sd_chip_entries(game_dir: Path) -> list[ChipEntry]:
    """What `game_dir` should expand to on the SD card, or [] if it cannot.

    Returns the chips of the single complete romset the folder's archives add up
    to. An incomplete folder yields NOTHING rather than a partial set: half a
    romset on the card is a game that reaches the device and dies there, which
    is strictly worse than a game that is visibly absent and reported at upload.

    Nothing is written or cached. The card's copy is produced during packaging,
    straight out of the archives — 65 ms for a whole set on the deployment host,
    measured — so there is no extracted copy to double the storage and no cache
    to go stale when the user later supplies the missing parent.
    """
    archives = archives_in(game_dir)
    if not archives:
        return []
    ident = identify([(name, path) for name, path in archives])
    if not ident.complete:
        return []

    by_name = {name: path for name, path in archives}
    sizes: dict[tuple[str, str], int] = {}
    for name, path in archives:
        with _open_zip(path) as zf:
            for info in zf.infolist():
                sizes[(name, info.filename)] = info.file_size

    entries = []
    for crc in _required(romset(ident.setname)):
        archive_name, member = ident.found[crc]
        entries.append(ChipEntry(
            archive=by_name[archive_name],
            member=member,
            name=Path(member).name,        # never trust a path inside a zip
            size=sizes.get((archive_name, member), CHIP_SIZE),
        ))
    return entries


def all_chip_entries(game_dir: Path) -> list[ChipEntry]:
    """Every chip in the folder's archives, deduped by content CRC and NAMED BY
    that CRC -- the whole pool, extracted as-is, not one guessed romset's slice.

    sd_chip_entries() picks the single set with the fewest missing chips and
    ships only that set's chips. That is minimal, but it makes the card and the
    device guess independently: the packager here identified the folder as
    `wofj` and the firmware, from the same chips, went for `wofr1` and reported
    two absent -- chips that WERE in the archives but were left behind because
    they belonged to the set the packager did not pick.

    So ship the whole pool. The device binds a chip to a slot by CRC, never by
    filename and never by which set we guessed (Core/Src/porting/cps1), so extra
    chips are free -- it takes what its chosen set needs and ignores the rest --
    and no chip any runnable set might need is ever dropped. Files are named
    `<crc>.bin`, which is also the shared-pool name the firmware looks up, so the
    same output doubles as a /roms/cps1/.shared pool.

    Still returns [] when the folder completes NO set: a pool that cannot make
    even one playable game ships nothing rather than a folder that reaches the
    launcher and dies. That guard is the one thing worth guessing a set for.
    """
    archives = archives_in(game_dir)
    if not archives:
        return []
    if not identify([(name, path) for name, path in archives]).complete:
        return []

    entries: list[ChipEntry] = []
    seen: set[str] = set()
    for name, path in archives:
        with _open_zip(path) as zf:
            for info in zf.infolist():
                if info.is_dir() or info.file_size != CHIP_SIZE:
                    continue
                crc = "%08x" % (zlib.crc32(zf.read(info)) & 0xFFFFFFFF)
                if crc in seen:                 # same bytes in two archives = one chip
                    continue
                seen.add(crc)
                entries.append(ChipEntry(
                    archive=path,
                    member=info.filename,
                    name=f"{crc}.bin",          # by content, never by on-disk name
                    size=info.file_size,
                ))
    return entries


@dataclass(frozen=True)
class PlannedGame:
    """One romset that should become a library entry."""

    setname: str
    title: str | None
    #: Archives whose chips this set needs — ALL of them belong in its folder,
    #: because the device scans that one directory and nothing else.
    archives: tuple[str, ...]
    #: The archives it had to borrow from. Non-empty means this is a clone.
    borrowed_from: tuple[str, ...]


def plan_games(archives) -> list[PlannedGame]:
    """Which of these archives are GAMES, and which were only chip donors.

    Drop every zip in at once and this decides, without asking:

      a set that could not complete on its own BORROWED chips, so it is the
      release being added — and whatever it borrowed from was a donor.

    Upload a clone and its base release together and you get the clone, once;
    upload a base release alone and you get the base release. Which is the rule
    a person would apply, and it needs no parent/child slots to state.

    Every returned game lists ALL the archives its folder needs, donors
    included: two clones sharing one base release each carry their own copy,
    because a game folder that depends on another folder existing is a game
    that breaks when the other is deleted.
    """
    archives = list(archives)
    if not archives:
        return []

    pool = chips_in_archives(archives)
    planned: list[PlannedGame] = []

    for rs in romsets():
        required = _required(rs)
        if any(crc not in pool for crc in required):
            continue
        used = []
        for crc in required:
            archive_name = pool[crc][0]
            if archive_name not in used:
                used.append(archive_name)
        # The set's "own" archive is the one supplying its program ROM: a
        # romset is named by its program revision, and that is never what a
        # donor contributes.
        own = pool[required[0]][0]
        planned.append(PlannedGame(
            setname=rs["name"], title=rs.get("title"),
            archives=tuple(used),
            borrowed_from=tuple(a for a in used if a != own),
        ))

    children = [g for g in planned if g.borrowed_from]
    return children if children else planned


def compose_folder(dest: Path, archives) -> list[str]:
    """Write a COMPLETE romset into `dest` as loose chip dumps.

    This is the artifact the SD card carries: original MAME filenames, bytes
    untouched, every chip the set needs in one folder. Nothing is renamed to a
    hash -- the device identifies by content and does not read the names, so the
    names may as well stay the ones MAME and every romset tool use.

    Refuses an incomplete set instead of writing a folder that would reach the
    device and fail there. The folder is only created once the set is known to
    be complete, so a rejected compose leaves nothing behind to clean up.
    """
    ident = identify(archives)
    if not ident.complete:
        raise IncompleteRomset(ident.message())

    rs = romset(ident.setname)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    try:
        handles = {}
        for crc in _required(rs):
            archive_name, member = ident.found[crc]
            if archive_name not in handles:
                handles[archive_name] = _open_zip(
                    next(src for name, src in archives if name == archive_name))
            data = handles[archive_name].read(member)
            name = Path(member).name          # never trust a path inside a zip
            (dest / name).write_bytes(data)
            written.append(name)
        for zf in handles.values():
            zf.close()
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise

    return written
