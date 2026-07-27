# -*- coding: utf-8 -*-
"""The three settings init_db() applies for concurrency and query speed.

None of them change what the app returns, which is exactly why they need pinning: if
one silently stopped being applied, every test would still pass and the only symptom
would be a slower, lock-prone database nobody thought to look at.
"""
from app import db


def test_wal_is_on(session_id):
    """A background cover autofill writes while the library grid polls. Under the
    default rollback journal that write locks the whole database and the read waits."""
    with db.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_busy_timeout_is_set(session_id):
    """Writers still serialise under WAL. Without a timeout the loser of a race fails
    immediately with "database is locked" instead of waiting its turn."""
    with db.connect() as conn:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_library_query_uses_the_composite_index_and_no_temp_sort(session_id):
    """The library grid's query — every rom for the session, newest first. It used to
    take session_id off one index and then sort the whole result in a temp B-tree; the
    composite index answers both halves. Pinning the PLAN, not a timing, because a
    timing would be flaky and the plan is the actual claim."""
    with db.connect() as conn:
        plan = " ".join(
            r[-1] for r in conn.execute(
                "EXPLAIN QUERY PLAN "
                "SELECT * FROM roms WHERE session_id = ? ORDER BY created_at DESC",
                ("public",),
            )
        )
    assert "idx_roms_session_created" in plan, plan
    assert "TEMP B-TREE" not in plan.upper(), plan


def test_foreign_keys_still_on(session_id):
    """Was already true; kept here so the pragma block is covered as a whole."""
    with db.connect() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
