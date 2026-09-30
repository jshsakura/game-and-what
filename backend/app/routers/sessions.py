"""Session lifecycle + library listing. No login (MVP): a session == a workspace."""
from __future__ import annotations

import zlib
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictBool
from ..systems import get_system

from .. import config, db
from ..services import romtag, storage

router = APIRouter(prefix="/api", tags=["sessions"])


def require_korean_mode() -> None:
    """Block Korea-specific endpoints when the deploy isn't in Korean mode
    (GNW_KOREAN_MODE). Keeps the international/public image free of 한글 features."""
    if not config.KOREAN_MODE:
        raise HTTPException(status_code=403, detail="This feature is only available in Korean mode")


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
    - cover_ver: cache-bust token for the cover URL (see _cover_ver).
    - size_bytes: the ROM file size (CUE + all tracks for CD games), so the UI can count/preview what a size-capped
      SD selection would actually contain without asking the server per keystroke."""
    if r.get("korean_name"):
        display = r["korean_name"]
    else:
        _, cleaned = romtag.extract_region(r.get("stored_name") or "")
        stem = cleaned.rsplit(".", 1)[0] if "." in cleaned else cleaned
        display = stem.strip() or (r.get("stored_name") or "")
    r["display_name"] = display
    r["display_region"] = "Korea" if r.get("is_korean_patched") else r.get("region")
    r["cover_ver"] = _cover_ver(session_id, r)
    try:
        r["size_bytes"] = (storage.session_root(session_id) / r["rom_path"]).stat().st_size
    except OSError:
        r["size_bytes"] = None
    if r.get("system_key") in {"segacd", "pcecd"} or r.get("extra_files"):
        r["primary_size_bytes"] = r["size_bytes"]
        primary = storage.session_root(session_id) / r["rom_path"]
        files = [{"name": primary.name, "size": r["primary_size_bytes"]}]
        try:
            extra = json.loads(r.get("extra_files") or "[]")
        except (ValueError, TypeError):
            extra = []
        seen = {primary.name}
        for item in extra if isinstance(extra, list) else []:
            name = item.get("name") if isinstance(item, dict) else None
            if not name or name in seen or Path(name).name != name or "\\" in name:
                continue
            seen.add(name)
            try:
                size = (primary.parent / name).stat().st_size
            except OSError:
                size = None
            files.append({"name": name, "size": size})
        r["rom_files"] = files
        r["size_bytes"] = sum(f["size"] for f in files) if all(f["size"] is not None for f in files) else None
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
def get_library(session_id: str, compact: bool = False) -> dict:
    """All ROMs, videos, music and clock backgrounds stored in this session."""
    with db.connect() as conn:
        require_session(conn, session_id)
        roms = [
            _enrich_rom(dict(r), session_id)
            for r in conn.execute(
                "SELECT * FROM roms WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        ]
        hidden_systems = [r[0] for r in conn.execute(
            "SELECT system_key FROM hidden_systems WHERE session_id = ? ORDER BY system_key",
            (session_id,))]
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
        clock_files = [
            dict(r)
            for r in conn.execute(
                # rowid breaks the tie: a batch of album photos (or convert,
                # tweak the crop, convert again) lands in the same second, and
                # created_at alone would let their order flip between reloads.
                "SELECT * FROM clock_files WHERE session_id = ? ORDER BY created_at DESC, rowid DESC",
                (session_id,),
            ).fetchall()
        ]
    result = {"session_id": session_id, "roms": roms, "videos": videos, "music": music,
              "clock_files": clock_files, "hidden_systems": hidden_systems}
    if compact:
        # Rich facts are already fetched by the detail popup's igdb-meta endpoint.
        # Keep list facts/flags/sizes, but avoid sending every game's full metadata.
        result["roms"] = [{k: v for k, v in r.items() if k != "igdb_meta" and v is not None}
                          for r in roms]
        return JSONResponse(result)
    return result


class SystemVisibility(BaseModel):
    hidden: StrictBool


@router.patch("/sessions/{session_id}/systems/{system_key}/visibility")
def set_system_visibility(session_id: str, system_key: str, body: SystemVisibility) -> dict:
    try:
        get_system(system_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown platform")
    with db.connect() as conn:
        require_session(conn, session_id)
        if body.hidden:
            conn.execute("INSERT OR IGNORE INTO hidden_systems VALUES (?, ?)",
                         (session_id, system_key))
        else:
            conn.execute("DELETE FROM hidden_systems WHERE session_id = ? AND system_key = ?",
                         (session_id, system_key))
        hidden = [r[0] for r in conn.execute(
            "SELECT system_key FROM hidden_systems WHERE session_id = ? ORDER BY system_key",
            (session_id,))]
    return {"hidden_systems": hidden}
