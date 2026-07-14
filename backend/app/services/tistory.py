"""Resolve a Korean game title from the '하이드가 사는 세상' retro archive
(eagleforce.tistory.com), used to fill Korean names for library roms that don't
have one. The blog's search page lists posts titled:

    [SYS] 한글명 / (원어) / English / (지역판)

so we match on BOTH the [SYS] tag (mapped to our system key) AND the English
title — Double Dragon exists on GG/SMS/NES, so the system tag is what keeps a
match honest. Returns a 'confidence':
    'exact' — system tag matches AND an English segment matches the rom exactly
    'fuzzy' — system tag matches, English differs (sequel/subtitle) → still a
              candidate, but flagged so it can be eyeballed before applying.

Network I/O is isolated in search(); parse_results()/best_match() are pure and
unit-tested.
"""
from __future__ import annotations

import html as html_lib
import re
from urllib.parse import quote

import httpx

from . import romtag

# blog [SYS] tag (lowercased) -> our system key
SYSMAP = {
    "col": "col", "msx": "msx", "gg": "gg", "sms": "sms", "nes": "nes",
    "fc": "nes", "famicom": "nes", "md": "md", "pce": "pce", "pce-cd": "pce",
    "gb": "gb", "gbc": "gbc", "gamegear": "gg", "sg": "sg", "sg-1000": "sg",
    "gba": "gba",
}

_ANCHOR = re.compile(r'<a[^>]+href="(/\d+)"[^>]*>(.*?)</a>', re.S)
_HANGUL = re.compile(r"[가-힣]")
_BASE = "https://eagleforce.tistory.com"
_UA = {"User-Agent": "Mozilla/5.0 (gnw-retro-manager)"}


def _norm(s: str) -> str:
    s = re.sub(r"\s*[(\[].*?[)\]]", "", s or "")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def clean_query(stored_name: str) -> str:
    """Filename -> blog search term: drop extension, region tag and '~ alt'."""
    stem = stored_name.rsplit(".", 1)[0] if "." in stored_name else stored_name
    _, stem = romtag.extract_region(stem)
    stem = re.sub(r"\s*~.*$", "", stem)             # drop '~ alternate title'
    return re.sub(r"\s+", " ", stem).strip()


def first_alias(korean: str) -> str:
    """A post may list aliases ('바람돌이 소닉, 소닉 더 헷지혹'); the first is the
    real Korean release name (e.g. Samsung's '바람돌이 소닉')."""
    return re.split(r"[,/]", korean)[0].strip()


def parse_results(html_text: str) -> list[dict]:
    """Parse a blog search page into [{sys, korean, engs, url}] (pure)."""
    out: list[dict] = []
    seen: set[str] = set()
    for href, inner in _ANCHOR.findall(html_text):
        if href in seen:
            continue
        seen.add(href)
        txt = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", inner))).strip()
        m = re.match(r"\[([^\]]+)\]\s*(.+)", txt)
        if not m:
            continue
        segs = [s.strip() for s in m.group(2).split("/") if s.strip()]
        korean = next((s for s in segs if _HANGUL.search(s)), None)
        engs = [s for s in segs if re.search(r"[a-z]", s, re.I) and not _HANGUL.search(s)]
        out.append({"sys": SYSMAP.get(m.group(1).strip().lower()),
                    "korean": korean, "engs": engs, "url": href})
    return out


def _similarity(a: str, b: str) -> int:
    """Cheap normalized-string closeness: common-prefix length, plus a containment
    bonus so 'bareknuckle' scores high against 'bareknuckleii'."""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    if a and b and (a in b or b in a):
        n += min(len(a), len(b))
    return n


# A fuzzy candidate must share at least this much with the query, so an unrelated
# same-system post (Double Dragon for a 'Bare Knuckle' search) is never picked.
_FUZZY_MIN = 3


def best_match(system: str, stored_name: str, results: list[dict]) -> dict | None:
    """Pick the best post for this rom (pure). Exact (system + English) wins;
    otherwise the closest same-system candidate (English-similarity) as 'fuzzy'."""
    key = _norm(clean_query(stored_name))
    cands = [r for r in results if r["sys"] == system and r["korean"]]
    for r in cands:
        if any(_norm(e) == key for e in r["engs"]):
            return {"korean": first_alias(r["korean"]), "confidence": "exact", "url": r["url"]}

    best, best_score = None, 0
    for r in cands:
        score = max((_similarity(_norm(e), key) for e in r["engs"]), default=0)
        if score > best_score:
            best, best_score = r, score
    if best and best_score >= _FUZZY_MIN:
        return {"korean": first_alias(best["korean"]), "confidence": "fuzzy", "url": best["url"]}
    return None


# tiny per-process cache so repeated queries in one run don't refetch
_CACHE: dict[str, list[dict]] = {}


def search(query: str, *, client: httpx.Client | None = None) -> list[dict]:
    """Fetch + parse the blog search page for `query`. Network errors -> []."""
    if query in _CACHE:
        return _CACHE[query]
    url = f"{_BASE}/search/{quote(query)}"
    try:
        get = client.get if client else httpx.get
        r = get(url, timeout=20, follow_redirects=True, headers=_UA)
        results = parse_results(r.text) if r.status_code == 200 else []
    except httpx.HTTPError:
        results = []
    _CACHE[query] = results
    return results


def resolve(system: str, stored_name: str, *, client: httpx.Client | None = None) -> dict | None:
    """Best-effort Korean-title match for one rom, or None."""
    return best_match(system, stored_name, search(clean_query(stored_name), client=client))
