"""Video upload → background MJPEG/.avi encode job → /media."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import config, db
from ..services import jobs, storage, video
from .sessions import require_session

router = APIRouter(prefix="/api", tags=["videos"])


async def _run_encode(
    job_id: str, video_id: str, src: Path, dst: Path, session_id: str,
    mode: str = video.DEFAULT_FIT_MODE,
) -> None:
    """Background: encode src -> dst, updating job + DB status."""
    await jobs.update(job_id, status="running", progress=0.05, message="encoding")
    try:
        await video.encode_to_mjpeg_avi(src, dst, mode=mode)
        # web preview (browser-playable .mp4) + square thumbnail, built from the
        # source while it's still here. Non-fatal — the card just falls back to an
        # icon, and the serve endpoints can lazy-build from the .avi later.
        prev = storage.media_preview_path(session_id, video_id)
        thumb = storage.media_thumb_path(session_id, video_id)
        try:
            await video.make_web_preview(src, prev)
            await video.make_thumb(src, thumb)
        except video.VideoEncodeError:
            pass
    except video.VideoEncodeError as exc:
        await jobs.update(job_id, status="failed", message=str(exc))
        with db.connect() as conn:
            conn.execute("UPDATE videos SET status='failed' WHERE id=?", (video_id,))
        return
    finally:
        src.unlink(missing_ok=True)  # drop the original upload, keep the .avi

    rel = storage.relative_to_session(session_id, dst)
    with db.connect() as conn:
        conn.execute(
            "UPDATE videos SET status='ok', avi_path=? WHERE id=?", (rel, video_id)
        )
    await jobs.update(
        job_id, status="done", progress=1.0, message="done",
        result={"video_id": video_id, "avi_path": rel},
    )


@router.post("/sessions/{session_id}/videos")
async def upload_video(
    session_id: str,
    file: UploadFile = File(...),
    file_size: int = Form(0),  # optional client hint, unused for validation
    mode: str = Form(video.DEFAULT_FIT_MODE),  # fit | fill | stretch
) -> dict:
    """Upload one video; returns a job id to poll for encode progress."""
    if mode not in video.FIT_MODES:
        mode = video.DEFAULT_FIT_MODE
    if not video.ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg not installed on server")

    with db.connect() as conn:
        require_session(conn, session_id)

    data = await file.read()
    if len(data) > config.MAX_VIDEO_BYTES:
        raise HTTPException(status_code=413, detail="video too large")

    original = file.filename or "video"
    avi_name = f"{storage.safe_name(Path(original).stem)}.avi"
    src_path = storage.media_dir(session_id) / f".src_{storage.new_id()}"
    dst_path = storage.media_dir(session_id) / avi_name
    storage.write_bytes(src_path, data)

    video_id = storage.new_id()
    job_id = storage.new_id()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO videos (id, session_id, original_name, avi_name, job_id, status)
               VALUES (?,?,?,?,?, 'encoding')""",
            (video_id, session_id, original, avi_name, job_id),
        )
    await jobs.create(job_id, "video_encode")
    asyncio.create_task(_run_encode(job_id, video_id, src_path, dst_path, session_id, mode=mode))

    return {"video_id": video_id, "job_id": job_id, "avi_name": avi_name, "status": "encoding"}
