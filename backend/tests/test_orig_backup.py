# -*- coding: utf-8 -*-
"""Pre-encode source backups (video/_orig_backup) — ours, not the card's.

A re-encode keeps the original file so a bad convert can be redone from the source.
The device never reads it, so it must not ride along in the SD zip (it is the
biggest thing we keep — full-size source video), and it must not live forever: it
expires on the same clock as the trash.

The zip rule is general, not a special case for this one folder: an underscore
FOLDER is internal. Only folder names count — a rom may legitimately be named
"_Test.nes".
"""
from __future__ import annotations

import time

from app import config
from app.services import storage
from app.services.packaging import _excluded


def _write(path, data=b"x", *, age_days: float = 0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if age_days:
        old = time.time() - age_days * 86400
        import os
        os.utime(path, (old, old))
    return path


# ── SD zip ────────────────────────────────────────────────────────────────────

def test_source_backup_never_ships_even_with_the_video_opt_in(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    backup = _write(tmp_path / config.MEDIA_DIR_NAME / storage.ORIG_BACKUP_DIR_NAME / "src.avi")
    shipped = _write(tmp_path / config.MEDIA_DIR_NAME / "clip.avi")

    assert _excluded(tmp_path, backup, include_video=True) is True
    assert _excluded(tmp_path, shipped, include_video=True) is False


def test_underscore_folders_are_internal_in_general(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    music_backup = _write(
        tmp_path / config.MUSIC_DIR_NAME / storage.ORIG_BACKUP_DIR_NAME / "song.wav")

    assert _excluded(tmp_path, music_backup, include_video=True) is True


def test_a_rom_whose_name_starts_with_underscore_still_ships(tmp_path, monkeypatch):
    """The rule tests FOLDER names only — the file's own name is the user's."""
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    rom = _write(tmp_path / config.ROMS_DIR_NAME / "nes" / "_Test.nes")

    assert _excluded(tmp_path, rom, include_video=False) is False


# ── retention ─────────────────────────────────────────────────────────────────

def test_purge_removes_backups_past_the_window_and_keeps_recent_ones(session_id):
    root = storage.session_root(session_id)
    backups = root / config.MEDIA_DIR_NAME / storage.ORIG_BACKUP_DIR_NAME
    stale = _write(backups / "old.avi", age_days=40)
    fresh = _write(backups / "new.avi", age_days=1)

    removed = storage.purge_orig_backups(session_id, older_than_days=30)

    assert removed == 1
    assert not stale.exists()
    assert fresh.exists()


def test_purge_is_a_no_op_when_there_is_no_backup_folder(session_id):
    assert storage.purge_orig_backups(session_id, older_than_days=30) == 0


# ── trash clock ───────────────────────────────────────────────────────────────

def test_deleting_an_old_file_still_gets_the_full_recovery_window(session_id):
    """The recovery window is 30 days from the DELETE, not from whenever the file
    happened to be written. A rename preserves mtime, so trashing a ROM uploaded
    months ago used to make it purgeable on the very next startup — the activity
    feed offered a restore that the purge had already taken away."""
    rom = _write(storage.roms_dir(session_id, "nes") / "Old.nes", age_days=200)

    storage.move_to_trash(session_id, f"{config.ROMS_DIR_NAME}/nes/Old.nes")
    purged = storage.purge_trash(session_id, older_than_days=30)

    assert purged == 0
    assert storage.restore_from_trash(session_id, f"{config.ROMS_DIR_NAME}/nes/Old.nes") is True
    assert rom.exists()
