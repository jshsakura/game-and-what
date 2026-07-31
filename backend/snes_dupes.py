"""Find SNES entries that are the same cartridge twice, and say WHY they differ.

Read-only. It prints a plan and never touches the library — deletions go through
the API (`DELETE /api/sessions/public/roms/<id>`) so the file lands in _trash and
the activity feed can undo it. Run it from /app/backend:

    python3 snes_dupes.py            # grouped report
    python3 snes_dupes.py --json     # same data, for a tool or a review page

The identity of a cart is NOT its filename here: the library is named from two
Korean sources, so the same game arrives twice as '한글 (English)' and as a bare
한글 title. What it IS, is the cart's own header — the internal title, the ROM
size, and the destination byte — which is why this groups on those three and
treats the filename as a label rather than a fact. See docs/SNES_DUPES.md.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from app import db
from app.services import storage

SESSION = "public"

ASCII_ONLY = re.compile(r"^[\x00-\x7f]+$")
PAREN = re.compile(r"\(([^()]*)\)")
# Region/revision markers a dump carries, e.g. '(U)', '[!]', '(V1.1)'.
DUMP_TAG = re.compile(r"\((?:U|E|J|JU|UE|K|KP|F|G|S|I|Ch|UK|A|B|PD|H\d?|M\d|"
                      r"V\d[\d.]*|\d)\)|\[[^\]]*\]", re.I)
# An entry marked this way is NOT a redundant copy — it is the thing the pair
# exists for. A Korean patch needs its original; a hack is its own game.
PATCH = re.compile(r"korea-patch|한글|패치|\(K\)", re.I)
HACK = re.compile(r"\bv\d|\bV\d|베타|beta|hack|데모|demo|프로토|proto|자가제|\+|"
                  r"익스퍼트|expert|competition|컴피티션|\d\.\d", re.I)
# Header titles too generic to identify anything: every Mario World hack says
# SUPER MARIOWORLD, and a stack of Sufami Turbo carts all say ADD-ON BASE CASSETE.
GENERIC = {"SFC", "SFX 1", "SFC 2", "ADD-ON BASE CASSETE", "SUPER MARIOWORLD"}
# Destination byte (header + 0x19) → where the cart was sold. Two dumps of one
# game from different regions are two releases, not a duplicate.
DEST = {0x00: "일본", 0x01: "미국", 0x02: "유럽", 0x03: "스칸디나비아", 0x06: "프랑스",
        0x07: "네덜란드", 0x08: "스페인", 0x09: "독일", 0x0b: "이탈리아", 0x0c: "중국",
        0x0d: "인도네시아", 0x0e: "한국", 0x0f: "공통", 0x10: "캐나다", 0x11: "브라질",
        0x12: "호주"}


def stem(name: str) -> str:
    return re.sub(r"\.(smc|sfc)$", "", name or "", flags=re.I)


def norm(text: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", (text or "").lower())


def english_title(name: str) -> str | None:
    """The English title a curated name carries in parentheses, if any."""
    for g in reversed(PAREN.findall(stem(name))):
        if ASCII_ONLY.match(g) and len(g) > 3 and not DUMP_TAG.fullmatch(f"({g})"):
            return g
    return None


def korean_part(name: str) -> str:
    return norm(PAREN.sub("", stem(name)))


def has_note(name: str) -> bool:
    """Does the name carry one of OUR disambiguation markers — '(원본)',
    '(다른 덤프)'? A Hangul parenthetical is not part of a title; it is a note we
    added to tell a second copy apart, so that entry is by construction the odd
    one out and makes a poor default keeper."""
    return any(re.search(r"[가-힣]", g) for g in PAREN.findall(stem(name)))


def region_of(path: Path) -> str | None:
    """The region the cart declares. LoROM keeps its header at 0x7fc0, HiROM at
    0xffc0; the destination byte sits 0x19 into it."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    for base in (0x7FC0, 0xFFC0):
        blk = data[base:base + 32]
        if len(blk) == 32 and blk[:21].decode("ascii", "ignore").strip() and blk[0x19] in DEST:
            return DEST[blk[0x19]]
    return None


def classify(rows: list[dict]) -> str:
    """Why do these entries differ? patch/hack are intentional pairs; subtitle is
    the same title written out to different lengths; unclear is a name that reads
    like another game entirely (a foreign release name — or a real bootleg)."""
    names = [r["stored_name"] for r in rows]
    if any(PATCH.search(n) for n in names) or any(r["is_korean_patched"] for r in rows):
        return "patch"
    if any(HACK.search(n) for n in names):
        return "hack"
    ks = [korean_part(n) for n in names]
    es = [english_title(n) or "" for n in names]
    same_head = len({k[:6] for k in ks}) == 1 or (all(es) and len({norm(e)[:6] for e in es}) == 1)
    nested = any(a != b and (a in b or b in a) for a in ks for b in ks)
    pairs = [difflib.SequenceMatcher(None, a, b).ratio() for a in ks for b in ks if a != b]
    return "subtitle" if (nested or same_head or (max(pairs) if pairs else 1) >= 0.5) else "unclear"


def scan() -> list[dict]:
    root = storage.session_root(SESSION)
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id,stored_name,rom_path,snes_rom_kb,snes_title,crc32,is_korean_patched,"
            "cover_status,created_at FROM roms WHERE system_key='snes' AND session_id=?",
            (SESSION,))]

    by_title: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if (r["snes_title"] or "").strip():
            by_title[r["snes_title"].strip()].append(r)

    groups = []
    for title, group in sorted(by_title.items()):
        if len(group) < 2 or title in GENERIC:
            continue
        for size in sorted({r["snes_rom_kb"] for r in group}, key=lambda s: s or 0):
            same = [r for r in group if r["snes_rom_kb"] == size]
            if len(same) < 2 or not size:
                continue
            kind = classify(same)
            # Best first: a cover, then a name that carries the English title, then
            # one without a '(다른 덤프)'-style note, then the longer (more
            # informative) one.
            order = sorted(same, key=lambda r: (
                r["cover_status"] != "ok", english_title(r["stored_name"]) is None,
                has_note(r["stored_name"]), -len(stem(r["stored_name"])), r["created_at"]))
            regions = {r["id"]: region_of(root / r["rom_path"]) for r in same}

            # Propose dropping ONE PER REGION at most, and never an entry whose
            # name reads like a different game — a bootleg reskin keeps the host
            # cart's header, so the header alone cannot tell them apart.
            best = korean_part(order[0]["stored_name"])
            kept, rec, caution = set(), {}, set()
            for r in order:
                reg = regions[r["id"]] or f"?{r['id'][:4]}"
                k = korean_part(r["stored_name"])
                like_best = (k in best or best in k
                             or difflib.SequenceMatcher(None, k, best).ratio() >= 0.35)
                if kind in ("subtitle", "unclear") and reg in kept and like_best:
                    rec[r["id"]] = "drop"
                else:
                    rec[r["id"]] = "keep"
                    kept.add(reg)
                    if not like_best and r is not order[0]:
                        caution.add(r["id"])
            groups.append({
                "title": title, "size": size, "kind": kind,
                "one_region": len({v for v in regions.values() if v}) <= 1,
                "rows": [{"id": r["id"], "name": r["stored_name"], "crc": r["crc32"],
                          "cover": r["cover_status"], "region": regions[r["id"]],
                          "recommend": rec[r["id"]], "caution": r["id"] in caution}
                         for r in order],
            })
    return groups


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    groups = scan()
    if args.json:
        print(json.dumps({"groups": groups}, ensure_ascii=False, indent=1))
        return

    kinds = Counter(g["kind"] for g in groups)
    rows = sum(len(g["rows"]) for g in groups)
    drops = sum(1 for g in groups for r in g["rows"] if r["recommend"] == "drop")
    print(f"groups {len(groups)} · rows {rows} · 권장 삭제 {drops}")
    print(f"  {dict(kinds)}  (같은 지역 그룹 {sum(1 for g in groups if g['one_region'])})")
    for g in groups:
        mix = " · ".join(dict.fromkeys(r["region"] or "?" for r in g["rows"]))
        print(f"\n[{g['kind']}] {g['title']} · {g['size']}KB · {mix}")
        for r in g["rows"]:
            mark = "DROP" if r["recommend"] == "drop" else "keep"
            flag = " ⚠확인" if r["caution"] else ""
            print(f"  {mark} {r['name']}  ({r['region'] or '?'}, {r['crc']}, "
                  f"cover={r['cover']}){flag}")


if __name__ == "__main__":
    main()
