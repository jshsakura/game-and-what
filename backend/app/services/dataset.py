"""The parts of this database that are ABOUT THE GAMES, packaged for anyone to use.

Without the name dictionary this project is a file manager. The dictionary is the work —
1,900-odd Korean names, matched by hand and by list over months — and it is the one thing
a new installation cannot produce for itself. So it ships: in the repo as seed data, and
from a running server as an endpoint.

**What makes this safe to hand out is the shape of `rom_names`, not any scrubbing we do
here.** It is keyed by the SHA-256 of the rom's CONTENTS and holds nothing else: no
session, no path, no filename of mine, no timestamp anyone could read a habit out of.
Somebody hashes their own rom and gets a name back. No rom ever moves.

Everything that would say something about MY library instead of about a game lives in
other tables and is not touched by this module: `events` (an activity log is a behavioural
trace), `music`/`videos` (personal media), `sessions`/`uploads`, and on `roms` the paths,
stored names, favourites and sd_include/sd_exclude flags — those are my choices, not facts.

Deliberately NOT exported, for reasons that are not privacy:
  - Cover IMAGES. We ship where a cover came from, never the file. Fetch your own.
  - IGDB scores. They are IGDB's data under IGDB's terms, not ours to redistribute.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import config, db
from . import storage

# The repo's copy: what a fresh clone gets before it has ever seen a rom. Lives at the
# repo root (data/), NOT under backend/data — that one is the user's library.
SEED_PATH = Path(__file__).resolve().parents[3] / "data" / "names.ko.json"

FORMAT = 1


def export_names(conn, lang: str = "ko") -> dict:
    """Every resolved name, keyed by content hash. Sorted, so a re-export diffs cleanly."""
    rows = conn.execute(
        """SELECT hash, system_key, korean_name, original_name, source
             FROM rom_names
            WHERE lang = ? AND korean_name IS NOT NULL
            ORDER BY system_key, hash""",
        (lang,),
    ).fetchall()
    return {
        "format": FORMAT,
        "lang": lang,
        "count": len(rows),
        # Per-row provenance, free: `source` already records which list or hand-edit
        # resolved each name ('꿀렁', 'atari-collection', 'manual', …).
        "names": [
            {
                "hash": r["hash"],
                "system": r["system_key"],
                "name": r["korean_name"],
                # The filename the rom arrived under. It is the fallback key when a hash
                # misses — a different dump of the same game hashes differently — and it
                # is the game's name, not mine: renames live in roms.stored_name.
                "original_name": r["original_name"],
                "source": r["source"],
            }
            for r in rows
        ],
    }


def import_names(conn, payload: dict, lang: str = "ko") -> tuple[int, int]:
    """Merge a shared dictionary in. Returns (added, skipped).

    INSERT OR IGNORE, never REPLACE: a name I fixed by hand outranks anything that
    arrives from a file, and a merge must never quietly overwrite it.
    """
    if payload.get("format") != FORMAT:
        raise ValueError(f"unknown dataset format: {payload.get('format')!r}")

    added = skipped = 0
    for row in payload.get("names") or []:
        h, system, name = row.get("hash"), row.get("system"), row.get("name")
        if not (h and system and name):
            skipped += 1
            continue
        cur = conn.execute(
            """INSERT OR IGNORE INTO rom_names
                   (hash, system_key, korean_name, source, lang, original_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (h, system, storage.nfc(name), row.get("source"), lang,
             storage.nfc(row["original_name"]) if row.get("original_name") else None),
        )
        added += cur.rowcount
        skipped += 1 - cur.rowcount
    return added, skipped


def seed_if_empty() -> tuple[int, int]:
    """A Korean install starts with the dictionary, not with nothing.

    KOREAN_MODE, because that is the flag the whole Korean-name resolve hangs off
    (config.py) — the international image has no use for a Korean dictionary and should
    not carry one into its database.

    Only when the table is EMPTY: after that the local database is the authority, and a
    seed file arriving with a release must not walk over what the user has since named.
    """
    if not config.KOREAN_MODE or not SEED_PATH.exists():
        return (0, 0)
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM rom_names LIMIT 1").fetchone():
            return (0, 0)
        payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        return import_names(conn, payload)
