# -*- coding: utf-8 -*-
"""app/db.py: the sqlite connection contract, schema init, and the additive
migration path. Pins:

  - connect() hands back row-dict access with foreign keys enforced, commits on
    a clean exit and rolls back on an exception (the "with db.connect()"
    pattern used everywhere else relies on this).
  - init_db() creates every table/index from scratch and is safe to call
    repeatedly (idempotent) — it seeds exactly one shared session row.
  - _migrate() is purely additive: given a pre-migration ("legacy") schema, it
    adds every missing column without touching existing data, including the
    one-time cover_flag backfill's CASE logic and its cleanup pass that nulls
    out anything outside the supported flag set.
"""
from __future__ import annotations

import sqlite3

import pytest

from app import config, db


# ── connect() ────────────────────────────────────────────────────────────────

def test_connect_yields_row_factory_with_foreign_keys_on(data_dir):
    with db.connect() as conn:
        assert conn.row_factory is sqlite3.Row
        fk_on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk_on == 1


def test_connect_commits_on_clean_exit(data_dir):
    db.init_db()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sessions (id, label) VALUES (?, ?)", ("committed-session", "x")
        )
    # A fresh connection must see the committed row.
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id FROM sessions WHERE id = ?", ("committed-session",)
        ).fetchone()
    assert row is not None


def test_connect_rolls_back_on_exception(data_dir):
    db.init_db()

    class _Boom(Exception):
        pass

    with pytest.raises(_Boom):
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, label) VALUES (?, ?)", ("rolled-back", "x")
            )
            raise _Boom("something went wrong mid-transaction")

    with db.connect() as conn:
        row = conn.execute(
            "SELECT id FROM sessions WHERE id = ?", ("rolled-back",)
        ).fetchone()
    assert row is None


# ── init_db() ────────────────────────────────────────────────────────────────

_EXPECTED_TABLES = {"sessions", "roms", "videos", "music", "uploads", "rom_names", "events"}


def test_init_db_creates_every_table(data_dir):
    db.init_db()
    with db.connect() as conn:
        names = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert _EXPECTED_TABLES <= names


def test_init_db_seeds_exactly_one_shared_session(data_dir):
    db.init_db()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, label FROM sessions WHERE id = ?", (config.SHARED_SESSION_ID,)
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["label"] == "shared"


def test_init_db_is_idempotent(data_dir):
    db.init_db()
    db.init_db()
    db.init_db()
    with db.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE id = ?", (config.SHARED_SESSION_ID,)
        ).fetchone()[0]
    assert count == 1


def test_init_db_creates_data_dir_and_library_dir(data_dir):
    # config.ensure_dirs() is called from init_db(); the isolated data_dir
    # fixture already creates it once, so assert it survives a fresh call too.
    db.init_db()
    assert config.LIBRARY_DIR.exists()


# ── _migrate() additive columns ─────────────────────────────────────────────

_LEGACY_ROMS_SCHEMA = """
CREATE TABLE roms (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(id),
    system_key   TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_name  TEXT NOT NULL,
    korean_name  TEXT,
    rom_path     TEXT NOT NULL,
    cover_path   TEXT,
    cover_status TEXT NOT NULL DEFAULT 'none',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_LEGACY_ROM_NAMES_SCHEMA = """
CREATE TABLE rom_names (
    hash         TEXT PRIMARY KEY,
    system_key   TEXT NOT NULL,
    korean_name  TEXT NOT NULL,
    source       TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _make_legacy_conn(data_dir) -> sqlite3.Connection:
    """A raw connection over a bare pre-migration schema (no additive columns),
    with the shared session row present so roms.session_id's FK is satisfiable."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, label TEXT)")
    conn.execute(_LEGACY_ROMS_SCHEMA)
    conn.execute(_LEGACY_ROM_NAMES_SCHEMA)
    conn.execute("INSERT INTO sessions (id, label) VALUES (?, 'shared')", (config.SHARED_SESSION_ID,))
    conn.commit()
    return conn


def test_migrate_adds_all_missing_roms_columns(data_dir):
    conn = _make_legacy_conn(data_dir)
    try:
        db._migrate(conn)
        conn.commit()
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(roms)")}
    finally:
        conn.close()

    expected_new_cols = {
        "cover_source", "crop_box", "orig_lang", "play_lang", "is_korean_patched",
        "lang_source", "cover_flag", "region", "sd_include", "igdb_score",
        "igdb_votes", "sd_exclude", "extra_files", "content_hash", "favorite",
        "pico8_compat", "pico8_mem_hint", "patch_ver",
    }
    assert expected_new_cols <= cols


def test_migrate_adds_rom_names_lang_and_original_name_columns(data_dir):
    conn = _make_legacy_conn(data_dir)
    try:
        db._migrate(conn)
        conn.commit()
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(rom_names)")}
    finally:
        conn.close()

    assert "lang" in cols
    assert "original_name" in cols


def test_migrate_new_boolean_columns_default_to_zero(data_dir):
    conn = _make_legacy_conn(data_dir)
    try:
        conn.execute(
            "INSERT INTO roms (id, session_id, system_key, original_name, stored_name, rom_path) "
            "VALUES ('r1', ?, 'nes', 'Game.nes', 'Game.nes', 'roms/nes/Game.nes')",
            (config.SHARED_SESSION_ID,),
        )
        conn.commit()
        db._migrate(conn)
        conn.commit()
        row = conn.execute("SELECT * FROM roms WHERE id = 'r1'").fetchone()
    finally:
        conn.close()

    assert row["is_korean_patched"] == 0
    assert row["sd_include"] == 0
    assert row["sd_exclude"] == 0
    assert row["favorite"] == 0


@pytest.mark.parametrize(
    "is_korean_patched,play_lang,orig_lang,expected_flag",
    [
        (1, "en", "ja", "ko"),          # Korean-patched always wins, regardless of play/orig lang
        (0, "ja", "en", "ja"),          # falls back to play_lang
        (0, "", "en", "en"),            # falls back to orig_lang when play_lang is blank
        (0, "", "", None),              # nothing to derive from -> NULL
        (0, "xx", "en", None),          # play_lang outside the supported flag set -> cleaned to NULL
    ],
)
def test_migrate_backfills_cover_flag_from_existing_lang_columns(
    data_dir, is_korean_patched, play_lang, orig_lang, expected_flag
):
    """Simulates a DB that already ran an EARLIER migration adding
    is_korean_patched/play_lang/orig_lang (but not cover_flag yet) — the
    realistic order a production DB would actually be in — and checks the
    one-time cover_flag backfill CASE logic plus its NOT IN(...) cleanup pass."""
    conn = _make_legacy_conn(data_dir)
    try:
        conn.execute("ALTER TABLE roms ADD COLUMN is_korean_patched INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE roms ADD COLUMN play_lang TEXT")
        conn.execute("ALTER TABLE roms ADD COLUMN orig_lang TEXT")
        conn.execute(
            "INSERT INTO roms (id, session_id, system_key, original_name, stored_name, rom_path, "
            "is_korean_patched, play_lang, orig_lang) "
            "VALUES ('r1', ?, 'nes', 'Game.nes', 'Game.nes', 'roms/nes/Game.nes', ?, ?, ?)",
            (config.SHARED_SESSION_ID, is_korean_patched, play_lang, orig_lang),
        )
        conn.commit()

        db._migrate(conn)
        conn.commit()
        row = conn.execute("SELECT cover_flag FROM roms WHERE id = 'r1'").fetchone()
    finally:
        conn.close()

    assert row["cover_flag"] == expected_flag


def test_migrate_is_a_noop_on_an_already_current_schema(data_dir):
    # init_db() already runs the full schema + migration once; calling migrate
    # again directly must not raise (every ALTER is guarded by a column check).
    db.init_db()
    with db.connect() as conn:
        db._migrate(conn)  # should not raise


# ── row_to_dict() ────────────────────────────────────────────────────────────

def test_row_to_dict_converts_row_to_plain_dict(data_dir):
    db.init_db()
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, label FROM sessions WHERE id = ?", (config.SHARED_SESSION_ID,)
        ).fetchone()
        result = db.row_to_dict(row)
    assert result == {"id": config.SHARED_SESSION_ID, "label": "shared"}


def test_row_to_dict_passes_through_none():
    assert db.row_to_dict(None) is None
