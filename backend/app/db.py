"""SQLite metadata store. Files live on disk; this tracks what/where/status."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    label       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS roms (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(id),
    system_key   TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_name  TEXT NOT NULL,          -- on-device rom filename (may be Korean)
    korean_name  TEXT,                   -- resolved title, null if unmatched
    rom_path     TEXT NOT NULL,
    cover_path   TEXT,                   -- .img path, null until generated
    cover_status TEXT NOT NULL DEFAULT 'none',  -- none|ok|failed
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS videos (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(id),
    original_name TEXT NOT NULL,
    avi_name     TEXT NOT NULL,
    avi_path     TEXT,
    job_id       TEXT,
    status       TEXT NOT NULL DEFAULT 'queued',  -- queued|encoding|ok|failed
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS music (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(id),
    original_name TEXT NOT NULL,
    stored_name  TEXT NOT NULL,        -- on-SD filename: /music/<stored_name>
    music_path   TEXT NOT NULL,        -- relative path under the session root
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS uploads (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(id),
    filename     TEXT NOT NULL,
    total_size   INTEGER NOT NULL,
    received     INTEGER NOT NULL DEFAULT 0,
    kind         TEXT NOT NULL,          -- rom|video
    system_key   TEXT,                   -- required when kind=rom
    tmp_path     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'receiving',  -- receiving|complete|failed
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS rom_names (
    hash         TEXT PRIMARY KEY,      -- sha256 of the rom file
    system_key   TEXT NOT NULL,
    korean_name  TEXT NOT NULL,         -- resolved 'Korean (English)' base (no ext)
    source       TEXT,                  -- which 꿀렁 list resolved it
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS events (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(id),
    event_type   TEXT NOT NULL,         -- rom_upload|rom_rename|rom_delete|pico8_compat|lang_patch|sd_exclude
    rom_id       TEXT,                  -- null for roms since deleted (snapshot below)
    rom_name     TEXT,                  -- stored_name snapshot at event time
    system_key   TEXT,
    meta         TEXT,                  -- small JSON, varies by type (e.g. {"status":"broken"})
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_roms_session ON roms(session_id);
CREATE INDEX IF NOT EXISTS idx_videos_session ON videos(session_id);
CREATE INDEX IF NOT EXISTS idx_music_session ON music(session_id);
CREATE INDEX IF NOT EXISTS idx_uploads_session ON uploads(session_id);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, created_at DESC);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """A connection with row dicts and foreign keys on. Commits on clean exit."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Lightweight additive migrations (SQLite ALTER ADD COLUMN is a no-op-safe
    way to evolve the schema without dropping data)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(roms)")}
    if "cover_source" not in cols:
        # 'manual' = user uploaded / hand-picked → never overwritten by auto-fill.
        # 'auto'   = fetched by autocover/autoresolve → may be force-refreshed.
        conn.execute("ALTER TABLE roms ADD COLUMN cover_source TEXT")
    if "crop_box" not in cols:
        # The user's chosen crop region (JSON [x,y,w,h] fractions) so the web
        # DISPLAY thumbnail shows the SAME framing as the device .img. NULL =
        # center-crop. The full original preview is never modified.
        conn.execute("ALTER TABLE roms ADD COLUMN crop_box TEXT")

    # Language / Korean-patch facts, derived from the filename (꿀렁 'J-K' markers
    # or region tags) and overridable by the user. See services/langtag.py.
    if "orig_lang" not in cols:
        conn.execute("ALTER TABLE roms ADD COLUMN orig_lang TEXT")   # ja/en/ko/unl…, NULL=unknown
    if "play_lang" not in cols:
        conn.execute("ALTER TABLE roms ADD COLUMN play_lang TEXT")   # language it runs in (ko once patched)
    if "is_korean_patched" not in cols:
        conn.execute("ALTER TABLE roms ADD COLUMN is_korean_patched INTEGER NOT NULL DEFAULT 0")
    if "lang_source" not in cols:
        # 'auto' = filename-derived (safe to re-scan). 'manual' = user toggled →
        # an auto re-scan must NOT overwrite it (mirrors cover_source).
        conn.execute("ALTER TABLE roms ADD COLUMN lang_source TEXT")
    if "cover_flag" not in cols:
        # The flag/country shown on the cover, chosen EXPLICITLY per rom and
        # INDEPENDENT of the Korean-patch toggle. One of the supported flag codes
        # (ko/ja/en/zh/es/de/fr/it/eu) or NULL = no flag. Backfilled once from the
        # old derived logic (한글패치→ko, else play/orig lang) so existing covers
        # keep the flag they already had.
        conn.execute("ALTER TABLE roms ADD COLUMN cover_flag TEXT")
        conn.execute(
            "UPDATE roms SET cover_flag = CASE "
            "WHEN is_korean_patched = 1 THEN 'ko' "
            "WHEN lower(coalesce(play_lang,'')) <> '' THEN lower(play_lang) "
            "WHEN lower(coalesce(orig_lang,'')) <> '' THEN lower(orig_lang) "
            "ELSE NULL END"
        )
        conn.execute(
            "UPDATE roms SET cover_flag = NULL WHERE cover_flag NOT IN "
            "('ko','ja','en','zh','es','de','fr','it','eu')"
        )
    if "region" not in cols:
        # Region/dump locale parsed out of the filename (e.g. 'Japan',
        # 'USA, Europe, Brazil', 'Korea'). Kept here so it can be stripped from the
        # on-device display name while staying available for later use. See
        # services/romtag.py. NULL = no region tag found.
        conn.execute("ALTER TABLE roms ADD COLUMN region TEXT")
    if "sd_include" not in cols:
        # Homebrew ROM files are NOT shipped in the SD ZIP by default (homebrew apps
        # live inside the firmware; double-shipping conflicts) — only their cover is.
        # The user can opt a specific homebrew ROM in: sd_include=1 → its ROM file
        # is included. Ignored for non-homebrew systems (those always ship).
        conn.execute("ALTER TABLE roms ADD COLUMN sd_include INTEGER NOT NULL DEFAULT 0")
    if "igdb_score" not in cols:
        # IGDB total_rating (0-100, combined user+critic) for the matched game, used
        # to rank/curate a bloated set. NULL = not yet fetched; -1 = fetched but IGDB
        # has no rating; 0-100 = the score. igdb_votes = total_rating_count (a 92 from
        # 3 votes is noisier than a 92 from 1700 — kept so curation can weight by it).
        conn.execute("ALTER TABLE roms ADD COLUMN igdb_score INTEGER")
        conn.execute("ALTER TABLE roms ADD COLUMN igdb_votes INTEGER")
    if "sd_exclude" not in cols:
        # The inverse of sd_include, for NON-homebrew ROMs (which ship by default):
        # sd_exclude=1 drops this ROM's file + cover from the SD ZIP while KEEPING it
        # in the library/DB — used to slim a bloated set (AKA-dups, protos) without
        # deleting anything. Ignored for homebrew (those opt IN via sd_include).
        conn.execute("ALTER TABLE roms ADD COLUMN sd_exclude INTEGER NOT NULL DEFAULT 0")
    if "extra_files" not in cols:
        # Homebrew cards can hold MULTIPLE files under one cover (e.g. the app .bin
        # PLUS its assets .dat). rom_path is the primary file; extra_files is a JSON
        # array of the additional ones [{"name":..., "size":...}], all stored next
        # to it in roms/homebrew/. Packaging ships each by the .bin/.dat rule.
        conn.execute("ALTER TABLE roms ADD COLUMN extra_files TEXT")
    if "content_hash" not in cols:
        # sha256 of the ROM file's bytes — used to reject EXACT duplicates at upload
        # (same content re-uploaded under a different name → keep the existing entry,
        # which may already carry the Korean name). NULL until hashed/backfilled.
        conn.execute("ALTER TABLE roms ADD COLUMN content_hash TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_roms_hash ON roms(session_id, content_hash)")
    if "favorite" not in cols:
        # User-marked favorite (★) — purely a UI convenience for filtering/gathering
        # the roms you care about. No effect on packaging/download.
        conn.execute("ALTER TABLE roms ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0")
    if "pico8_compat" not in cols:
        # PICO-8 only: known runnability on the G&W z8lua engine, from the community
        # compatibility sheet — 'good' | 'partial' | 'broken' | NULL (untested).
        conn.execute("ALTER TABLE roms ADD COLUMN pico8_compat TEXT")
    if "pico8_mem_hint" not in cols:
        # PICO-8 only: rough static cart-complexity hint (percent of PICO-8 code
        # limits), computed at upload from the cart header. NOT the real device RAM
        # figure — just a first-pass nudge alongside the manual compat status.
        conn.execute("ALTER TABLE roms ADD COLUMN pico8_mem_hint INTEGER")
    if "patch_ver" not in cols:
        # Korean-patch version/date parsed from the ORIGINAL filename's
        # 'Korea-patch …vYYYYMMDD vX.Y' tag (preserved in original_name even after
        # the stored_name is cleaned). Sortable string "YYYY-MM-DD vX.Y" so the
        # newest patch of the same game can be picked objectively (vs upload time).
        # NULL = no patch-version tag found. See services/patchver.py.
        conn.execute("ALTER TABLE roms ADD COLUMN patch_ver TEXT")

    # Multi-language prep: the name-mapping cache is currently Korean ('ko'). A
    # `lang` column lets other languages (en/ja…) coexist later without a rebuild.
    rn_cols = {r["name"] for r in conn.execute("PRAGMA table_info(rom_names)")}
    if "lang" not in rn_cols:
        conn.execute("ALTER TABLE rom_names ADD COLUMN lang TEXT NOT NULL DEFAULT 'ko'")
    if "original_name" not in rn_cols:
        # The full ORIGINAL upload filename (region tag and all). Lets the
        # conversion DB resolve by (system_key, original_name) — not only by
        # content hash — so a re-upload or same-named dump maps to the known
        # Korean/clean name. See services/name_index.py.
        conn.execute("ALTER TABLE rom_names ADD COLUMN original_name TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rom_names_origin "
            "ON rom_names (system_key, original_name, lang)"
        )


def init_db() -> None:
    config.ensure_dirs()
    with connect() as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)
        # The shared workspace always exists (single common library).
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, label) VALUES (?, 'shared')",
            (config.SHARED_SESSION_ID,),
        )


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
