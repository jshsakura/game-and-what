"""Bundle a session's library into a ZIP that mirrors the SD card layout."""
from __future__ import annotations

import hashlib
import os
import tempfile
import zipfile
from pathlib import Path

from .. import config
from ..systems import EXPERIMENTAL_DIRNAMES
from . import pico8core, storage


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
    if excluded_roms and rel in excluded_roms:
        return True
    if {storage.SCRATCH_DIR_NAME, storage.PREVIEW_DIR_NAME, storage.TRASH_DIR_NAME,
            storage.FIRMWARE_DIR_NAME, storage.EXTRA_DIR_NAME} & set(parts):
        # _firmware / _extra are internal; added at the SD ROOT below (with the
        # firmware filename / the user's chosen passthrough paths).
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
            yield path, str(path.relative_to(root))
    # PICO-8 core (needed to run .p8) when packaging everything or pico8 is selected.
    if systems is None or "pico8" in systems:
        cores = pico8core.ensure_cores_dir()
        if cores and cores.exists():
            for cp in sorted(cores.rglob("*")):
                if cp.is_file():
                    yield cp, f"cores/{cp.relative_to(cores)}"
    # Extra passthrough files (bios/…) → SD root. Cores can't boot without their
    # BIOS, so ship these with ANY selection (not just the full SD).
    extra = storage.extra_dir(session_id)
    if extra.exists():
        for ep in sorted(extra.rglob("*")):
            if ep.is_file():
                yield ep, str(ep.relative_to(extra)).replace("\\", "/")
    # Firmware update → SD ROOT, included with ANY download so the card is complete.
    fw = storage.firmware_path(session_id)
    if fw.exists():
        yield fw, storage.FIRMWARE_FILENAME


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
    for abs_path, _ in entries:
        try:
            total += abs_path.stat().st_size
        except OSError:
            pass
    done = 0
    if on_progress:
        on_progress(0, total)
    for abs_path, arcname in entries:
        if should_cancel and should_cancel():
            raise BuildCancelled()
        zf.write(abs_path, arcname=arcname)
        try:
            done += abs_path.stat().st_size
        except OSError:
            pass
        if on_progress:
            on_progress(done, total)


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
    for abs_path, arcname in _sd_entries(session_id, include_video, systems, homebrew_roms, excluded_roms):
        st = abs_path.stat()
        h.update(f"{arcname}|{st.st_size}|{st.st_mtime_ns}\n".encode())
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

    def on_progress(done: int, total: int) -> None:
        frac = (done / total) if total else 1.0
        if frac - state["last"] < 0.005 and frac < 1.0:
            return
        state["last"] = frac
        jobs.update(job_id, status="running", progress=frac,
                    message=f"{done // 1_000_000}/{max(total // 1_000_000, 1)} MB")

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
    """Keep the SD-zip cache from piling up: most-recently-used first, bounded by
    BOTH a count cap AND a total-size budget, so it can never balloon (these zips
    are ~hundreds of MB each). The newest zip — the one just built/served — is
    always kept so its returned path stays valid."""
    zips = sorted(cache_dir.glob("sd-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    total = 0
    for i, z in enumerate(zips):
        try:
            size = z.stat().st_size
        except OSError:
            size = 0
        keep = i == 0 or (i < _SD_CACHE_KEEP and total + size <= _SD_CACHE_MAX_BYTES)
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


def session_has_content(session_id: str, include_video: bool = False, systems: "set[str] | None" = None) -> bool:
    """Any SD-bound content? Scratch/DATA (and video, by default) don't count."""
    root = storage.session_root(session_id)
    if not root.exists():
        return False
    return any(
        p.is_file() and not _excluded(root, p, include_video, systems)
        for p in root.rglob("*")
    )
