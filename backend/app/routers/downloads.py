"""Single-file download endpoints.

ROM download  → ZIP(rom + cover) so the set travels together and can be
                unpacked straight onto the SD card root (/roms/… /covers/…).
Video download → the single .avi file.

On-card paths are identical to what the bulk /package endpoint produces so
the two download paths are always consistent.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse

from .. import db
from ..services import storage, video
from .sessions import require_session

router = APIRouter(prefix="/api", tags=["downloads"])


def _require_rom(conn, session_id: str, rom_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM roms WHERE id = ? AND session_id = ?",
        (rom_id, session_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="ROM not found in session")
    return dict(row)


def _require_video(conn, session_id: str, video_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM videos WHERE id = ? AND session_id = ?",
        (video_id, session_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Video not found in session")
    return dict(row)


@router.get("/sessions/{session_id}/roms/{rom_id}/download")
def download_rom(session_id: str, rom_id: str) -> Response:
    """Download a ROM + its cover as a ZIP ready to unpack onto the SD card.

    Archive layout mirrors /roms/<dir>/<name>.<ext> and /covers/<dir>/<name>.img
    — identical to the bulk /package endpoint.
    """
    with db.connect() as conn:
        require_session(conn, session_id)
        rom = _require_rom(conn, session_id, rom_id)

    session_root = storage.session_root(session_id)
    rom_rel: str = rom["rom_path"]        # e.g. "roms/nes/Game.nes"
    cover_rel: str | None = rom["cover_path"]  # e.g. "covers/nes/Game.img" or None
    is_homebrew = Path(rom_rel).parts[1:2] == ("homebrew",) if "/" in rom_rel else False

    buf = io.BytesIO()
    added = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Primary ROM file — but a homebrew .bin app lives in the firmware (not on
        # SD), so skip it unless the user opted it in (matches the SD package rule).
        rom_abs = session_root / rom_rel
        skip_primary = is_homebrew and rom_rel.lower().endswith(".bin") and not rom["sd_include"]
        if rom_abs.exists() and not skip_primary:
            zf.write(rom_abs, arcname=rom_rel); added += 1
        # Extra files attached to the card (e.g. smw_assets.dat) — always travel.
        for ef in json.loads(rom["extra_files"] or "[]"):
            ef_rel = f"{Path(rom_rel).parent}/{ef['name']}"
            ef_abs = session_root / ef_rel
            if ef_abs.exists():
                zf.write(ef_abs, arcname=ef_rel); added += 1
        # Cover ships alongside (separate name from the data file).
        if cover_rel:
            cover_abs = session_root / cover_rel
            if cover_abs.exists():
                zf.write(cover_abs, arcname=cover_rel); added += 1

    if added == 0:
        raise HTTPException(status_code=404, detail="Nothing to download for this ROM")

    stem = Path(rom["stored_name"]).stem
    filename = f"{stem}.zip"
    # Korean (non-latin-1) names crash a plain filename="…" header → RFC 5987:
    # ASCII fallback + UTF-8 filename* (HTTP headers are latin-1 only).
    ascii_name = filename.encode("ascii", "ignore").decode().strip() or "rom.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition":
                 f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/sessions/{session_id}/roms/{rom_id}/rom")
def serve_rom(session_id: str, rom_id: str) -> Response:
    """Serve the raw ROM bytes (no zip, no cover) for in-browser emulation.

    Unlike /download (which bundles a SD-ready zip), the web emulator needs the
    bare ROM file. Inline disposition + permissive caching so the core can fetch
    it directly as EJS/Nostalgist gameUrl.
    """
    with db.connect() as conn:
        require_session(conn, session_id)
        rom = _require_rom(conn, session_id, rom_id)

    abs_path = storage.session_root(session_id) / rom["rom_path"]
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="ROM file missing from disk")

    name = Path(rom["stored_name"]).name
    ascii_name = name.encode("ascii", "ignore").decode() or "game.bin"
    return Response(
        content=abs_path.read_bytes(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition":
                f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}",
            "Cache-Control": "public, max-age=86400",
        },
    )


@router.get("/sessions/{session_id}/roms/{rom_id}/cdfile")
def serve_cd_track(session_id: str, rom_id: str, name: str) -> Response:
    """Serve one track/data file from a CD game's folder, for in-browser CD play.

    Folder-per-game CD entries store the .cue + track .bin/.iso next to each other
    (rom_path's parent). The web emulator fetches the .cue via /rom and each track
    here, then hands the whole set to the core. `name` is a bare filename (basename
    only) resolved inside the rom's own folder — no traversal."""
    with db.connect() as conn:
        require_session(conn, session_id)
        rom = _require_rom(conn, session_id, rom_id)

    folder = (storage.session_root(session_id) / rom["rom_path"]).parent
    target = folder / Path(name).name           # basename only → can't escape the folder
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Track file missing from disk")

    return Response(
        content=target.read_bytes(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(target.name)}",
            "Cache-Control": "public, max-age=86400",
        },
    )


@router.get("/sessions/{session_id}/videos/{video_id}/download")
def download_video(session_id: str, video_id: str) -> Response:
    """Download the encoded .avi for a video entry."""
    with db.connect() as conn:
        require_session(conn, session_id)
        video = _require_video(conn, session_id, video_id)

    if video["status"] != "ok" or not video["avi_path"]:
        raise HTTPException(status_code=404, detail="Video not ready yet")

    session_root = storage.session_root(session_id)
    avi_abs = session_root / video["avi_path"]

    if not avi_abs.exists():
        raise HTTPException(status_code=404, detail="AVI file missing from disk")

    def _iter_file(path: Path, chunk: int = 1 << 20):
        with path.open("rb") as fh:
            while True:
                data = fh.read(chunk)
                if not data:
                    break
                yield data

    return StreamingResponse(
        _iter_file(avi_abs),
        media_type="video/avi",
        headers={
            "Content-Disposition":
                f"attachment; filename=\"{(video['avi_name'].encode('ascii','ignore').decode().strip() or 'video.avi')}\"; "
                f"filename*=UTF-8''{quote(video['avi_name'])}",
            "Content-Length": str(avi_abs.stat().st_size),
        },
    )


@router.get("/sessions/{session_id}/music/{music_id}/download")
def download_music(session_id: str, music_id: str) -> Response:
    """Download a stored MP3 track."""
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            "SELECT * FROM music WHERE id = ? AND session_id = ?", (music_id, session_id)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Music not found in session")
        music = dict(row)

    abs_path = storage.session_root(session_id) / music["music_path"]
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="MP3 file missing from disk")

    name = music["original_name"]
    ascii_name = name.encode("ascii", "ignore").decode() or music["stored_name"]
    return Response(
        content=abs_path.read_bytes(),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition":
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}",
        },
    )


@router.get("/sessions/{session_id}/music/{music_id}/stream")
def music_stream(session_id: str, music_id: str) -> Response:
    """Stream an MP3 for the in-app player. FileResponse honors Range requests so
    the audio element can seek/scrub (the download endpoint can't)."""
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            "SELECT * FROM music WHERE id = ? AND session_id = ?", (music_id, session_id)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        music = dict(row)
    mp3 = storage.session_root(session_id) / music["music_path"]
    if not mp3.exists():
        raise HTTPException(status_code=404, detail="mp3 missing")
    return FileResponse(mp3, media_type="audio/mpeg")


@router.get("/sessions/{session_id}/videos/{video_id}/thumb")
async def video_thumb(session_id: str, video_id: str) -> Response:
    """16:9 thumbnail (built+cached from the .avi on first request)."""
    with db.connect() as conn:
        require_session(conn, session_id)
        v = _require_video(conn, session_id, video_id)
    thumb = storage.media_thumb_path(session_id, video_id)
    if not thumb.exists():
        if v["status"] != "ok" or not v["avi_path"]:
            raise HTTPException(status_code=404, detail="no thumbnail")
        avi = storage.session_root(session_id) / v["avi_path"]
        if not avi.exists():
            raise HTTPException(status_code=404, detail="avi missing")
        try:
            await video.make_thumb(avi, thumb)
        except video.VideoEncodeError:
            raise HTTPException(status_code=404, detail="thumbnail failed")
    return FileResponse(thumb, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/sessions/{session_id}/videos/{video_id}/preview")
async def video_preview(session_id: str, video_id: str) -> Response:
    """Browser-playable .mp4 preview (built+cached from the .avi on first request).
    FileResponse honors Range requests so the player can seek."""
    with db.connect() as conn:
        require_session(conn, session_id)
        v = _require_video(conn, session_id, video_id)
    prev = storage.media_preview_path(session_id, video_id)
    if not prev.exists():
        if v["status"] != "ok" or not v["avi_path"]:
            raise HTTPException(status_code=404, detail="not ready")
        avi = storage.session_root(session_id) / v["avi_path"]
        if not avi.exists():
            raise HTTPException(status_code=404, detail="avi missing")
        try:
            await video.make_web_preview(avi, prev)
        except video.VideoEncodeError:
            raise HTTPException(status_code=404, detail="preview failed")
    return FileResponse(prev, media_type="video/mp4")


@router.get("/sessions/{session_id}/music/{music_id}/cover")
async def music_cover(session_id: str, music_id: str) -> Response:
    """Embedded MP3 album art (extracted+cached on first request). 404 if none."""
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            "SELECT * FROM music WHERE id = ? AND session_id = ?", (music_id, session_id)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        music = dict(row)
    cover = storage.music_cover_path(session_id, music_id)
    if not cover.exists():
        mp3 = storage.session_root(session_id) / music["music_path"]
        if not mp3.exists():
            raise HTTPException(status_code=404, detail="mp3 missing")
        try:
            await video.extract_cover(mp3, cover)
        except video.VideoEncodeError:
            raise HTTPException(status_code=404, detail="no cover art")
    return FileResponse(cover, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"})
