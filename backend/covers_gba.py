"""One-off: fill in the GBA covers from libretro-thumbnails.

Run in-process rather than through the API: the deployed container is built from
an older image that doesn't know the `gba` system yet, so its cover endpoints
500 on it (same as the Virtual Boy import). Once the new image ships, the normal
autocover/cover-search UI covers this system like any other.

MATCH ON THE CART HEADER, NOT THE FILENAME. Most of this library is named in
Korean ("포켓몬스터 리프그린1.1.gba"), and fuzzy-matching that text against
libretro's English boxart filenames returns confident nonsense — it paired both
Pokémon FireRed and LeafGreen with "Zoey 101". Every GBA cart instead carries a
4-char game code at 0xAC, and scripts/gba_idle_loop_db.json already maps that
code to the game's English title. So: code → title → an EXACT normalized match
against the boxart list. Anything that doesn't match exactly is left coverless
for the cover-search UI rather than guessed at.
"""
import asyncio
import json
import re
from pathlib import Path

from app import db
from app.routers.covers import _render_cover, _save_cover, _update_cover_db
from app.services import artfetch, libretro, storage

SESSION = "public"
SYSTEM = "gba"
REPO_SLUG = "Nintendo_-_Game_Boy_Advance"

GAME_CODE_OFFSET = 0xAC
FIXED_BYTE_OFFSET = 0xB2
FIXED_BYTE_VALUE = 0x96
HEADER_LENGTH = 0xC0

DB_PATH = Path(__file__).resolve().parent.parent / "scripts" / "gba_idle_loop_db.json"

# Korean-only names whose game sits under a title no amount of normalizing will
# reach — a different regional name (Screw Breaker = Drill Dozer, Akumajou
# Dracula = Castlevania) or one our idle-loop table spells differently.
CODE_ALIAS = {
    "BPYP": "Prince of Persia - The Sands of Time",
    "V49J": "Screw Breaker - Goushin DoriRureRo",
    "AA2C": "Super Mario Advance 2 - Super Mario World",
    "ADKP": "Donald Duck Advance",
    "AX4J": "Super Mario Advance 4 - Super Mario 3 + Mario Brothers",
    "AZ8E": "Super Puzzle Fighter II",
    "AAMJ": "Akumajou Dracula - Circle of the Moon",
}


def normalize(title: str) -> str:
    """Fold a title to a comparable key: drop region/revision parens, punctuation."""
    title = re.sub(r"\.(png|jpg)$", "", title, flags=re.I)
    title = re.sub(r"\([^()]*\)", " ", title)      # (USA), (En,Fr,De), (Rev 1)
    title = re.sub(r"\[[^\[\]]*\]", " ", title)    # [!]
    title = title.replace("&", " and ")
    title = re.sub(r"[^a-z0-9]+", " ", title.lower())
    return " ".join(title.split())


def game_code(path: Path) -> str | None:
    header = path.open("rb").read(HEADER_LENGTH)
    if len(header) < HEADER_LENGTH or header[FIXED_BYTE_OFFSET] != FIXED_BYTE_VALUE:
        return None
    return header[GAME_CODE_OFFSET:GAME_CODE_OFFSET + 4].decode("ascii", "replace")


def english_titles() -> dict[str, list[str]]:
    """game_code → candidate English titles, from the merged idle-loop database."""
    out: dict[str, list[str]] = {}
    for row in json.loads(DB_PATH.read_text(encoding="utf-8")):
        names = [n for n in (row.get("title"), row.get("header_title")) if n]
        if names:
            out[row["game_code"]] = names
    return out


def filename_title(stored_name: str) -> str | None:
    """The English title the library keeps in the last (...) group of a Korean name."""
    stem = stored_name.rsplit(".", 1)[0]
    for group in reversed(re.findall(r"\(([^()]+)\)", stem)):
        g = group.strip()
        # region/revision tags are not titles
        if re.fullmatch(r"[UEJKF]|\d+|v?\d[\d.]*|[A-Z]{1,3}\d*", g):
            continue
        return g
    return None


def squash(title: str) -> str:
    return normalize(title).replace(" ", "")


def find_boxart(cands: list[str], index: dict[str, str]) -> str | None:
    """Match a title to a boxart, tightly. Three passes, each still unambiguous:
    exact; then the title as a prefix of a longer official name ("Pokemon Fire Red"
    → "Pokemon - FireRed Version"); then every query word present with barely any
    extra. A shorter boxart name never matches a longer query, which is what keeps
    "Pokemon Ruby" off the bare "Pokemon" art."""
    for c in cands:
        if normalize(c) in index:
            return index[normalize(c)]

    for c in cands:
        q = squash(c)
        if len(q) < 6:
            continue
        hits = [f for k, f in index.items()
                if squash(k).startswith(q) and len(squash(k)) - len(q) <= 12]
        if len(hits) == 1:
            return hits[0]

    for c in cands:
        qt = set(normalize(c).split())
        if len(qt) < 2:
            continue
        hits = [f for k, f in index.items()
                if qt <= set(k.split()) and len(set(k.split())) - len(qt) <= 2]
        if len(hits) == 1:
            return hits[0]
    return None


async def main() -> None:
    titles = english_titles()
    files = await libretro._boxart_files(REPO_SLUG)
    if not files:
        raise SystemExit("could not list libretro boxarts")
    index: dict[str, str] = {}
    for f in files:
        index.setdefault(normalize(f), f)
    print(f"libretro boxarts: {len(files)} files, {len(index)} distinct titles")

    root = storage.session_root(SESSION)
    with db.connect() as conn:
        roms = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM roms WHERE session_id=? AND system_key=? AND cover_status != 'ok'",
                (SESSION, SYSTEM),
            )
        ]

    ok = 0
    unmatched: list[tuple[str, str]] = []
    for rom in roms:
        code = game_code(root / rom["rom_path"])
        # The English title the library already carries beats anything derived from
        # the code, so try it first.
        cands = [c for c in [CODE_ALIAS.get(code or ""), filename_title(rom["stored_name"])] if c]
        cands += titles.get(code or "", [])
        hit = find_boxart(cands, index)
        if not hit:
            unmatched.append((code or "????", rom["stored_name"]))
            continue

        url = libretro.boxart_url(REPO_SLUG, hit) if hasattr(libretro, "boxart_url") else (
            f"https://raw.githubusercontent.com/libretro-thumbnails/{REPO_SLUG}"
            f"/master/Named_Boxarts/{hit}"
        )
        raw = await artfetch.fetch_image(url)
        if not raw:
            unmatched.append((code or "????", rom["stored_name"] + "  (fetch failed)"))
            continue

        cover_bytes = _render_cover(rom, raw)
        cover_rel = _save_cover(SESSION, rom, cover_bytes, raw)
        with db.connect() as conn:
            _update_cover_db(conn, rom["id"], cover_rel, "ok", "libretro")
        print(f"  [ok] {code}  {rom['stored_name'][:34]:<36} ←  {hit}")
        ok += 1

    print(f"\ncovers: {ok} set, {len(unmatched)} unmatched")
    for code, name in unmatched:
        print(f"  [no match] {code}  {name}")


if __name__ == "__main__":
    asyncio.run(main())
