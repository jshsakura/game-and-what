"""Clock background: any image/video → a 320×240 /clock/bg.gif for download.

Stateless — nothing is stored server-side. The user converts a source, downloads
the resulting bg.gif, and drops it into /clock/ on the SD card (the firmware's
Clock app reads /clock/bg.gif). The LCD is 320×240 and the clock scale-fills, so
a larger source only wastes bytes; the encoder pins the output to 320×240.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .. import config
from ..services import storage, video

router = APIRouter(prefix="/api", tags=["clock"])


@router.post("/clock/background")
async def clock_background(
    file: UploadFile = File(...),
    mode: str = Form(video.DEFAULT_FIT_MODE),  # fit (letterbox) | fill (crop) | stretch
) -> FileResponse:
    """Convert an uploaded image or video into a clock-ready bg.gif and return it
    as a download. A still image becomes a 1-frame static background; a video/GIF
    is length-capped and loops on-device. The temp workspace is removed once the
    response has been sent."""
    if mode not in video.FIT_MODES:
        mode = video.DEFAULT_FIT_MODE
    if not video.ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg is not installed on the server")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(data) > config.MAX_VIDEO_BYTES:
        raise HTTPException(status_code=413, detail="file too large")

    work = Path(tempfile.mkdtemp(prefix="clockbg_"))
    src = work / f"src_{storage.safe_name(Path(file.filename or 'input').name)}"
    out = work / "bg.gif"
    storage.write_bytes(src, data)

    try:
        await video.encode_to_clock_gif(src, out, mode=mode)
    except video.VideoEncodeError as exc:
        shutil.rmtree(work, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc))

    # FileResponse streams `out`, then the background task tidies the workspace.
    return FileResponse(
        out, media_type="image/gif", filename="bg.gif",
        background=BackgroundTask(shutil.rmtree, work, ignore_errors=True),
    )
