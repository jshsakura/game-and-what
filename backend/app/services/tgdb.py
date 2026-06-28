"""TheGamesDB (thegamesdb.net) cover lookup — public API key, instant, no approval.

Used as a cover fallback after IGDB. Has a monthly request quota, so callers
should hit it only for ROMs still missing a cover (not force-refresh everything).
"""
from __future__ import annotations

import httpx

from .. import config

_BASE = "https://api.thegamesdb.net/v1"
_TIMEOUT = httpx.Timeout(15.0)

# our system key -> TheGamesDB platform id (verified against /Platforms).
# Systems without a reliable TGDB platform (tama, mini, homebrew, pico8) are
# omitted → we search without a platform filter for those.
_PLATFORM: dict[str, int] = {
    "nes": 7, "gb": 4, "gbc": 41, "gg": 20, "sms": 35, "md": 18, "sg": 4949,
    "pce": 34, "col": 31, "msx": 4929, "a2600": 22, "a7800": 27,
    "amstrad": 4914, "wsv": 4959, "gw": 4950, "lynx": 4924,
}


def available() -> bool:
    return bool(config.TGDB_API_KEY)


async def cover_url(name: str, system_key: str) -> str | None:
    """First front box-art URL for `name` on the given system, or None.
    Never raises — a miss/network error just returns None.

    Unverified (returns whatever game ranks first); for auto-fill prefer
    ``cover_candidates`` so the title can be matched before use."""
    cands = await cover_candidates(name, system_key)
    return cands[0][1] if cands else None


async def _request(name: str, system_key: str) -> tuple[int, list[tuple[str, str]]]:
    """Low-level call → (http_status, candidates). status 0 = network/parse error,
    429 = monthly quota exhausted. Never raises."""
    if not config.TGDB_API_KEY or not name.strip():
        return (0, [])
    params = {
        "apikey": config.TGDB_API_KEY,
        "name": name,
        "include": "boxart",
        "fields": "game_title",
    }
    pid = _PLATFORM.get(system_key)
    if pid:
        params["filter[platform]"] = pid
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE}/Games/ByGameName", params=params)
        if resp.status_code != 200:
            return (resp.status_code, [])
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return (0, [])

    games = (data.get("data") or {}).get("games") or []
    boxart = (data.get("include") or {}).get("boxart") or {}
    base = (boxart.get("base_url") or {}).get("original") or ""
    images = boxart.get("data") or {}
    if not games or not base:
        return (200, [])
    out: list[tuple[str, str]] = []
    for game in games:
        gid = str(game.get("id"))
        title = game.get("game_title") or ""
        for img in images.get(gid, []):
            if img.get("type") == "boxart" and img.get("side", "front") == "front":
                fn = img.get("filename")
                if fn:
                    out.append((title, base + fn))
                    break
    return (200, out)


async def cover_candidates(name: str, system_key: str) -> list[tuple[str, str]]:
    """(game_title, front_boxart_url) pairs in TGDB best-match order, so the caller
    can verify the title actually matches before using a cover. Never raises."""
    _, out = await _request(name, system_key)
    return out


async def search(name: str, system_key: str) -> dict:
    """Interactive search: candidates plus a quota flag so the UI can tell the user
    when TheGamesDB's monthly allowance is exhausted (HTTP 429) vs a genuine miss."""
    status, out = await _request(name, system_key)
    return {"candidates": out, "quota_exceeded": status == 429}
