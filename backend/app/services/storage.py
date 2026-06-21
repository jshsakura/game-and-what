"""Filesystem layout for the persistent library. Mirrors the SD card."""
from __future__ import annotations

import re
import unicodedata
import uuid
from pathlib import Path

from .. import config

# Chars illegal on FAT/exFAT (the SD card's filesystems). Korean is fine.
# Colon is handled separately (→ ' - ') so subtitle titles stay readable.
_ILLEGAL = re.compile(r'[<>"/\\|?*\x00-\x1f]')
# A colon is a subtitle separator ('스타워즈: 제국의 역습'); FAT forbids it, so
# turn it into ' - ' instead of an ugly underscore. Eats surrounding spaces.
_COLON = re.compile(r"\s*:\s*")


def new_id() -> str:
    return uuid.uuid4().hex


def nfc(text: str | None) -> str | None:
    """Normalize to NFC so decomposed Korean (NFD — e.g. from macOS uploads) is
    stored composed and never renders as broken/spaced jamo. Pass-through on None.
    Apply to EVERY persisted title/filename string at its entry boundary."""
    return unicodedata.normalize("NFC", text) if text else text


def safe_name(name: str) -> str:
    """Make a filename safe for FAT/exFAT while keeping Korean/letters intact.
    A subtitle colon becomes ' - ' (not '_'); other illegal chars fall back to
    '_'. Collapses runs of whitespace. Always NFC-normalized (see nfc())."""
    text = _COLON.sub(" - ", nfc(name) or "")
    cleaned = _ILLEGAL.sub("_", text).strip().strip(".")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned or "untitled"


def session_root(session_id: str) -> Path:
    return config.LIBRARY_DIR / safe_name(session_id)


def roms_dir(session_id: str, dirname: str) -> Path:
    return session_root(session_id) / config.ROMS_DIR_NAME / dirname


def covers_dir(session_id: str, dirname: str) -> Path:
    return session_root(session_id) / config.COVERS_DIR_NAME / dirname


def media_dir(session_id: str) -> Path:
    return session_root(session_id) / config.MEDIA_DIR_NAME


# Transient encode/extract names, written before an ffmpeg run and removed in the
# caller's `finally`: `.src_*` (input) in the media dir (video) AND the music dir
# (audio extraction), plus `.out_*` (output) in the music dir. See the video /
# upload / music routers.
TEMP_GLOBS = (".src_*", ".out_*")
_TEMP_DIRS = (config.MEDIA_DIR_NAME, config.MUSIC_DIR_NAME)


def sweep_temp_uploads() -> int:
    """Delete orphaned encode/extract temp files (`.src_*` / `.out_*`) left when an
    ffmpeg run was killed mid-way (hard crash / OOM / container stop → the normal
    `finally` cleanup didn't run). Safe at startup: these exist only DURING a run,
    so any present after a restart is guaranteed an orphan. Returns count removed."""
    removed = 0
    if not config.LIBRARY_DIR.exists():
        return 0
    for sub in _TEMP_DIRS:
        for d in config.LIBRARY_DIR.glob(f"*/{sub}"):
            for pat in TEMP_GLOBS:
                for f in d.glob(pat):
                    try:
                        f.unlink()
                        removed += 1
                    except OSError:
                        pass
    return removed


def music_dir(session_id: str) -> Path:
    return session_root(session_id) / config.MUSIC_DIR_NAME


# Scratch / reference uploads ("DATA"). Lives under "_data" — NOT a real SD
# folder, and explicitly EXCLUDED from the SD package zip.
SCRATCH_DIR_NAME = "_data"

# High-res web preview covers — shown in the UI (the device .img is tiny). NOT a
# real SD folder; EXCLUDED from the SD package zip.
PREVIEW_DIR_NAME = "_previews"


def scratch_dir(session_id: str) -> Path:
    return session_root(session_id) / SCRATCH_DIR_NAME


def previews_dir(session_id: str, dirname: str) -> Path:
    return session_root(session_id) / PREVIEW_DIR_NAME / dirname


# Web-only media cache (browser thumbnail/preview/cover) — under _previews, so it's
# EXCLUDED from the SD zip. Keyed by the row id.
def media_thumb_path(session_id: str, video_id: str) -> Path:
    return previews_dir(session_id, "media") / f"{video_id}.jpg"


def media_preview_path(session_id: str, video_id: str) -> Path:
    return previews_dir(session_id, "media") / f"{video_id}.mp4"


def music_cover_path(session_id: str, music_id: str) -> Path:
    return previews_dir(session_id, "music") / f"{music_id}.jpg"


# Deleted files go here (soft delete) — recoverable, EXCLUDED from the SD zip.
TRASH_DIR_NAME = "_trash"
# Single firmware file kept here; added to the SD zip ROOT as /retro-go_update.bin.
FIRMWARE_DIR_NAME = "_firmware"
FIRMWARE_FILENAME = "retro-go_update.bin"   # name the device flashes from (gw_sleep.c)
# Arbitrary passthrough files (bios, configs…). Stored mirroring their SD target
# path; the SD zip adds them at root verbatim (e.g. _extra/bios/nes/disksys.rom
# → /bios/nes/disksys.rom).
EXTRA_DIR_NAME = "_extra"


def extra_dir(session_id: str) -> Path:
    return session_root(session_id) / EXTRA_DIR_NAME


def trash_dir(session_id: str) -> Path:
    return session_root(session_id) / TRASH_DIR_NAME


def firmware_path(session_id: str) -> Path:
    return session_root(session_id) / FIRMWARE_DIR_NAME / FIRMWARE_FILENAME


def move_to_trash(session_id: str, rel_path: str) -> None:
    """Move a session-relative file into _trash (flattened), never raising."""
    try:
        src = session_root(session_id) / rel_path
        if not src.exists():
            return
        dest = trash_dir(session_id) / rel_path.replace("/", "__")
        dest.parent.mkdir(parents=True, exist_ok=True)
        src.replace(dest)
    except OSError:
        pass


def restore_from_trash(session_id: str, rel_path: str | None) -> bool:
    """Inverse of move_to_trash: move the _trash copy back to its original
    session-relative path. Returns True if restored, False if the trash copy is
    gone (already purged / never existed)."""
    if not rel_path:
        return False
    try:
        src = trash_dir(session_id) / rel_path.replace("/", "__")
        if not src.exists():
            return False
        dest = session_root(session_id) / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        src.replace(dest)
        return True
    except OSError:
        return False


def purge_trash(session_id: str, older_than_days: int) -> int:
    """Delete _trash files older than N days (by mtime). Returns count removed.
    Caps how long deleted ROMs stay recoverable. Never raises."""
    import time

    removed = 0
    try:
        d = trash_dir(session_id)
        if not d.exists():
            return 0
        cutoff = time.time() - older_than_days * 86400
        for p in d.iterdir():
            try:
                if p.is_file() and p.stat().st_mtime < cutoff:
                    p.unlink()
                    removed += 1
            except OSError:
                pass
    except OSError:
        pass
    return removed


def write_bytes(path: Path, data: bytes) -> Path:
    """Persist bytes, creating parent dirs. Returns the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def relative_to_session(session_id: str, path: Path) -> str:
    """Path as it will sit on the SD card, e.g. 'roms/nes/Game.nes'."""
    return str(path.relative_to(session_root(session_id)))
