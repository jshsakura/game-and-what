"""Activity feed — an append-only log of library changes (uploads, renames,
PICO-8 compat edits, deletes…) so anyone using the shared library can see what
changed and when. Written inside the SAME transaction as the mutation it records
(pass the open conn), so an event is never logged for a change that rolled back.

Full history is kept (volume is low: a handful of events per curation session,
~100 bytes each). Deletes additionally carry a restore snapshot so a ROM can be
recovered from the _trash within the retention window (see RETENTION_DAYS).

Best-effort: logging must never break the underlying action — log() swallows its
own errors rather than failing the request.
"""
from __future__ import annotations

import json
import sqlite3

from . import storage

DEFAULT_LIMIT = 50      # recent window the bell panel requests by default
QUERY_MAX = 1000        # safety ceiling on a single API response
# How long a deleted ROM stays recoverable in _trash. After this its files are
# purged and the delete event flips to "expired" (no restore button).
RETENTION_DAYS = 30


def _parse(meta: str | None) -> dict | None:
    try:
        return json.loads(meta) if meta else None
    except Exception:
        return None


def log(
    conn: sqlite3.Connection,
    session_id: str,
    event_type: str,
    *,
    rom_id: str | None = None,
    rom_name: str | None = None,
    system_key: str | None = None,
    meta: dict | None = None,
) -> None:
    """Append one activity event. Never raises — a feed write must not sink the
    mutation that triggered it. Append-only: nothing is trimmed here."""
    try:
        conn.execute(
            """INSERT INTO events (id, session_id, event_type, rom_id, rom_name,
                   system_key, meta)
               VALUES (?,?,?,?,?,?,?)""",
            (storage.new_id(), session_id, event_type, rom_id, rom_name,
             system_key, json.dumps(meta, ensure_ascii=False) if meta else None),
        )
    except Exception:
        pass


def seed_uploads(conn: sqlite3.Connection, session_id: str) -> int:
    """Backfill the log from the existing library so history isn't empty: one
    rom_upload event per ROM that doesn't have one yet (idempotent — new uploads
    log their own, so this no-ops once converged). Returns rows seeded."""
    try:
        rows = conn.execute(
            """SELECT id, stored_name, system_key, created_at FROM roms r
                 WHERE session_id = ?
                   AND NOT EXISTS (SELECT 1 FROM events e
                     WHERE e.rom_id = r.id AND e.event_type = 'rom_upload')
                 ORDER BY created_at""",
            (session_id,),
        ).fetchall()
        for r in rows:
            conn.execute(
                """INSERT INTO events (id, session_id, event_type, rom_id, rom_name,
                       system_key, created_at) VALUES (?,?,?,?,?,?,?)""",
                (storage.new_id(), session_id, "rom_upload", r["id"], r["stored_name"],
                 r["system_key"], r["created_at"]),
            )
        return len(rows)
    except Exception:
        return 0


# Within the retention window? Uses the DB clock so it matches created_at (UTC).
_WITHIN = f"(created_at >= datetime('now', '-{RETENTION_DAYS} days'))"


def recent(conn: sqlite3.Connection, session_id: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Newest-first activity events. For deletes, `meta` is slimmed to the restore
    flags the UI needs ({restored, restorable, expired}) — the heavy snapshot stays
    server-side and is only read back when a restore is actually requested."""
    rows = conn.execute(
        f"""SELECT id, event_type, rom_id, rom_name, system_key, meta, created_at,
                  {_WITHIN} AS within_window
             FROM events WHERE session_id = ?
             ORDER BY created_at DESC, id DESC LIMIT ?""",
        (session_id, limit),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        meta = _parse(d.pop("meta"))
        within = bool(d.pop("within_window"))
        if d["event_type"] == "rom_delete":
            restored = bool((meta or {}).get("restored"))
            has_snap = bool((meta or {}).get("snapshot"))
            d["meta"] = {
                "restored": restored,
                "restorable": has_snap and not restored and within,
                "expired": has_snap and not restored and not within,
            }
        else:
            d["meta"] = meta
        out.append(d)
    return out


def get(conn: sqlite3.Connection, session_id: str, event_id: str) -> dict | None:
    """One event WITH its full meta (incl. restore snapshot) + window flag."""
    r = conn.execute(
        f"""SELECT id, event_type, rom_id, rom_name, system_key, meta, created_at,
                  {_WITHIN} AS within_window
             FROM events WHERE id = ? AND session_id = ?""",
        (event_id, session_id),
    ).fetchone()
    if r is None:
        return None
    d = dict(r)
    d["meta"] = _parse(d["meta"])
    d["within_window"] = bool(d.pop("within_window"))
    return d


def mark_restored(conn: sqlite3.Connection, event_id: str) -> None:
    """Flag a delete event as restored so its button turns into 'restored'."""
    row = conn.execute("SELECT meta FROM events WHERE id = ?", (event_id,)).fetchone()
    meta = (_parse(row["meta"]) if row else None) or {}
    meta["restored"] = True
    conn.execute("UPDATE events SET meta = ? WHERE id = ?",
                 (json.dumps(meta, ensure_ascii=False), event_id))
