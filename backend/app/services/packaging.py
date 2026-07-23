"""Bundle a session's library into a ZIP that mirrors the SD card layout."""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from .. import config
from ..systems import EXPERIMENTAL_DIRNAMES
from . import cps1, pico8core, storage


def _excluded(root: Path, path: Path, include_video: bool, systems: "set[str] | None" = None,
              homebrew_roms: "set[str] | None" = None,
              excluded_roms: "set[str] | None" = None) -> bool:
    """Files NOT bound for the SD zip: the DATA scratch dir always; video
    (/media) unless explicitly included (video is an extra, not core SD content).
    When `systems` (a set of dirnames) is set, keep only those systems' roms/covers.
    `homebrew_roms` = relative paths of homebrew ROM files the user opted INTO the
    SD (default: none → homebrew ships covers only).
    `excluded_roms` = relative paths (rom files + their covers) the user opted OUT
    of the SD (sd_exclude=1) — kept in the library but dropped from the card."""
    parts = path.relative_to(root).parts
    rel = "/".join(parts)
    if excluded_roms:
        if rel in excluded_roms:
            return True
        # Folder-per-game (CD): only the .cue/.chd is a DB row — its track sidecars
        # are not. Excluding the entry therefore has to take the whole folder, or the
        # tracks sail past every filter on their own (2 GB of PC Engine CD audio was
        # doing exactly that, sd_exclude included). Callers put the game folder in the
        # set; anything under it goes with it.
        if any("/".join(parts[:i]) in excluded_roms for i in range(1, len(parts))):
            return True
    # CPS-1 stores MAME romset ZIPs, and the card must not get them: the firmware
    # caches each chip into external flash and reads it in place, which needs raw
    # chip bytes -- it has no inflate in the emulator path and nowhere to put 4 MB
    # of decompressed graphics against 724 KB of RAM. The chips are emitted in
    # _sd_entries() straight out of these archives instead. (An arcade core in a
    # browser would want the opposite, the zip, which is why the zip stays the
    # master here rather than being converted.)
    if (len(parts) >= 2 and parts[0] == config.ROMS_DIR_NAME and parts[1] == "cps1"):
        return True
    # An underscore-prefixed FOLDER is ours, not the card's: _trash, _data,
    # _previews, _firmware, _extra — and the _orig_backup of pre-encode source
    # videos. The device reads none of them, so none of them ship. (_firmware and
    # _extra are re-added at the SD ROOT below, under their real names.) Only
    # folder names are tested: a rom may legitimately be called "_Test.nes".
    if any(part.startswith("_") for part in parts[:-1]):
        return True
    # /media exists only on the fork firmware — never ship it on an official deploy.
    if (not include_video or not config.EXPERIMENTAL_MODE) and config.MEDIA_DIR_NAME in parts:
        return True
    # /music (fork Music app) likewise stays off the card on an official deploy.
    if not config.EXPERIMENTAL_MODE and config.MUSIC_DIR_NAME in parts:
        return True
    # Official mode: drop fork-only system folders (roms/<dir>, covers/<dir>) even
    # if the library still holds files from an earlier experimental deploy.
    if (not config.EXPERIMENTAL_MODE and len(parts) >= 2
            and parts[0] in (config.ROMS_DIR_NAME, config.COVERS_DIR_NAME)
            and parts[1] in EXPERIMENTAL_DIRNAMES):
        return True
    # Homebrew: .bin apps are bundled IN the firmware (flashed, not loaded from SD)
    # → SD needs only their COVER, unless the user explicitly opts that .bin in.
    # Asset files (.dat — SMW's smw_assets.dat, Zelda3's zelda3_assets.dat) are
    # REQUIRED to run those ports, so they ALWAYS ship.
    if len(parts) >= 2 and parts[0] == config.ROMS_DIR_NAME and parts[1] == "homebrew":
        if path.suffix.lower() == ".bin" and (not homebrew_roms or rel not in homebrew_roms):
            return True
    if systems is not None:
        # roms/<dirname>/... or covers/<dirname>/... for the SELECTED systems only.
        if len(parts) < 2 or parts[1] not in systems:
            return True
    return False


# Bump when the zip-building logic changes so old cached zips are invalidated.
# "3": DEFLATE level 1 (was 6).
_SD_CACHE_VERSION = "3"
_SD_CACHE_KEEP = 4                    # max cached zips to retain (LRU)
# Budget must comfortably hold a couple of FULL-library zips (~2.4 GB each) plus
# per-system ones, or switching variants (all / +video / single system) evicts
# the full zip and forces a 1–2 min rebuild every time. A retro SD library is a
# few GB; 12 GB of cache is a cheap trade for never rebuilding the common ones.
_SD_CACHE_MAX_BYTES = 12_000_000_000
# …but only while the disk can afford it. This cache is an optimisation, and an
# optimisation that fills the disk has stopped being one: a full disk breaks uploads,
# the database and the app itself, and rebuilding a zip only costs a minute. So the
# budget yields to free space — keep this much headroom clear no matter what.
_SD_CACHE_DISK_RESERVE = 20_000_000_000


def _cache_budget(cache_dir: Path) -> int:
    """What the cache may occupy right now: the fixed cap, or whatever the disk can spare
    above the reserve — whichever is smaller. Zero when the disk is already tight, which
    empties the cache rather than defending it."""
    try:
        usage = shutil.disk_usage(cache_dir)
    except OSError:
        return _SD_CACHE_MAX_BYTES
    # The cache's own bytes are already counted as "used", so they are part of what it may
    # spend: free + what it is holding, minus the headroom we insist on keeping.
    held = sum(z.stat().st_size for z in cache_dir.glob("sd-*.zip") if z.exists())
    spare = usage.free + held - _SD_CACHE_DISK_RESERVE
    return max(0, min(_SD_CACHE_MAX_BYTES, spare))


def _sd_entries(session_id: str, include_video: bool, systems: "set[str] | None",
                homebrew_roms: "set[str] | None", excluded_roms: "set[str] | None" = None):
    """Yield (abs_path, arcname) for every file that belongs in the SD zip. Single
    source of truth so the zip writer and the cache fingerprint never drift.

    Cover .img files already carry their baked-in language flag (applied at
    render_cover time), so they are copied as-is.
    """
    root = storage.session_root(session_id)
    for path in sorted(root.rglob("*")):
        if path.is_file() and not _excluded(root, path, include_video, systems, homebrew_roms, excluded_roms):
            yield path, str(path.relative_to(root)), None
    yield from _cps1_entries(root, systems, excluded_roms)
    # PICO-8 core (needed to run .p8) when packaging everything or pico8 is selected.
    if systems is None or "pico8" in systems:
        cores = pico8core.ensure_cores_dir()
        if cores and cores.exists():
            for cp in sorted(cores.rglob("*")):
                if cp.is_file():
                    yield cp, f"cores/{cp.relative_to(cores)}", None
    # Extra passthrough files (bios/…) → SD root. Cores can't boot without their
    # BIOS, so ship these with ANY selection (not just the full SD).
    extra = storage.extra_dir(session_id)
    if extra.exists():
        for ep in sorted(extra.rglob("*")):
            if ep.is_file():
                yield ep, str(ep.relative_to(extra)).replace("\\", "/"), None
    # Firmware update → SD ROOT, included with ANY download so the card is complete.
    fw = storage.firmware_path(session_id)
    if fw.exists():
        yield fw, storage.FIRMWARE_FILENAME, None


def _entry_size(src: Path, member: "str | None") -> int:
    """Uncompressed bytes this entry contributes to the card."""
    if member is None:
        return src.stat().st_size
    with zipfile.ZipFile(src) as zf:
        return zf.getinfo(member).file_size


def _cps1_entries(root: Path, systems: "set[str] | None", excluded_roms: "set[str] | None"):
    """Expand each CPS-1 game folder of romset ZIPs into its chips.

    A CPS-1 game on the server is /roms/cps1/<game name>/*.zip — the clone's
    archive plus, for a MAME split set, its parent's. The card gets
    /roms/cps1/<game name>/<chip> instead, because that is the only form the
    firmware can read (see _excluded).

    The whole chip pool is extracted as-is, named by CRC — NOT one guessed
    romset's slice. Emitting only the set the packager picks made the card and
    the device guess a romset independently and disagree: the same folder was
    `wofj` here and `wofr1` on the device, which then reported two chips absent
    that were present in the archives all along. Shipping every chip lets the
    firmware bind by CRC and complete whatever set it runs; extra chips are free.

    An INCOMPLETE folder (one that completes NO set) still contributes nothing:
    half a romset is a game that appears in the launcher and dies when opened,
    worse than one visibly absent and reported as incomplete at upload time.
    """
    if systems is not None and "cps1" not in systems:
        return
    base = root / config.ROMS_DIR_NAME / "cps1"
    if not base.is_dir():
        return
    for game_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        rel = f"{config.ROMS_DIR_NAME}/cps1/{game_dir.name}"
        if excluded_roms and rel in excluded_roms:
            continue
        for chip in cps1.all_chip_entries(game_dir):
            yield chip.archive, f"{rel}/{chip.name}", chip.member


class BuildCancelled(Exception):
    """Raised inside the zip writer when a caller asks the build to stop."""


def _write_sd_zip(zf: "zipfile.ZipFile", session_id: str, include_video: bool,
                  systems: "set[str] | None", homebrew_roms: "set[str] | None",
                  excluded_roms: "set[str] | None" = None,
                  on_progress=None, should_cancel=None) -> None:
    """Write the SD-card layout into an OPEN ZipFile.

    on_progress(done_bytes, total_bytes): called after each file (best-effort
    progress, measured in uncompressed input bytes). should_cancel(): polled
    before each file; if it returns True, raises BuildCancelled."""
    entries = list(_sd_entries(session_id, include_video, systems, homebrew_roms, excluded_roms))
    total = 0
    for abs_path, _, member in entries:
        try:
            total += _entry_size(abs_path, member)
        except OSError:
            pass
    done = 0
    if on_progress:
        on_progress(0, total, "")
    for abs_path, arcname, member in entries:
        if should_cancel and should_cancel():
            raise BuildCancelled()
        if member is None:
            zf.write(abs_path, arcname=arcname)
        else:
            # A CPS-1 chip, read out of its romset archive on the way past. No
            # extracted copy is kept anywhere: composing at build time is what
            # makes re-uploading safe, since there is no stale folder to
            # invalidate when the user later supplies a missing parent set.
            with zipfile.ZipFile(abs_path) as src:
                zf.writestr(arcname, src.read(member))
        try:
            done += _entry_size(abs_path, member)
        except OSError:
            pass
        if on_progress:
            # The name of what just went in. Compressing a 4.6 GB library takes minutes,
            # and a bar with no words is indistinguishable from a hang — the one thing the
            # server knows and the user does not is WHICH game it is packing right now.
            on_progress(done, total, abs_path.name)


def sd_fingerprint(session_id: str, include_video: bool = False, systems: "set[str] | None" = None,
                   homebrew_roms: "set[str] | None" = None, excluded_roms: "set[str] | None" = None) -> str:
    """A cheap content key (no file reads — stat only) over exactly the files that
    would go in the zip + params + cache version. Changes iff the resulting zip
    would change → used as the cache key and HTTP ETag."""
    h = hashlib.sha1()
    h.update(_SD_CACHE_VERSION.encode())
    h.update(f"|exp={config.EXPERIMENTAL_MODE}".encode())  # mode changes what _excluded drops
    h.update(f"|video={include_video}|sys={sorted(systems) if systems else None}"
             f"|hb={sorted(homebrew_roms) if homebrew_roms else None}"
             f"|ex={sorted(excluded_roms) if excluded_roms else None}|".encode())
    for abs_path, arcname, member in _sd_entries(session_id, include_video, systems,
                                                 homebrew_roms, excluded_roms):
        st = abs_path.stat()
        # For a CPS-1 chip the source is its ARCHIVE, so the key moves exactly
        # when the archive does -- which is when the composed chips would change.
        h.update(f"{arcname}|{member or ''}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def cached_zip_path(session_id: str, include_video: bool = False, systems: "set[str] | None" = None,
                    homebrew_roms: "set[str] | None" = None,
                    excluded_roms: "set[str] | None" = None) -> tuple[str, str, bool]:
    """(zip_path, etag, exists) for the current library/params, without building.
    Lets the caller answer 'is it ready?' before starting a build job."""
    key = sd_fingerprint(session_id, include_video, systems, homebrew_roms, excluded_roms)
    cache_dir = config.DATA_DIR / "_cache"
    cached = cache_dir / f"sd-{key}.zip"
    exists = cached.exists()
    if exists:
        os.utime(cached, None)   # mark recently used (for LRU prune)
    return str(cached), key, exists


def build_sd_zip_cached(session_id: str, include_video: bool = False, systems: "set[str] | None" = None,
                        homebrew_roms: "set[str] | None" = None,
                        excluded_roms: "set[str] | None" = None,
                        on_progress=None, should_cancel=None) -> tuple[str, str]:
    """Return (zip_path, etag). The zip is CACHED on disk keyed by its content
    fingerprint — rebuilt only when the library/params change (was: rebuilt on
    every download, ~hundreds of MB). Built to disk, never in RAM (no OOM).
    Returns the cached path (do NOT delete it) + the fingerprint as an ETag.

    on_progress / should_cancel are forwarded to the writer (see _write_sd_zip);
    a cancelled build raises BuildCancelled and leaves no cache file behind.
    ROMs are mostly padding/repetition and DEFLATE level 1 gets ~the same ratio
    as level 6 at ~1.5x the speed, so the build is CPU-bound for the shortest
    time."""
    key = sd_fingerprint(session_id, include_video, systems, homebrew_roms, excluded_roms)
    cache_dir = config.DATA_DIR / "_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"sd-{key}.zip"
    if cached.exists():
        os.utime(cached, None)   # mark recently used (for LRU prune)
        if on_progress:
            on_progress(1, 1)
        return str(cached), key

    # Build to a temp file in the same dir, then atomically rename into place so a
    # concurrent request never sees a half-written cache file.
    fd, tmp = tempfile.mkstemp(prefix="sd-", suffix=".zip.tmp", dir=str(cache_dir))
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
            _write_sd_zip(zf, session_id, include_video, systems, homebrew_roms, excluded_roms,
                          on_progress=on_progress, should_cancel=should_cancel)
        os.replace(tmp, cached)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _prune_sd_cache(cache_dir)
    return str(cached), key


def run_sd_zip_build_job(job_id: str, session_id: str, include_video: bool = False,
                         systems: "set[str] | None" = None, homebrew_roms: "set[str] | None" = None,
                         excluded_roms: "set[str] | None" = None) -> None:
    """Build the SD zip while reporting progress into the jobs registry and
    honouring cancellation. Runs in a worker thread (run_in_threadpool). Never
    raises — terminal state is recorded on the job (done | cancelled | failed)."""
    from . import jobs  # local import: jobs pulls in nothing from packaging

    # Throttle progress writes: only every ~0.5% so a huge library doesn't spam
    # the registry once per file.
    state = {"last": -1.0}

    def on_progress(done: int, total: int, name: str = "") -> None:
        frac = (done / total) if total else 1.0
        if frac - state["last"] < 0.005 and frac < 1.0:
            return
        state["last"] = frac
        # "689/3281 MB · 젤다의 전설 - 이상한 모자.gba" — the numbers say how long is left,
        # the name says the thing is alive. The client splits on the separator.
        head = f"{done // 1_000_000}/{max(total // 1_000_000, 1)} MB"
        jobs.update(job_id, status="running", progress=frac,
                    message=f"{head} · {name}" if name else head)

    def should_cancel() -> bool:
        return jobs.is_cancelled(job_id)

    jobs.update(job_id, status="running", progress=0.0, message="")
    try:
        _, etag = build_sd_zip_cached(session_id, include_video, systems, homebrew_roms,
                                      excluded_roms, on_progress=on_progress,
                                      should_cancel=should_cancel)
        jobs.update(job_id, status="done", progress=1.0, message="", result={"etag": etag})
    except BuildCancelled:
        jobs.update(job_id, status="cancelled", message="")
    except BaseException as exc:  # noqa: BLE001 — surface any build failure on the job
        jobs.update(job_id, status="failed", message=str(exc))


def prune_cache() -> int:
    """Tidy the SD-zip cache (e.g. at startup) so it never lingers oversized after
    the budget shrinks. Returns the number of zips removed."""
    cache_dir = config.DATA_DIR / "_cache"
    if not cache_dir.exists():
        return 0
    before = len(list(cache_dir.glob("sd-*.zip")))
    _prune_sd_cache(cache_dir)
    return before - len(list(cache_dir.glob("sd-*.zip")))


def _prune_sd_cache(cache_dir: Path) -> None:
    """Keep the SD-zip cache from piling up: most-recently-used first, bounded by a count
    cap AND a size budget — and the budget yields to free disk (`_cache_budget`).

    A full-library zip is ~2.4 GB, so four of them is a cache that can eat a disk. It had a
    flat 12 GB budget, which was a fine trade when the disk was empty and a bad one when it
    was not: at 99% full, the pruner was dutifully *defending* 2.7 GB of zips that rebuild
    in a minute.

    The newest zip is always kept — it is the one just built or being served, and its path
    has already been handed out.
    """
    budget = _cache_budget(cache_dir)
    zips = sorted(cache_dir.glob("sd-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    total = 0
    for i, z in enumerate(zips):
        try:
            size = z.stat().st_size
        except OSError:
            size = 0
        keep = i == 0 or (i < _SD_CACHE_KEEP and total + size <= budget)
        if keep:
            total += size
            continue
        try:
            z.unlink()
        except OSError:
            pass


def sd_content_size(session_id: str, include_video: bool = False, systems: "set[str] | None" = None,
                    homebrew_roms: "set[str] | None" = None, excluded_roms: "set[str] | None" = None) -> int:
    """Total bytes of the SD-bound files (roms/covers, +video/+system filters) plus
    the PICO-8 core — an estimate of what lands on the card."""
    root = storage.session_root(session_id)
    total = 0
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file() and not _excluded(root, p, include_video, systems, homebrew_roms, excluded_roms):
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    # CPS-1 romset zips were just excluded above; what the card actually gets is
    # the chips inside them, which are roughly twice the size. Counting the zips
    # would under-report the card by half for every arcade game.
    for _src, _arc, member in _cps1_entries(root, systems, excluded_roms):
        try:
            total += _entry_size(_src, member)
        except (OSError, KeyError):
            pass
    if systems is None or "pico8" in systems:
        cores = pico8core.ensure_cores_dir()
        if cores and cores.exists():
            for cp in cores.rglob("*"):
                if cp.is_file():
                    try:
                        total += cp.stat().st_size
                    except OSError:
                        pass
    # Extra (bios) ships with any selection → always counted.
    extra = storage.extra_dir(session_id)
    if extra.exists():
        for ep in extra.rglob("*"):
            if ep.is_file():
                try:
                    total += ep.stat().st_size
                except OSError:
                    pass
    # Firmware ships with any download → always counted.
    fw = storage.firmware_path(session_id)
    if fw.exists():
        total += fw.stat().st_size
    return total


def session_has_content(session_id: str, include_video: bool = False, systems: "set[str] | None" = None,
                        homebrew_roms: "set[str] | None" = None,
                        excluded_roms: "set[str] | None" = None) -> bool:
    """Any SD-bound content? Scratch/DATA (and video, by default) don't count.

    Takes the same opt-in/opt-out sets as the zip builder: this is the gate in front
    of it, so asking a different question ("is anything there?" vs "is anything there
    once the filters run?") means a build the user CAN download gets 404'd — e.g. a
    session whose only content is a homebrew .bin that was opted into the SD.
    """
    root = storage.session_root(session_id)
    if not root.exists():
        return False
    return any(
        p.is_file() and not _excluded(root, p, include_video, systems, homebrew_roms, excluded_roms)
        for p in root.rglob("*")
    )
