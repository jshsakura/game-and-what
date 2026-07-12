# -*- coding: utf-8 -*-
"""services/jobs.py (in-memory job registry) and services/events.py (append-only
activity feed). Pinned behaviour:
  - jobs: immutable Job replace-on-update, unknown-id is a no-op (never raises),
    create() resets any prior cancellation flag for that id.
  - events: log() never raises (best-effort), seed_uploads() is idempotent,
    recent() slims rom_delete meta to {restored, restorable, expired} using the
    RETENTION_DAYS window, mark_restored() flips the restored flag in place.
"""
from __future__ import annotations

import sqlite3
import uuid

import pytest

from app import config, db
from app.services import events, jobs


# ---------------------------------------------------------------------------
# jobs.py
# ---------------------------------------------------------------------------

def _jid() -> str:
    """A fresh job id per test — jobs._jobs/_cancelled are module-level globals
    shared across the whole test session, so ids must never collide."""
    return f"job-{uuid.uuid4().hex}"


def test_create_returns_queued_job_with_defaults():
    jid = _jid()

    job = jobs.create(jid, "sd_zip")

    assert job.id == jid
    assert job.kind == "sd_zip"
    assert job.status == "queued"
    assert job.progress == 0.0
    assert job.message == ""
    assert job.result is None


def test_get_returns_the_created_job():
    jid = _jid()
    jobs.create(jid, "video_encode")

    fetched = jobs.get(jid)

    assert fetched is not None
    assert fetched.kind == "video_encode"


def test_get_unknown_job_returns_none():
    assert jobs.get(_jid()) is None


def test_update_replaces_immutably_without_mutating_the_old_reference():
    jid = _jid()
    original = jobs.create(jid, "sd_zip")

    updated = jobs.update(jid, status="running", progress=0.5, message="halfway")

    # the dataclass instance already handed back to the caller is untouched
    assert original.status == "queued"
    assert original.progress == 0.0
    # the registry now holds the new state
    assert updated.status == "running"
    assert updated.progress == 0.5
    assert updated.message == "halfway"
    assert jobs.get(jid).status == "running"


def test_update_unknown_job_returns_none_and_does_not_raise():
    assert jobs.update(_jid(), status="done") is None


def test_as_dict_rounds_progress_and_includes_all_fields():
    jid = _jid()
    jobs.create(jid, "sd_zip")
    jobs.update(jid, progress=1 / 3, result={"etag": "abc"})

    d = jobs.get(jid).as_dict()

    assert d == {
        "id": jid,
        "kind": "sd_zip",
        "status": "queued",
        "progress": round(1 / 3, 3),
        "message": "",
        "result": {"etag": "abc"},
    }


def test_request_cancel_unknown_job_returns_false():
    assert jobs.request_cancel(_jid()) is False


def test_request_cancel_known_job_flags_is_cancelled():
    jid = _jid()
    jobs.create(jid, "sd_zip")
    assert jobs.is_cancelled(jid) is False

    assert jobs.request_cancel(jid) is True

    assert jobs.is_cancelled(jid) is True


def test_create_resets_a_prior_cancellation_flag():
    """A job id reused after being cancelled (e.g. a restarted build) must not
    start out already-cancelled."""
    jid = _jid()
    jobs.create(jid, "sd_zip")
    jobs.request_cancel(jid)
    assert jobs.is_cancelled(jid) is True

    jobs.create(jid, "sd_zip")  # re-created (same id)

    assert jobs.is_cancelled(jid) is False


# ---------------------------------------------------------------------------
# events.py
# ---------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path, monkeypatch):
    """A real sqlite connection against an isolated, schema-migrated DB file —
    events.py runs raw SQL against the `events`/`roms` tables, so an in-memory
    stub without the migrations would be a poor substitute."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gnw.db")
    monkeypatch.setattr(config, "TMP_DIR", tmp_path / "tmp")
    db.init_db()
    with db.connect() as c:
        yield c


def test_log_appends_a_readable_event(conn):
    events.log(conn, config.SHARED_SESSION_ID, "rom_upload", rom_id="r1",
               rom_name="Game.nes", system_key="nes", meta={"size": 123})

    rows = events.recent(conn, config.SHARED_SESSION_ID)

    assert len(rows) == 1
    assert rows[0]["event_type"] == "rom_upload"
    assert rows[0]["rom_id"] == "r1"
    assert rows[0]["rom_name"] == "Game.nes"
    assert rows[0]["meta"] == {"size": 123}


def test_log_with_no_meta_stores_null(conn):
    events.log(conn, config.SHARED_SESSION_ID, "rom_upload", rom_id="r1")

    row = events.recent(conn, config.SHARED_SESSION_ID)[0]

    assert row["meta"] is None


def test_log_never_raises_even_against_a_broken_connection():
    """log() is best-effort: a logging failure must never sink the mutation it
    is attached to."""
    bare = sqlite3.connect(":memory:")  # no schema at all -> INSERT will fail

    events.log(bare, "public", "rom_upload", rom_id="r1")  # must not raise


def test_seed_uploads_backfills_one_event_per_unlogged_rom(conn):
    conn.execute(
        "INSERT INTO roms (id, session_id, system_key, original_name, stored_name, rom_path) "
        "VALUES ('rom1', ?, 'nes', 'Game.nes', 'Game.nes', 'roms/nes/Game.nes')",
        (config.SHARED_SESSION_ID,),
    )

    seeded = events.seed_uploads(conn, config.SHARED_SESSION_ID)

    assert seeded == 1
    rows = events.recent(conn, config.SHARED_SESSION_ID)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "rom_upload"
    assert rows[0]["rom_id"] == "rom1"


def test_seed_uploads_is_idempotent(conn):
    conn.execute(
        "INSERT INTO roms (id, session_id, system_key, original_name, stored_name, rom_path) "
        "VALUES ('rom1', ?, 'nes', 'Game.nes', 'Game.nes', 'roms/nes/Game.nes')",
        (config.SHARED_SESSION_ID,),
    )
    events.seed_uploads(conn, config.SHARED_SESSION_ID)

    seeded_again = events.seed_uploads(conn, config.SHARED_SESSION_ID)

    assert seeded_again == 0
    assert len(events.recent(conn, config.SHARED_SESSION_ID)) == 1


def test_seed_uploads_swallows_errors_and_returns_zero():
    bare = sqlite3.connect(":memory:")  # no roms table -> SELECT raises

    assert events.seed_uploads(bare, "public") == 0


def test_recent_orders_newest_first_and_respects_limit(conn):
    for i in range(3):
        conn.execute(
            "INSERT INTO events (id, session_id, event_type, created_at) "
            "VALUES (?, ?, 'rom_upload', datetime('now', ?))",
            (f"e{i}", config.SHARED_SESSION_ID, f"+{i} seconds"),
        )

    rows = events.recent(conn, config.SHARED_SESSION_ID, limit=2)

    assert len(rows) == 2
    assert rows[0]["id"] == "e2"  # newest (largest offset) first
    assert rows[1]["id"] == "e1"


def test_recent_slims_delete_meta_to_restorable_within_window(conn):
    conn.execute(
        "INSERT INTO events (id, session_id, event_type, meta) VALUES "
        "('d1', ?, 'rom_delete', ?)",
        (config.SHARED_SESSION_ID, '{"snapshot": {"id": "rom1"}, "restored": false}'),
    )

    row = events.recent(conn, config.SHARED_SESSION_ID)[0]

    assert row["meta"] == {"restored": False, "restorable": True, "expired": False}


def test_recent_slims_delete_meta_to_expired_outside_window(conn):
    conn.execute(
        "INSERT INTO events (id, session_id, event_type, meta, created_at) VALUES "
        "('d1', ?, 'rom_delete', ?, datetime('now', '-31 days'))",
        (config.SHARED_SESSION_ID, '{"snapshot": {"id": "rom1"}, "restored": false}'),
    )

    row = events.recent(conn, config.SHARED_SESSION_ID)[0]

    assert row["meta"] == {"restored": False, "restorable": False, "expired": True}


def test_recent_slims_delete_meta_to_restored_once_restored(conn):
    conn.execute(
        "INSERT INTO events (id, session_id, event_type, meta) VALUES "
        "('d1', ?, 'rom_delete', ?)",
        (config.SHARED_SESSION_ID, '{"snapshot": {"id": "rom1"}, "restored": true}'),
    )

    row = events.recent(conn, config.SHARED_SESSION_ID)[0]

    assert row["meta"] == {"restored": True, "restorable": False, "expired": False}


def test_recent_delete_meta_without_snapshot_is_never_restorable(conn):
    """A delete event with no restore snapshot (e.g. an old row predating the
    recovery feature) must not offer a restore button."""
    conn.execute(
        "INSERT INTO events (id, session_id, event_type, meta) VALUES "
        "('d1', ?, 'rom_delete', ?)",
        (config.SHARED_SESSION_ID, '{"restored": false}'),
    )

    row = events.recent(conn, config.SHARED_SESSION_ID)[0]

    assert row["meta"] == {"restored": False, "restorable": False, "expired": False}


def test_parse_returns_none_for_malformed_json_meta(conn):
    conn.execute(
        "INSERT INTO events (id, session_id, event_type, meta) VALUES "
        "('e1', ?, 'rom_upload', 'not json')",
        (config.SHARED_SESSION_ID,),
    )

    row = events.recent(conn, config.SHARED_SESSION_ID)[0]

    assert row["meta"] is None


def test_get_returns_full_event_with_window_flag(conn):
    events.log(conn, config.SHARED_SESSION_ID, "rom_delete", rom_id="r1",
               meta={"snapshot": {"id": "r1"}, "restored": False})
    event_id = events.recent(conn, config.SHARED_SESSION_ID)[0]["id"]

    full = events.get(conn, config.SHARED_SESSION_ID, event_id)

    assert full["meta"]["snapshot"] == {"id": "r1"}  # full meta, not slimmed
    assert full["within_window"] is True


def test_get_unknown_event_returns_none(conn):
    assert events.get(conn, config.SHARED_SESSION_ID, "missing") is None


def test_mark_restored_sets_flag_and_preserves_other_meta(conn):
    events.log(conn, config.SHARED_SESSION_ID, "rom_delete", rom_id="r1",
               meta={"snapshot": {"id": "r1"}, "restored": False})
    event_id = events.recent(conn, config.SHARED_SESSION_ID)[0]["id"]

    events.mark_restored(conn, event_id)

    full = events.get(conn, config.SHARED_SESSION_ID, event_id)
    assert full["meta"]["restored"] is True
    assert full["meta"]["snapshot"] == {"id": "r1"}  # untouched
    slim = events.recent(conn, config.SHARED_SESSION_ID)[0]
    assert slim["meta"]["restorable"] is False


def test_mark_restored_on_event_with_no_meta_creates_one(conn):
    conn.execute(
        "INSERT INTO events (id, session_id, event_type) VALUES ('e1', ?, 'rom_delete')",
        (config.SHARED_SESSION_ID,),
    )

    events.mark_restored(conn, "e1")

    full = events.get(conn, config.SHARED_SESSION_ID, "e1")
    assert full["meta"] == {"restored": True}
