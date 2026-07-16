"""Backfill a No-Intro-style CRC32 for every ROM into a new roms.crc32 column.

Why CRC32 (not the existing sha256 content_hash): No-Intro DATs, RetroArch and
Korean-patch checksum lists are keyed on CRC32, so this is what lets us later
match a file against a known-Korean-patch list WITHOUT booting it. SNES .smc
dumps may carry a 512-byte copier header; No-Intro strips it before hashing, so
we do too (size % 1024 == 512). Everything else is hashed as-is.

Idempotent: adds the column if missing, only fills rows where crc32 IS NULL.
Run inside the container:  docker exec -w /app/backend game-and-what python backfill_crc.py
"""
import zlib
from pathlib import Path

from app import db
from app.services import storage

SESSION = "public"
root = storage.session_root(SESSION)


def rom_crc(path: Path, system_key: str) -> str:
    data = path.read_bytes()
    # SNES copier header — the one system where dumps commonly carry a 512-byte
    # header that No-Intro/CRC lists exclude.
    if system_key == "snes" and len(data) % 1024 == 512:
        data = data[512:]
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08X}"


with db.connect() as conn:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(roms)")}
    if "crc32" not in cols:
        conn.execute("ALTER TABLE roms ADD COLUMN crc32 TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_roms_crc32 ON roms(crc32)")
        print("added crc32 column + index")

    rows = conn.execute(
        "SELECT id, system_key, rom_path FROM roms WHERE crc32 IS NULL"
    ).fetchall()

done = missing = 0
for rom_id, system_key, rom_path in rows:
    abs_path = root / rom_path
    if not abs_path.exists():
        missing += 1
        continue
    crc = rom_crc(abs_path, system_key)
    with db.connect() as conn:
        conn.execute("UPDATE roms SET crc32 = ? WHERE id = ?", (crc, rom_id))
    done += 1

print(f"crc32 backfill: filled {done}, missing-file {missing}, already-set {5121 - len(rows)}")
