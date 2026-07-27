"""Music upload → /music. MP3 is played by the firmware's Music app directly
(it reads ID3 tags + album art itself), so there is NO server-side conversion —
we just store the file and include /music in the SD ZIP."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from .. import config, db
from ..services import storage, video
from .sessions import require_session

router = APIRouter(prefix="/api", tags=["music"])


def _store_mp3(session_id: str, original: str, data: bytes) -> dict:
    """Persist MP3 bytes under /music + record the row."""
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty")
    if len(data) > config.MAX_MUSIC_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    stored_name = storage.safe_name(Path(original).stem) + ".mp3"
    dst = storage.music_dir(session_id) / stored_name
    storage.write_bytes(dst, data)
    rel = storage.relative_to_session(session_id, dst)

    music_id = storage.new_id()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO music (id, session_id, original_name, stored_name, music_path, size_bytes)
               VALUES (?,?,?,?,?,?)""",
            (music_id, session_id, original, stored_name, rel, len(data)),
        )
    return {
        "id": music_id,
        "original_name": original,
        "stored_name": stored_name,
        "music_path": rel,
        "size_bytes": len(data),
    }


@router.post("/sessions/{session_id}/music")
async def upload_music(session_id: str, file: UploadFile = File(...)) -> dict:
    """Store an MP3 as-is, OR extract the audio of an uploaded video to MP3 → /music."""
    with db.connect() as conn:
        require_session(conn, session_id)

    original = storage.nfc(file.filename) or "track.mp3"
    suffix = Path(original).suffix.lower()
    data = await file.read()

    if suffix == ".mp3":
        # MP3 → store verbatim (firmware plays it directly).
        item = _store_mp3(session_id, original, data)
    else:
        # Anything else (video / other audio) → extract the audio track to MP3.
        if not video.ffmpeg_available():
            raise HTTPException(status_code=503, detail="Cannot extract audio from video without ffmpeg")
        if not data:
            raise HTTPException(status_code=400, detail="The file is empty")
        if len(data) > config.MAX_VIDEO_BYTES:
            raise HTTPException(status_code=413, detail="File too large")

        music = storage.music_dir(session_id)
        src = music / f".src_{storage.new_id()}{suffix or '.bin'}"
        out = music / f".out_{storage.new_id()}.mp3"
        storage.write_bytes(src, data)
        try:
            await video.extract_mp3(src, out)
            mp3_bytes = out.read_bytes()
        except video.VideoEncodeError as exc:
            raise HTTPException(status_code=502, detail=f"Audio extraction failed: {exc}")
        finally:
            src.unlink(missing_ok=True)
            out.unlink(missing_ok=True)
        stem = Path(original).stem or "track"
        item = _store_mp3(session_id, f"{stem}.mp3", mp3_bytes)

    # Shrink+boost embedded album art for the device's small LCD (no-op if none).
    abs_path = storage.session_root(session_id) / item["music_path"]
    try:
        if await video.optimize_album_art(abs_path):
            item["size_bytes"] = abs_path.stat().st_size
            with db.connect() as conn:
                conn.execute("UPDATE music SET size_bytes=? WHERE id=?", (item["size_bytes"], item["id"]))
            (storage.music_cover_path(session_id, item["id"])).unlink(missing_ok=True)  # drop stale cached cover
    except Exception:
        pass

    return item
