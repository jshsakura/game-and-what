"""One-off: register the Game Boy Advance romset (already dropped into /roms/gba/)
into the DB so the DB-driven library doesn't desync from the files. Mirrors the
column set the rest of the library uses (see import_vb.py). Idempotent: skips
files already in the roms table.

GBA-specific: each cart header carries a 4-char game code at 0xAC, and gpSP can
only skip a game's VBlank busy-wait if THAT code is in its idle-loop table. No
code in the table → no skip → no chance of full speed on the G&W's M7. So we read
the header of every ROM and set `idle_loop` from the merged table in
scripts/gba_idle_loop_db.json (see scripts/gba_idle_match.py).

Covers are left empty (cover_status='none'); they're fetched later via the
cover-search UI / autofill (libretro/igdb/tgdb mappings were added for gba).
"""
import json
from pathlib import Path

from app import db
from app.services import storage, langtag, romtag, name_index

SESSION = "public"
SYSTEM = "gba"
FLAG = {"ko", "ja", "en", "zh", "es", "de", "fr", "it", "eu"}

# GBA cartridge header (GBATEK).
GAME_CODE_OFFSET = 0xAC
GAME_CODE_LENGTH = 4
FIXED_BYTE_OFFSET = 0xB2
FIXED_BYTE_VALUE = 0x96
HEADER_LENGTH = 0xC0

DB_PATH = Path(__file__).resolve().parent.parent / "scripts" / "gba_idle_loop_db.json"


def load_idle_codes() -> set[str]:
    """Game codes whose VBlank idle loop gpSP knows how to skip."""
    rows = json.loads(DB_PATH.read_text(encoding="utf-8"))
    return {r["game_code"] for r in rows if r.get("has_idle")}


def game_code(path: Path) -> str | None:
    """The 4-char code from the cart header, or None if this isn't a GBA ROM."""
    header = path.open("rb").read(HEADER_LENGTH)
    if len(header) < HEADER_LENGTH or header[FIXED_BYTE_OFFSET] != FIXED_BYTE_VALUE:
        return None
    return header[GAME_CODE_OFFSET:GAME_CODE_OFFSET + GAME_CODE_LENGTH].decode("ascii", "replace")


idle_codes = load_idle_codes()
root = storage.session_root(SESSION)
rom_dir = root / "roms" / SYSTEM
files = sorted(p for p in rom_dir.iterdir() if p.suffix.lower() == ".gba")

with db.connect() as conn:
    existing = {
        r[0]
        for r in conn.execute(
            "SELECT stored_name FROM roms WHERE session_id=? AND system_key=?",
            (SESSION, SYSTEM),
        )
    }

added = skipped = flagged = headerless = 0
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

    code = game_code(path)
    if code is None:
        # e-Reader / NES-e cards carry a .gba extension but no cart header.
        headerless += 1
    idle_loop = int(code in idle_codes) if code else 0
    flagged += idle_loop

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
                   igdb_score, igdb_votes, idle_loop)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                storage.new_id(), SESSION, SYSTEM, stem, stored_name, None,
                f"roms/{SYSTEM}/{stored_name}", None, "none",
                li.orig_lang, li.play_lang, int(li.is_korean_patched), li.source,
                region, cover_flag, chash, -1, 0, idle_loop,
            ),
        )
    added += 1

print(f"gba import: added {added}, skipped {skipped} (already present), total files {len(files)}")
print(f"  idle-loop flagged: {flagged}   headerless (not a GBA cart): {headerless}")
