"""Give the Korean-patched GBA roms their Korean names.

The 2026-07-15 upload landed 107 roms named in English/romaji with the patch tag
still glued on ("Breath of Fire - Ryuu no Senshi (Korea-patch J-K v20090823)").
`patchver.py` already lifted that tag into the `patch_ver` column, so the name is
free to become the house form — "한글 (English)" — which is what every other
system in this library uses.

SOURCE: eagleforce.tistory.com via `app.services.tistory`, the same resolver the
other systems use. Its SYSMAP had no `gba` entry, so every GBA lookup was
silently returning None — the blog has the posts, we just never asked for them.
That one-line fix is what makes this script possible.

MATCH ON THE ENGLISH BASE, NOT THE RAW FILENAME. The patch tag has to come off
before the blog search or the query is nonsense. And the blog's [GBA] system tag
is what keeps a match honest — Double Dragon exists on half a dozen systems.

Only 'exact' matches (system tag + an English segment matching exactly) are
applied. 'fuzzy' and 'none' are printed for a human to eyeball, never guessed at:
this library learned the hard way that a confident fuzzy scorer paired both
Pokémon FireRed and LeafGreen with "Zoey 101".

NOTE: deliberately does NOT set the `korean_name` column. `_enrich_rom` uses
display_name = korean_name when present, which would hide the English. The house
convention keeps it NULL and lets the display name fall out of the stored_name.

Idempotent: a rom already carrying Hangul in its name is skipped.

    cd backend && python3 korean_gba_names.py          # dry run, prints the plan
    cd backend && python3 korean_gba_names.py --apply  # rename + index
"""
import re
import sys

import httpx

from app import db
from app.services import gamelist, name_index, renames, storage, tistory

SESSION = "public"
SYSTEM = "gba"

HANGUL = re.compile(r"[가-힣]")
# "(Korea-patch J-K v20090823 v1.02)" — already parsed into patch_ver, drop it.
PATCH_TAG = re.compile(r"\s*\(Korea-patch[^)]*\)", re.I)
# ...except the part marker, which is the one thing in that tag that identifies
# WHICH rom this is: the Tactics Ogre Gaiden patch shipped as two separate roms
# (Part.A / Part.B), same cart code, same title. They are not duplicates, and
# without this they would collide into "name" and "name (2)".
PART = re.compile(r"\bPart\.?\s*([AB])\b", re.I)

# The blog files these under a name the rom's romaji filename will never reach.
# Same idea as covers_gba.CODE_ALIAS, keyed on the English base instead.
QUERY_ALIAS = {
    "Akumajou Dracula - Circle of the Moon": "Castlevania - Circle of the Moon",
    "Castlevania - Akatsuki no Minuet": "Castlevania - Harmony of Dissonance",
    "Castlevania - Byakuya no Concerto": "Castlevania - Aria of Sorrow",
    "Hoshi no Kirby - Kagami no Daimeikyuu": "Kirby & the Amazing Mirror",
    "Hoshi no Kirby - Yume no Izumi Deluxe": "Kirby - Nightmare in Dream Land",
    "Mario & Luigi RPG": "Mario & Luigi - Superstar Saga",
    "Rockman Zero": "Rockman Zero",
    "Zelda no Densetsu - Fushigi no Boushi": "Zelda no Densetsu - Fushigi no Boushi",
}


def english_base(stored_name: str) -> str:
    """Filename -> the English title, patch tag stripped, part marker removed."""
    stem = stored_name.rsplit(".", 1)[0]
    return re.sub(r"\s+", " ", PATCH_TAG.sub("", stem)).strip()


def part_of(original_name: str) -> str | None:
    """'Part.A' / 'Part.B' if this rom is one half of a split patch, else None."""
    m = PART.search(original_name or "")
    return m.group(1).upper() if m else None


def resolve_all(rows: list[dict], client: httpx.Client) -> list[dict]:
    """Look every rom up on the blog. Pure-ish: no DB writes, no renames."""
    plan = []
    for rom in rows:
        base = english_base(rom["stored_name"])
        query = QUERY_ALIAS.get(base, base)
        hit = tistory.best_match(SYSTEM, query, tistory.search(query, client=client))
        new_name = None
        if hit and hit["confidence"] == "exact":
            composed = gamelist.compose_name(hit["korean"], base)
            part = part_of(rom["original_name"])
            if part:                      # keep the halves apart, and labelled
                composed = f"{composed} Part.{part}"
            new_name = f"{composed}.gba"
        plan.append({"rom": rom, "base": base, "hit": hit, "new_name": new_name})
    return plan


def main() -> None:
    apply = "--apply" in sys.argv
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM roms WHERE session_id = ? AND system_key = ? ORDER BY stored_name",
            (SESSION, SYSTEM)).fetchall()]

    targets = [r for r in rows if not HANGUL.search(r["stored_name"])]
    print(f"{len(rows)} GBA roms, {len(targets)} without a Korean name\n")

    with httpx.Client() as client:
        plan = resolve_all(targets, client)

    exact = [p for p in plan if p["new_name"]]
    fuzzy = [p for p in plan if p["hit"] and not p["new_name"]]
    none_ = [p for p in plan if not p["hit"]]

    for p in exact:
        print(f"  OK    {p['base'][:44]:46} -> {p['new_name']}")
    for p in fuzzy:
        print(f"  FUZZY {p['base'][:44]:46} ?  {p['hit']['korean']}  {tistory._BASE}{p['hit']['url']}")
    for p in none_:
        print(f"  NONE  {p['base']}")
    print(f"\nexact={len(exact)}  fuzzy={len(fuzzy)}  none={len(none_)}")

    if not apply:
        print("\ndry run — pass --apply to rename")
        return

    renamed = 0
    for p in exact:
        rom, new_name = p["rom"], p["new_name"]
        with db.connect() as conn:
            row = conn.execute(
                "SELECT id, system_key, stored_name, rom_path, cover_path FROM roms WHERE id = ?",
                (rom["id"],)).fetchone()
            if not row or row["stored_name"] == new_name:
                continue
            upd = renames.rename_rom(conn, SESSION, dict(row), new_name, suffix_on_clash=True)
            name_index.store(
                conn,
                name_index.hash_file(storage.session_root(SESSION) / upd["rom_path"]),
                SYSTEM,
                upd["stored_name"].rsplit(".", 1)[0],
                "tistory",
                rom["original_name"],
            )
            renamed += 1
    print(f"\nrenamed {renamed}")


if __name__ == "__main__":
    main()
