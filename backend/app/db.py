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
    cover_status TEXT NOT NULL DEFAULT 'none',  -- none|pending|ok|failed
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
    # Writers still serialise under WAL; this is what makes them WAIT for their turn
    # instead of failing on the spot. The default is 0 — no wait at all — so a cover
    # autofill and a probe finishing at the same moment could raise "database is
    # locked" at whichever one lost, on a write that had nothing wrong with it.
    conn.execute("PRAGMA busy_timeout = 5000")
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
    if "crc32" not in cols:
        # No-Intro/RetroArch-style CRC32 (SNES copier header stripped) — the id
        # Korean-patch checksum lists key on, so a ROM can be matched to a known
        # patch WITHOUT booting it (sha256 above is ours; CRC32 is the shared one).
        # NULL until backfilled — see backfill_crc.py.
        conn.execute("ALTER TABLE roms ADD COLUMN crc32 TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_roms_crc32 ON roms(crc32)")
    if "igdb_meta" not in cols:
        # Rich IGDB detail as JSON — release date, genres, developer, rating,
        # summary, screenshot URLs, videos. Fetched on demand (POST …/igdb-meta),
        # shown in the detail popup. NULL until fetched.
        conn.execute("ALTER TABLE roms ADD COLUMN igdb_meta TEXT")
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

    if "idle_loop" not in cols:
        # GBA only. gpSP can only skip a game's VBlank busy-wait if that game's
        # loop address is in its table (gba_over.h), keyed on the 4-char code in
        # the cart header; a game absent from the table busy-waits through the
        # whole frame and has no chance of full speed on the G&W's M7. 1 = the
        # ROM's header code is covered. Set at import from the merged idle-loop
        # database (scripts/gba_idle_loop_db.json, see scripts/gba_idle_match.py).
        # It marks a game as a full-speed CANDIDATE — not a promise: the skip only
        # pays off if the game actually idles for a good part of the frame.
        conn.execute("ALTER TABLE roms ADD COLUMN idle_loop INTEGER NOT NULL DEFAULT 0")

    if "exec_cycles" not in cols:
        # GBA only. The idle_loop flag says the VBlank wait CAN be skipped; it says
        # nothing about whether the game is light enough to keep up once it is. This
        # is the missing half: the cycles the CPU actually spends executing per frame,
        # out of a 280,896-cycle frame, measured by running the rom with the skip
        # active (scripts/idlefind). Weigh it against what the M7 leaves the CPU
        # (~90,000 cycles — timed on the device, see GBA_CPU_BUDGET in components.jsx)
        # for a verdict instead of a guess. NULL = not measured.
        conn.execute("ALTER TABLE roms ADD COLUMN exec_cycles INTEGER")

    if "probe_status" not in cols:
        # GBA only. Measuring a rom means RUNNING it for ~15s, so an upload cannot wait
        # for it: the rom lands as 'pending' and a background task fills in idle_loop /
        # exec_cycles. NULL = nothing to measure (not GBA, or no probe binary in this
        # build). 'pending' | 'ok' | 'failed' — a rom left 'pending' would spin in the
        # UI forever, so every probe MUST resolve to one of the other two.
        conn.execute("ALTER TABLE roms ADD COLUMN probe_status TEXT")

    if "idle_pc" not in cols:
        # The address itself, not just "there is one". Without it a measurement is only
        # good for the badge — the firmware needs the actual PC to hand gpSP, and losing
        # it would mean re-running the game to get it back. Hex string, e.g. "0x80008ce".
        # It is the backward BRANCH that closes the wait loop (what gpSP compares the PC
        # against), not the loop's start.
        conn.execute("ALTER TABLE roms ADD COLUMN idle_pc TEXT")

    if "idle_drop" not in cols:
        # What the skip actually BOUGHT, as measured: the share of the frame's work that
        # disappears when gpSP is given the address (the A/B drop, 0.0–1.0). exec_cycles
        # is the game's load with the skip on; this is the part the skip took back — and
        # it is the difference between ~34fps and 60fps, not a tuning knob. Measured, not
        # derived: for a game that already halts, most of the frame is idle too, and none
        # of that idleness is the skip's doing. NULL = no address, so nothing to buy.
        conn.execute("ALTER TABLE roms ADD COLUMN idle_drop REAL")

    if "audio_cycles" not in cols:
        # GBA only. What the game's SOUND DRIVER costs, per frame, in cycles — measured by
        # running the rom (scripts/idlefind).
        #
        # A GBA game does not write its own mixer. It links in a library — Nintendo's M4A
        # (Sappy) in most carts — which is copied into IWRAM at boot and then mixes every
        # sample in guest ARM code, every frame. The firmware replaces that library with a
        # native mixer, so ON THE DEVICE THE GUEST NEVER RUNS IT. exec_cycles includes it;
        # the device will not pay it. On Zelda: A Link to the Past that is 40% of the frame,
        # and it is the difference between 113% of budget and 68%.
        #
        # NULL = no driver found, or its block never ran.
        conn.execute("ALTER TABLE roms ADD COLUMN audio_cycles INTEGER")

    if "audio_variant" not in cols:
        # Which build of that library. 633 roms collapse into six — M4A is Nintendo's own
        # code and there are only a handful of SDK builds of it (mono, stereo, stereo2,
        # stereo3…), which is exactly why implementing six natively retires the cost for the
        # whole library. This is the hash of the block; `audio_name` is what the firmware
        # calls it, and a name means the firmware HAS a native mixer for it.
        conn.execute("ALTER TABLE roms ADD COLUMN audio_variant TEXT")

    if "audio_name" not in cols:
        conn.execute("ALTER TABLE roms ADD COLUMN audio_name TEXT")

    if "idle_hunted" not in cols:
        # We RAN the game and looked for a wait loop. 1 = looked; the answer, address or
        # not, is the game's and not the probe's.
        #
        # Without this a rom with no address and a full frame of work is ambiguous, and
        # the UI has to assume the kinder reading ("not measured") — which is right for a
        # rom we never chased and WRONG for one we did: the Classic NES carts have no wait
        # loop because they spend the frame emulating a NES. They are simply that heavy,
        # and saying "not measured" forever would hide it.
        conn.execute("ALTER TABLE roms ADD COLUMN idle_hunted INTEGER NOT NULL DEFAULT 0")

    if "snes_chip" not in cols:
        # SNES only. Which coprocessor the CARTRIDGE carries, read from its header at
        # upload (services/snes_hdr.py). Not a speed figure and not a verdict: a SNES
        # frame's cost is split across the 65816, the PPU and the SPC700, so a cycle
        # count would not mean here what exec_cycles means for `gba` — and this repo has
        # no SNES device timings to calibrate one against anyway.
        #
        # What it IS, is the fact that decides whether a port can run the game at all.
        # Star Fox without a GSU does not run slowly, it does not run. 91 of this
        # library's 2,281 snes roms carry something; 50 of those carry SuperFX or SA-1.
        #
        # 'none' = read, plain cart. 'unknown' = header failed its checksum, so we do not
        # know — kept distinct from 'none' for the same reason idle_hunted exists above:
        # a failure to look must never be recorded as an answer. NULL = never read.
        conn.execute("ALTER TABLE roms ADD COLUMN snes_chip TEXT")

    if "snes_map" not in cols:
        # The rest of what the same header read already had in hand and used to throw
        # away: the memory layout the cart wants ('LoROM', 'HiROM', 'ExHiROM', with
        # ' · FastROM' when it asks for 3.58 MHz access) and the size it declares in KB.
        #
        # They belong beside snes_chip for the same reason it is here — a port implements
        # a mapper or it does not — and because the declared size disagreeing with the
        # file on disk is how an overdump shows itself. NULL when the header failed its
        # checksum: those bytes are the ones we just refused to trust.
        conn.execute("ALTER TABLE roms ADD COLUMN snes_map TEXT")
        conn.execute("ALTER TABLE roms ADD COLUMN snes_rom_kb INTEGER")
        # Existing snes rows were stamped by the older read that only took the chip.
        # Clearing snes_chip puts them back in the backfill's sights on the next boot,
        # which is the whole recovery path — one query, and it converges again.
        conn.execute("UPDATE roms SET snes_chip = NULL WHERE system_key = 'snes'")

    # The library grid's query — every rom for the session, newest first — is the
    # heaviest thing this database does, and it had no index that could serve both halves
    # of it: session_id came off idx_roms_hash and then the whole result was sorted in a
    # temp B-tree. One composite index answers both. Measured on 5,019 roms: 74.8 ms →
    # 57.7 ms, and the plan loses its "USE TEMP B-TREE FOR ORDER BY" line. What is left is
    # materialising 5,019 wide rows, which no index can help with.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_roms_session_created "
        "ON roms (session_id, created_at DESC)"
    )

    # Videos moved from media/ to video/ (the folder the firmware actually browses),
    # so the stored relative paths have to follow. Idempotent: after the first run no
    # row starts with the legacy prefix. The files themselves are moved by
    # storage.migrate_legacy_media_dir() at startup.
    legacy_prefix = f"{config.LEGACY_MEDIA_DIR_NAME}/"
    has_videos = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='videos'").fetchone()
    if has_videos:
        conn.execute(
            "UPDATE videos SET avi_path = ? || substr(avi_path, ?) WHERE avi_path LIKE ?",
            (f"{config.MEDIA_DIR_NAME}/", len(legacy_prefix) + 1, f"{legacy_prefix}%"),
        )

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
        # WAL, set once — the mode lives in the file header, so this is a no-op on every
        # boot after the first. It is here for what the app actually does: a cover autofill
        # or a GBA probe writes in the background while the library grid polls. Under the
        # default rollback journal that write locks the whole database and the poll waits
        # behind it; measured on this library (5,019 roms), reads during a write went from
        # 1.36 ms median / 3.42 ms worst to 0.30 / 0.89.
        #
        # Safe here and not everywhere: WAL needs every reader on the same machine as the
        # file, which holds for one container on a local bind mount. It would not on NFS.
        # It also means gnw.db is no longer the whole story on disk — a copy taken without
        # its -wal sidecar can miss the newest commits, so use `sqlite3 .backup` (or stop
        # the container) rather than `cp` if you ever snapshot it.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(_SCHEMA)
        _migrate(conn)
        # The shared workspace always exists (single common library).
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, label) VALUES (?, 'shared')",
            (config.SHARED_SESSION_ID,),
        )
        # This database had NO planner statistics at all — every index choice was made off
        # sqlite's built-in guesses. `optimize` is the cheap form of fixing that: it runs
        # ANALYZE only on tables whose shape has actually moved since the last one, so a
        # settled library pays nothing for it on subsequent boots. Deliberately not VACUUM
        # — the file is 6 MB with 1.5% free pages, so a rewrite would reclaim about 90 kB
        # and is not worth the pause.
        conn.execute("PRAGMA optimize")


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
