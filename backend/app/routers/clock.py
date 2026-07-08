"""Clock background: any image/video → a 320×240 /clock/gif/bg.gif for download.

Stateless — nothing is stored server-side. The user converts a source, downloads
the resulting bg.gif, and drops it into /clock/gif/ on the SD card (the firmware's
Clock app scans that folder; bg.gif is just the default pick). The LCD is 320×240
and the clock scale-fills, so a larger source only wastes bytes; the encoder pins
the output to 320×240.
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


def _parse_crop(raw: str | None) -> video.ClockCrop | None:
    """Validate the cropper's fraction rectangle ("x,y,w,h", fractions of the
    source frame). Malformed or outside the frame → None (falls back to fit)."""
    if not raw:
        return None
    try:
        x, y, w, h = (float(v) for v in raw.split(","))
    except ValueError:
        return None
    eps = 0.001   # cropper rounding slack
    if w <= 0 or h <= 0 or x < -eps or y < -eps or x + w > 1 + eps or y + h > 1 + eps:
        return None
    x, y = max(x, 0.0), max(y, 0.0)
    return (x, y, min(w, 1.0 - x), min(h, 1.0 - y))


@router.post("/clock/background")
async def clock_background(
    file: UploadFile = File(...),
    mode: str = Form(video.DEFAULT_FIT_MODE),  # fit | fill | stretch | custom (user crop)
    crop: str = Form(""),                      # custom mode: "x,y,w,h" source fractions
) -> FileResponse:
    """Convert an uploaded image or video into a clock-ready bg.gif and return it
    as a download. A still image becomes a 1-frame static background; a video/GIF
    is length-capped and loops on-device. The temp workspace is removed once the
    response has been sent."""
    crop_box = _parse_crop(crop)
    if mode not in video.CLOCK_FIT_MODES or (mode == "custom" and crop_box is None):
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
        await video.encode_to_clock_gif(src, out, mode=mode, crop=crop_box)
    except video.VideoEncodeError as exc:
        shutil.rmtree(work, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc))

    # FileResponse streams `out`, then the background task tidies the workspace.
    return FileResponse(
        out, media_type="image/gif", filename="bg.gif",
        background=BackgroundTask(shutil.rmtree, work, ignore_errors=True),
    )
