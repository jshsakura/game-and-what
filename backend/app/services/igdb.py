"""IGDB v4 cover search (retro platforms). Credentials come from env only.

Used by the in-popup cover "검색기": search a game by name (optionally pinned to
the ROM's system platform) and return cover image URLs to pick from.
"""
from __future__ import annotations

import difflib
import re
import time

import httpx

from .. import config

_BASE = "https://api.igdb.com/v4"
_TOKEN: dict = {"value": None, "exp": 0.0}

# gnw system key -> IGDB platform id(s) (best-effort; unmapped → no platform filter).
# The gnw "nes" core runs Famicom/FDS too, and IGDB files Japan-only carts under
# Famicom (99) / FDS (51), NOT NES (18) — so we must search all three or every
# Famicom-exclusive (e.g. Kid Dracula) comes back empty.
_PLATFORM: dict[str, tuple[int, ...]] = {
    "nes": (18, 99, 51), "gb": (33,), "gbc": (22,), "gg": (35,), "sms": (64,),
    "md": (29,), "sg": (84,), "pce": (86, 128), "col": (68,), "msx": (27,),
    "a2600": (59,), "a7800": (60,), "amstrad": (25,), "mini": (166,), "gw": (307,),
    "ws": (57, 123), "ngp": (119, 120), "wsv": (415,), "lynx": (61,),
}


def _platform_filter(system: str | None) -> str:
    """' & platforms = (a,b)' clause for the system, or '' when unmapped."""
    ids = _PLATFORM.get(system or "")
    return f" & platforms = ({','.join(map(str, ids))})" if ids else ""


async def _token() -> str | None:
    now = time.time()
    if _TOKEN["value"] and _TOKEN["exp"] - 60 > now:
        return _TOKEN["value"]
    cid, sec = config.IGDB_CLIENT_ID, config.IGDB_CLIENT_SECRET
    if not cid or not sec:
        return None
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://id.twitch.tv/oauth2/token",
            params={"client_id": cid, "client_secret": sec,
                    "grant_type": "client_credentials"},
        )
    if resp.status_code != 200:
        return None
    data = resp.json()
    _TOKEN["value"] = data["access_token"]
    _TOKEN["exp"] = now + data.get("expires_in", 3600)
    return _TOKEN["value"]


def _esc(s: str) -> str:
    return s.replace('"', '\\"')


async def search_covers(query: str, system: str | None = None, limit: int = 12) -> dict:
    """Search IGDB for games matching ``query`` that have cover art.

    Returns {available, results:[{name, year, cover_url, thumb_url}]}.
    available=False means no IGDB credentials are configured.
    """
    query = (query or "").strip()
    if not query:
        return {"available": True, "results": []}
    token = await _token()
    if not token:
        return {"available": False, "results": []}

    headers = {"Client-ID": config.IGDB_CLIENT_ID, "Authorization": f"Bearer {token}"}
    where = "where cover != null" + _platform_filter(system) + ";"
    body = (
        f'search "{_esc(query)}"; '
        f"fields name,first_release_date,cover.image_id; {where} limit {min(limit, 20)};"
    )
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{_BASE}/games", headers=headers, content=body)
    except httpx.HTTPError:
        return {"available": True, "results": [], "error": "IGDB 요청 실패"}
    if resp.status_code != 200:
        return {"available": True, "results": [], "error": resp.text[:160]}

    results = []
    for game in resp.json():
        image_id = (game.get("cover") or {}).get("image_id")
        if not image_id:
            continue
        ts = game.get("first_release_date")
        results.append({
            "name": game.get("name"),
            "year": time.gmtime(ts).tm_year if ts else None,
            "cover_url": f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg",
            "thumb_url": f"https://images.igdb.com/igdb/image/upload/t_cover_small/{image_id}.jpg",
        })
    return {"available": True, "results": results}


_HANGUL = re.compile(r"[가-힣]")


async def resolve(query: str, system: str | None = None) -> dict | None:
    """Best IGDB match for a title → {name, korean, cover_url}. `korean` is the
    first alternative_name containing Hangul (often empty). None if no key/match."""
    query = (query or "").strip()
    if not query:
        return None
    token = await _token()
    if not token:
        return None
    headers = {"Client-ID": config.IGDB_CLIENT_ID, "Authorization": f"Bearer {token}"}
    pf = _platform_filter(system)
    where = (f" where{pf[2:]};" if pf else ";")   # strip the leading ' & '
    body = (
        f'search "{_esc(query)}"; '
        f"fields name,cover.image_id,alternative_names.name; limit 1;{where}"
    )
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{_BASE}/games", headers=headers, content=body)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200 or not resp.json():
        return None
    game = resp.json()[0]
    image_id = (game.get("cover") or {}).get("image_id")
    korean = next((a["name"] for a in (game.get("alternative_names") or [])
                   if _HANGUL.search(a.get("name", ""))), None)
    return {
        "name": game.get("name"),
        "korean": korean,
        "cover_url": f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg" if image_id else None,
    }


_RATING_FIELDS = ("name,total_rating,total_rating_count,aggregated_rating,"
                  "rating,alternative_names.name")


def _match_key(s: str) -> str:
    """Normalize a title for similarity matching: drop region/edition/() tags +
    punctuation, lowercase (keep Hangul)."""
    s = re.sub(r"\([^)]*\)", " ", s or "")
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = re.sub(r"[^a-z0-9가-힣]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


async def fetch_rating(query: str, system: str | None = None) -> dict | None:
    """Best IGDB rating for a title on its platform (nes also covers Famicom/FDS).
    Returns {score:int|None, votes:int, name:str, confidence:float} — score=None
    means a confident match but IGDB carries no rating. None = no usable match."""
    query = (query or "").strip()
    if not query:
        return None
    token = await _token()
    if not token:
        return None
    headers = {"Client-ID": config.IGDB_CLIENT_ID, "Authorization": f"Bearer {token}"}
    pf = _platform_filter(system)
    where = (f" where{pf[2:]};" if pf else ";")
    body = f'search "{_esc(query)}"; fields {_RATING_FIELDS}; limit 6;{where}'
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{_BASE}/games", headers=headers, content=body)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200 or not isinstance(resp.json(), list) or not resp.json():
        return None
    qkey = _match_key(query)
    best, best_sim = None, 0.0
    for g in resp.json():
        names = [g.get("name", "")] + [a.get("name", "")
                                       for a in (g.get("alternative_names") or [])]
        sim = max((difflib.SequenceMatcher(None, qkey, _match_key(n)).ratio()
                   for n in names if n), default=0.0)
        if sim > best_sim:
            best, best_sim = g, sim
    if not best or best_sim < 0.5:
        return None
    score = best.get("total_rating") or best.get("aggregated_rating") or best.get("rating")
    return {
        "score": round(score) if score is not None else None,
        "votes": best.get("total_rating_count") or 0,
        "name": best.get("name"),
        "confidence": round(best_sim, 2),
    }
