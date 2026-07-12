# -*- coding: utf-8 -*-
"""services/renames.py — renaming a ROM must keep the on-disk file, its cover,
its web preview AND the DB row consistent as one set. Folder-per-game (CD)
entries rename the containing folder + the primary file, but leave sidecar
track files (referenced by name from the .cue) untouched and co-located.
"""
from __future__ import annotations

import pytest

from app import config, db
from app.services import renames, storage
from app.services.renames import _free_name


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gnw.db")
    monkeypatch.setattr(config, "TMP_DIR", tmp_path / "tmp")
    db.init_db()
    with db.connect() as c:
        yield c


def _insert_rom(conn, *, rom_id, system_key, stored_name, rom_path, cover_path=None):
    conn.execute(
        "INSERT INTO roms (id, session_id, system_key, original_name, stored_name, "
        "rom_path, cover_path) VALUES (?,?,?,?,?,?,?)",
        (rom_id, config.SHARED_SESSION_ID, system_key, stored_name, stored_name,
         rom_path, cover_path),
    )
    return {"id": rom_id, "system_key": system_key, "stored_name": stored_name,
            "rom_path": rom_path, "cover_path": cover_path}


def _write(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _fetch(conn, rom_id):
    return dict(conn.execute("SELECT * FROM roms WHERE id = ?", (rom_id,)).fetchone())


# ---------------------------------------------------------------------------
# Simple (single-file) systems
# ---------------------------------------------------------------------------

def test_simple_rename_moves_file_and_updates_db(conn):
    sid = config.SHARED_SESSION_ID
    _write(storage.roms_dir(sid, "nes") / "Old.nes")
    row = _insert_rom(conn, rom_id="r1", system_key="nes",
                       stored_name="Old.nes", rom_path="roms/nes/Old.nes")

    result = renames.rename_rom(conn, sid, row, "New.nes")

    assert result == {"stored_name": "New.nes", "rom_path": "roms/nes/New.nes",
                       "cover_path": None}
    assert not (storage.roms_dir(sid, "nes") / "Old.nes").exists()
    assert (storage.roms_dir(sid, "nes") / "New.nes").exists()
    assert _fetch(conn, "r1")["stored_name"] == "New.nes"
    assert _fetch(conn, "r1")["rom_path"] == "roms/nes/New.nes"


def test_rename_moves_cover_alongside(conn):
    sid = config.SHARED_SESSION_ID
    _write(storage.roms_dir(sid, "nes") / "Old.nes")
    _write(storage.covers_dir(sid, "nes") / "Old.img", b"cover-bytes")
    row = _insert_rom(conn, rom_id="r1", system_key="nes", stored_name="Old.nes",
                       rom_path="roms/nes/Old.nes", cover_path="covers/nes/Old.img")

    result = renames.rename_rom(conn, sid, row, "New.nes")

    assert result["cover_path"] == "covers/nes/New.img"
    assert not (storage.covers_dir(sid, "nes") / "Old.img").exists()
    new_cover = storage.covers_dir(sid, "nes") / "New.img"
    assert new_cover.exists() and new_cover.read_bytes() == b"cover-bytes"
    assert _fetch(conn, "r1")["cover_path"] == "covers/nes/New.img"


def test_rename_moves_web_preview_named_by_rom_stem(conn):
    sid = config.SHARED_SESSION_ID
    _write(storage.roms_dir(sid, "nes") / "Old.nes")
    _write(storage.previews_dir(sid, "nes") / "Old.webp", b"preview-bytes")
    row = _insert_rom(conn, rom_id="r1", system_key="nes", stored_name="Old.nes",
                       rom_path="roms/nes/Old.nes")

    renames.rename_rom(conn, sid, row, "New.nes")

    assert not (storage.previews_dir(sid, "nes") / "Old.webp").exists()
    moved = storage.previews_dir(sid, "nes") / "New.webp"
    assert moved.exists() and moved.read_bytes() == b"preview-bytes"


def test_rename_raises_on_filename_collision_without_suffix(conn):
    sid = config.SHARED_SESSION_ID
    old = _write(storage.roms_dir(sid, "nes") / "Old.nes")
    _write(storage.roms_dir(sid, "nes") / "New.nes")  # target already taken
    row = _insert_rom(conn, rom_id="r1", system_key="nes", stored_name="Old.nes",
                       rom_path="roms/nes/Old.nes")

    with pytest.raises(ValueError, match="같은 이름의 파일"):
        renames.rename_rom(conn, sid, row, "New.nes")

    assert old.exists()  # untouched — the move never happened


def test_rename_suffix_on_clash_appends_number(conn):
    sid = config.SHARED_SESSION_ID
    _write(storage.roms_dir(sid, "nes") / "Old.nes")
    _write(storage.roms_dir(sid, "nes") / "New.nes")
    row = _insert_rom(conn, rom_id="r1", system_key="nes", stored_name="Old.nes",
                       rom_path="roms/nes/Old.nes")

    result = renames.rename_rom(conn, sid, row, "New.nes", suffix_on_clash=True)

    assert result["stored_name"] == "New (2).nes"
    assert (storage.roms_dir(sid, "nes") / "New (2).nes").exists()


def test_rename_sanitizes_new_name_for_fat_filesystem(conn):
    """A colon (subtitle separator) must become ' - ', matching storage.safe_name,
    and Korean characters must pass through untouched."""
    sid = config.SHARED_SESSION_ID
    _write(storage.roms_dir(sid, "nes") / "Old.nes")
    row = _insert_rom(conn, rom_id="r1", system_key="nes", stored_name="Old.nes",
                       rom_path="roms/nes/Old.nes")
    new_name = "젤다: 신들의 트라이포스.nes"

    result = renames.rename_rom(conn, sid, row, new_name)

    assert result["stored_name"] == storage.safe_name(new_name)
    assert "트라이포스" in result["stored_name"]
    assert (storage.roms_dir(sid, "nes") / result["stored_name"]).exists()


def test_rename_missing_source_file_updates_db_without_raising(conn):
    """Sharp edge: if the underlying rom file is already gone (e.g. manually
    deleted, or a prior operation left the DB out of sync), rename_rom silently
    updates the DB to point at a path where no file was ever moved."""
    sid = config.SHARED_SESSION_ID
    row = _insert_rom(conn, rom_id="r1", system_key="nes", stored_name="Old.nes",
                       rom_path="roms/nes/Old.nes")  # no file written to disk

    result = renames.rename_rom(conn, sid, row, "New.nes")

    assert result["stored_name"] == "New.nes"
    assert not (storage.roms_dir(sid, "nes") / "New.nes").exists()  # nothing to move
    assert _fetch(conn, "r1")["rom_path"] == "roms/nes/New.nes"  # DB updated anyway


def test_rename_onto_existing_cover_silently_overwrites_it(conn):
    """Sharp edge: unlike the rom-file path, the cover move has no collision
    guard — Path.rename onto an existing cover overwrites it outright (POSIX
    rename semantics)."""
    sid = config.SHARED_SESSION_ID
    _write(storage.roms_dir(sid, "nes") / "Old.nes")
    _write(storage.covers_dir(sid, "nes") / "Old.img", b"old-cover")
    _write(storage.covers_dir(sid, "nes") / "New.img", b"stale-cover-belonging-to-someone-else")
    row = _insert_rom(conn, rom_id="r1", system_key="nes", stored_name="Old.nes",
                       rom_path="roms/nes/Old.nes", cover_path="covers/nes/Old.img")

    result = renames.rename_rom(conn, sid, row, "New.nes")

    assert result["cover_path"] == "covers/nes/New.img"
    assert (storage.covers_dir(sid, "nes") / "New.img").read_bytes() == b"old-cover"


# ---------------------------------------------------------------------------
# _free_name
# ---------------------------------------------------------------------------

def test_free_name_returns_target_unchanged_when_available(tmp_path):
    target = tmp_path / "Game.nes"
    assert _free_name(target) == target


def test_free_name_increments_past_multiple_clashes(tmp_path):
    (tmp_path / "Game.nes").write_bytes(b"x")
    (tmp_path / "Game (2).nes").write_bytes(b"x")

    free = _free_name(tmp_path / "Game.nes")

    assert free == tmp_path / "Game (3).nes"


# ---------------------------------------------------------------------------
# Folder-per-game (CD) systems: rom_path has >= 4 parts (roms/<dir>/<game>/<file>)
# ---------------------------------------------------------------------------

def _cd_folder(sid, game="OldGame"):
    return storage.roms_dir(sid, "pcecd") / game


def test_folder_rename_moves_folder_and_primary_keeps_sidecar(conn):
    sid = config.SHARED_SESSION_ID
    folder = _cd_folder(sid)
    _write(folder / "OldGame.cue")
    _write(folder / "track01.bin", b"track-bytes")
    row = _insert_rom(conn, rom_id="r1", system_key="pcecd", stored_name="OldGame.cue",
                       rom_path="roms/pcecd/OldGame/OldGame.cue")

    result = renames.rename_rom(conn, sid, row, "NewGame")

    new_folder = storage.roms_dir(sid, "pcecd") / "NewGame"
    assert not folder.exists()
    assert new_folder.exists()
    assert (new_folder / "NewGame.cue").exists()
    assert (new_folder / "track01.bin").read_bytes() == b"track-bytes"  # untouched name
    assert result["rom_path"] == "roms/pcecd/NewGame/NewGame.cue"
    assert result["stored_name"] == "NewGame.cue"
    assert _fetch(conn, "r1")["rom_path"] == "roms/pcecd/NewGame/NewGame.cue"


def test_folder_rename_new_name_with_matching_extension(conn):
    sid = config.SHARED_SESSION_ID
    folder = _cd_folder(sid)
    _write(folder / "OldGame.cue")
    row = _insert_rom(conn, rom_id="r1", system_key="pcecd", stored_name="OldGame.cue",
                       rom_path="roms/pcecd/OldGame/OldGame.cue")

    result = renames.rename_rom(conn, sid, row, "NewGame.cue")

    assert result["rom_path"] == "roms/pcecd/NewGame/NewGame.cue"


def test_folder_rename_to_same_name_is_a_noop(conn):
    sid = config.SHARED_SESSION_ID
    folder = _cd_folder(sid)
    _write(folder / "OldGame.cue")
    _write(folder / "track01.bin", b"t")
    row = _insert_rom(conn, rom_id="r1", system_key="pcecd", stored_name="OldGame.cue",
                       rom_path="roms/pcecd/OldGame/OldGame.cue")

    result = renames.rename_rom(conn, sid, row, "OldGame")

    assert folder.exists()
    assert (folder / "OldGame.cue").exists()
    assert (folder / "track01.bin").exists()
    assert result["rom_path"] == "roms/pcecd/OldGame/OldGame.cue"


def test_folder_rename_raises_on_folder_collision_without_suffix(conn):
    sid = config.SHARED_SESSION_ID
    folder = _cd_folder(sid)
    _write(folder / "OldGame.cue")
    _write(_cd_folder(sid, "NewGame") / "placeholder.bin")  # target folder exists
    row = _insert_rom(conn, rom_id="r1", system_key="pcecd", stored_name="OldGame.cue",
                       rom_path="roms/pcecd/OldGame/OldGame.cue")

    with pytest.raises(ValueError, match="같은 이름의 폴더"):
        renames.rename_rom(conn, sid, row, "NewGame")

    assert folder.exists()  # untouched


def test_folder_rename_suffix_on_clash_renames_folder_and_file(conn):
    sid = config.SHARED_SESSION_ID
    folder = _cd_folder(sid)
    _write(folder / "OldGame.cue")
    _write(_cd_folder(sid, "NewGame") / "placeholder.bin")
    row = _insert_rom(conn, rom_id="r1", system_key="pcecd", stored_name="OldGame.cue",
                       rom_path="roms/pcecd/OldGame/OldGame.cue")

    result = renames.rename_rom(conn, sid, row, "NewGame", suffix_on_clash=True)

    clashed_folder = storage.roms_dir(sid, "pcecd") / "NewGame (2)"
    assert clashed_folder.exists()
    assert (clashed_folder / "NewGame (2).cue").exists()
    assert result["rom_path"] == "roms/pcecd/NewGame (2)/NewGame (2).cue"
