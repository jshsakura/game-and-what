"""One-off: register the Atari Lynx romset (already extracted into
/roms/lynx/) into the DB so the DB-driven library doesn't desync from the
dropped files. Mirrors the column set the rest of the library uses
(see restore_a2600.py). Idempotent: skips files already in the roms table.

Covers are left empty (cover_status='none'); they're fetched later via the
cover-search UI / autofill (igdb/tgdb/libretro mappings were added for lynx).
"""
from pathlib import Path

from app import db
from app.services import storage, langtag, romtag, name_index

SESSION = "public"
SYSTEM = "lynx"
FLAG = {"ko", "ja", "en", "zh", "es", "de", "fr", "it", "eu"}

root = storage.session_root(SESSION)
rom_dir = root / "roms" / SYSTEM
files = sorted(p for p in rom_dir.iterdir() if p.suffix.lower() == ".lnx")

with db.connect() as conn:
    existing = {
        r[0]
        for r in conn.execute(
            "SELECT stored_name FROM roms WHERE session_id=? AND system_key=?",
            (SESSION, SYSTEM),
        )
    }

added = skipped = 0
for path in files:
    safe = storage.safe_name(path.name)
    # Rename on disk if NFC/whitespace normalization changed anything, so the
    # stored_name and the actual file path stay 1:1.
    if safe != path.name:
        dst = path.with_name(safe)
        path.replace(dst)
        path = dst
    stored_name = path.name
    if stored_name in existing:
        skipped += 1
        continue

    stem = stored_name.rsplit(".", 1)[0]
    li = langtag.detect(stored_name)
    region = romtag.region_of(stored_name)
    cf = (li.play_lang or li.orig_lang or "").lower()
    cover_flag = cf if cf in FLAG else None
    chash = name_index.hash_bytes(path.read_bytes())

    with db.connect() as conn:
        conn.execute(
            """INSERT INTO roms (id, session_id, system_key, original_name, stored_name,
                   korean_name, rom_path, cover_path, cover_status, orig_lang, play_lang,
                   is_korean_patched, lang_source, region, cover_flag, content_hash,
                   igdb_score, igdb_votes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                storage.new_id(), SESSION, SYSTEM, stem, stored_name, None,
                f"roms/{SYSTEM}/{stored_name}", None, "none",
                li.orig_lang, li.play_lang, int(li.is_korean_patched), li.source,
                region, cover_flag, chash, -1, 0,
            ),
        )
    added += 1

print(f"lynx import: added {added}, skipped {skipped} (already present), total files {len(files)}")
