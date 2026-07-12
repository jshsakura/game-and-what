"""Session lifecycle + library listing. No login (MVP): a session == a workspace."""
from __future__ import annotations

import zlib

from fastapi import APIRouter, HTTPException

from .. import config, db
from ..services import romtag, storage

router = APIRouter(prefix="/api", tags=["sessions"])


def require_korean_mode() -> None:
    """Block Korea-specific endpoints when the deploy isn't in Korean mode
    (GNW_KOREAN_MODE). Keeps the international/public image free of 한글 features."""
    if not config.KOREAN_MODE:
        raise HTTPException(status_code=403, detail="한국어 모드에서만 사용할 수 있는 기능입니다")


def require_experimental_mode() -> None:
    """Block fork-firmware-only endpoints (media/music/clock converters) when the
    deploy tracks the upstream sylverb firmware only (GNW_EXPERIMENTAL_MODE off)."""
    if not config.EXPERIMENTAL_MODE:
        raise HTTPException(
            status_code=403,
            detail="This feature needs the fork firmware — enable GNW_EXPERIMENTAL_MODE",
        )


def require_system_enabled(system) -> None:
    """Reject uploads for fork-only (experimental) systems on an official deploy."""
    if system.experimental and not config.EXPERIMENTAL_MODE:
        raise HTTPException(
            status_code=403,
            detail=f"'{system.name}' is not supported by the upstream firmware — enable GNW_EXPERIMENTAL_MODE",
        )


def _cover_ver(session_id: str, r: dict) -> str:
    """A short token the client appends to the cover URL so it refetches the
    moment the cover CHANGES — and reuses the browser cache when it doesn't.
    Must move on every visible change: the flag is rendered live from cover_flag
    (no file write), the crop re-renders the display, and a new fetch rewrites
    the .img — so fold all three plus the .img mtime into the token."""
    mtime = 0
    cover_path = r.get("cover_path")
    if cover_path:
        try:
            mtime = int((storage.session_root(session_id) / cover_path).stat().st_mtime)
        except OSError:
            mtime = 0
    key = f"{r.get('cover_flag') or ''}|{r.get('crop_box') or ''}|{r.get('cover_status') or ''}|{mtime}"
    return f"{zlib.crc32(key.encode()):08x}"


def _enrich_rom(r: dict, session_id: str) -> dict:
    """Add derived display fields without touching stored files:
    - display_name: the clean title (Korean name if present, else the filename
      with its region tag + extension stripped) — '(USA, Europe)' etc. live in
      the `region` column now, not the shown name.
    - display_region: the region you actually PLAY in. A Japanese dump with a
      Korean patch reads as 'Korea' (play_lang ko), never 'Japan'.
    - cover_ver: cache-bust token for the cover URL (see _cover_ver)."""
    if r.get("korean_name"):
        display = r["korean_name"]
    else:
        _, cleaned = romtag.extract_region(r.get("stored_name") or "")
        stem = cleaned.rsplit(".", 1)[0] if "." in cleaned else cleaned
        display = stem.strip() or (r.get("stored_name") or "")
    r["display_name"] = display
    r["display_region"] = "Korea" if r.get("is_korean_patched") else r.get("region")
    r["cover_ver"] = _cover_ver(session_id, r)
    return r


@router.post("/sessions")
def create_session(label: str | None = None) -> dict:
    """Create a persistent workspace; the client stores the returned id."""
    session_id = storage.new_id()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sessions (id, label) VALUES (?, ?)", (session_id, label)
        )
    return {"session_id": session_id, "label": label}


def require_session(conn, session_id: str) -> None:
    row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown session")


@router.get("/sessions/{session_id}/library")
def get_library(session_id: str) -> dict:
    """All ROMs and videos stored in this session."""
    with db.connect() as conn:
        require_session(conn, session_id)
        roms = [
            _enrich_rom(dict(r), session_id)
            for r in conn.execute(
                "SELECT * FROM roms WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        ]
        videos = []
        for r in conn.execute(
            # only finished encodes — in-progress/failed ones aren't playable and
            # would break the MEDIA grid (no .avi yet).
            "SELECT * FROM videos WHERE session_id = ? AND status = 'ok' "
            "ORDER BY created_at DESC",
            (session_id,),
        ).fetchall():
            v = dict(r)
            try:
                v["size_bytes"] = (
                    (storage.session_root(session_id) / v["avi_path"]).stat().st_size
                    if v.get("avi_path") else None
                )
            except OSError:
                v["size_bytes"] = None
            videos.append(v)
        music = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM music WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        ]
    return {"session_id": session_id, "roms": roms, "videos": videos, "music": music}
