"""Firmware update file → SD root /retro-go_update.bin. A single file the device
flashes itself from on next boot (gw_sleep.c UPDATE_ARCHIVE_FILE). One per
library — uploading replaces it."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from .. import config, db
from ..services import storage
from .sessions import require_session

router = APIRouter(prefix="/api", tags=["firmware"])

_ALLOWED_SUFFIXES = {".bin"}


def _info(session_id: str) -> dict:
    p = storage.firmware_path(session_id)
    if p.exists():
        st = p.stat()
        # filename is always retro-go_update.bin, so the upload time identifies it.
        uploaded_at = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
        return {"present": True, "filename": storage.FIRMWARE_FILENAME,
                "size_bytes": st.st_size, "uploaded_at": uploaded_at}
    return {"present": False, "filename": storage.FIRMWARE_FILENAME,
            "size_bytes": 0, "uploaded_at": None}


@router.get("/sessions/{session_id}/firmware/download")
def download_firmware(session_id: str) -> Response:
    """Download the stored firmware .bin."""
    with db.connect() as conn:
        require_session(conn, session_id)
    p = storage.firmware_path(session_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="No firmware file")
    return Response(content=p.read_bytes(), media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{storage.FIRMWARE_FILENAME}"',
                             "Cache-Control": "no-store"})


@router.get("/sessions/{session_id}/firmware")
def get_firmware(session_id: str) -> dict:
    """Current firmware file info (present? size?)."""
    with db.connect() as conn:
        require_session(conn, session_id)
    return _info(session_id)


@router.post("/sessions/{session_id}/firmware")
async def upload_firmware(session_id: str, file: UploadFile = File(...)) -> dict:
    """Upload the firmware update (.bin). Replaces any existing one. It ships at
    the SD ZIP root as /retro-go_update.bin."""
    with db.connect() as conn:
        require_session(conn, session_id)

    name = storage.nfc(file.filename) or "firmware.bin"
    if Path(name).suffix.lower() not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only .bin files are supported (retro-go_update.bin)")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty")
    if len(data) > config.MAX_FIRMWARE_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    storage.write_bytes(storage.firmware_path(session_id), data)
    return {**_info(session_id), "original_name": name}


@router.delete("/sessions/{session_id}/firmware")
def delete_firmware(session_id: str) -> dict:
    """Remove the firmware file (won't ship in the SD ZIP)."""
    with db.connect() as conn:
        require_session(conn, session_id)
    p = storage.firmware_path(session_id)
    if p.exists():
        p.unlink()
    return {"present": False}
