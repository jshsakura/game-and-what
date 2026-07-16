"""One-off: register the Korean Sega 32X romset (dropped into /roms/32x/ from the
miyoo-library export) into the DB. Mirrors import_segacd.py, with two differences:

  • covers ARE present (covers/32x/<stem>.img, the device .565 image) — link them
    so cover_status='ok' instead of fetching later. Web previews (.webp) are NOT
    in the export, so regenerate those from the UI/autofill after import.
  • sd_exclude=1 on every row: the 32X is browser-play-only (download-excluded),
    same policy the user set for it — so it stays in the library but off the SD ZIP.

Idempotent: skips files already in the roms table.
"""
from pathlib import Path

from app import db
from app.services import storage, langtag, romtag, name_index

SESSION = "public"
SYSTEM = "32x"
FLAG = {"ko", "ja", "en", "zh", "es", "de", "fr", "it", "eu"}

root = storage.session_root(SESSION)
rom_dir = root / "roms" / SYSTEM
cover_dir = root / "covers" / SYSTEM
files = sorted(p for p in rom_dir.iterdir() if p.suffix.lower() == ".32x")

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

    cover_img = cover_dir / f"{stem}.img"
    has_cover = cover_img.exists()
    cover_path = f"covers/{SYSTEM}/{stem}.img" if has_cover else None
    cover_status = "ok" if has_cover else "none"
    cover_source = "auto" if has_cover else None

    with db.connect() as conn:
        conn.execute(
            """INSERT INTO roms (id, session_id, system_key, original_name, stored_name,
                   korean_name, rom_path, cover_path, cover_status, cover_source, orig_lang,
                   play_lang, is_korean_patched, lang_source, region, cover_flag, content_hash,
                   sd_exclude, igdb_score, igdb_votes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                storage.new_id(), SESSION, SYSTEM, stem, stored_name, None,
                f"roms/{SYSTEM}/{stored_name}", cover_path, cover_status, cover_source,
                li.orig_lang, li.play_lang, int(li.is_korean_patched), li.source,
                region, cover_flag, chash, 1, -1, 0,
            ),
        )
    added += 1

print(f"32x import: added {added}, skipped {skipped} (already present), total files {len(files)}")
