# -*- coding: utf-8 -*-
"""Videos moved from media/ to video/ — the folder the firmware's Video app
actually browses (VIDEO_ROOT in main_video.c; it has never read /media, so every
.avi we shipped there was invisible on the device).

Pinned here: the one-time migration moves the files AND rewrites the stored
relative paths, is idempotent, and never clobbers a file already in video/.
"""
from __future__ import annotations

from app import config, db
from app.services import storage


def _legacy_dir(session_id: str):
    d = storage.session_root(session_id) / config.LEGACY_MEDIA_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_sd_folder_name_is_the_one_the_firmware_browses():
    assert config.MEDIA_DIR_NAME == "video"


def test_migration_moves_legacy_files_and_drops_the_old_folder(session_id):
    legacy = _legacy_dir(session_id)
    (legacy / "clip.avi").write_bytes(b"AVI")

    moved = storage.migrate_legacy_media_dir()

    assert moved == 1
    assert (storage.media_dir(session_id) / "clip.avi").read_bytes() == b"AVI"
    assert not legacy.exists()


def test_migration_is_idempotent(session_id):
    legacy = _legacy_dir(session_id)
    (legacy / "clip.avi").write_bytes(b"AVI")
    storage.migrate_legacy_media_dir()

    assert storage.migrate_legacy_media_dir() == 0          # nothing left to move


def test_migration_keeps_the_file_already_in_video(session_id):
    # A half-finished move (or a re-encode) must not be overwritten by the stale copy.
    legacy = _legacy_dir(session_id)
    (legacy / "clip.avi").write_bytes(b"OLD")
    target = storage.media_dir(session_id)
    target.mkdir(parents=True, exist_ok=True)
    (target / "clip.avi").write_bytes(b"NEW")

    storage.migrate_legacy_media_dir()

    assert (target / "clip.avi").read_bytes() == b"NEW"


def test_migrate_rewrites_stored_video_paths(session_id):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO videos (id, session_id, original_name, avi_name, avi_path, status)"
            " VALUES ('v1', ?, 'clip.mp4', 'clip.avi', 'media/clip.avi', 'ok')",
            (session_id,),
        )

    db.init_db()          # runs _migrate

    with db.connect() as conn:
        row = conn.execute("SELECT avi_path FROM videos WHERE id = 'v1'").fetchone()
    assert row["avi_path"] == "video/clip.avi"
