"""DATA — scratch/reference uploads. Stored under the session's _data dir and
EXCLUDED from the SD package zip. Filesystem-backed (no DB metadata needed)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from .. import db
from ..services import storage
from .sessions import require_session

router = APIRouter(prefix="/api", tags=["data"])


def _safe_target(session_id: str, name: str) -> Path:
    """Resolve a scratch file path, guarding against path traversal."""
    base = storage.scratch_dir(session_id).resolve()
    target = (base / storage.safe_name(name)).resolve()
    if base not in target.parents:
        raise HTTPException(status_code=400, detail="잘못된 파일명")
    return target


@router.get("/sessions/{session_id}/data")
def list_data(session_id: str) -> dict:
    with db.connect() as conn:
        require_session(conn, session_id)
    base = storage.scratch_dir(session_id)
    files = []
    if base.exists():
        for p in sorted(base.iterdir()):
            if p.is_file():
                files.append({"name": p.name, "size": p.stat().st_size})
    return {"files": files}


@router.post("/sessions/{session_id}/data")
async def upload_data(session_id: str, files: list[UploadFile] = File(...)) -> dict:
    with db.connect() as conn:
        require_session(conn, session_id)
    stored = []
    for upload in files:
        name = upload.filename or "file"
        target = _safe_target(session_id, name)
        # Stream to disk in chunks instead of reading the whole upload into RAM —
        # CD images / archives can be hundreds of MB and a full read would spike
        # memory and stall the worker.
        target.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with target.open("wb") as out:
            while True:
                chunk = await upload.read(1 << 20)  # 1 MiB
                if not chunk:
                    break
                out.write(chunk)
                size += len(chunk)
        stored.append({"name": target.name, "size": size})
    return {"stored": len(stored), "files": stored}


@router.get("/sessions/{session_id}/data/{name}/download")
def download_data(session_id: str, name: str) -> Response:
    with db.connect() as conn:
        require_session(conn, session_id)
    target = _safe_target(session_id, name)
    if not target.exists():
        raise HTTPException(status_code=404, detail="파일이 없습니다")
    return Response(
        content=target.read_bytes(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{target.name}"'},
    )


@router.delete("/sessions/{session_id}/data/{name}")
def delete_data(session_id: str, name: str) -> dict:
    with db.connect() as conn:
        require_session(conn, session_id)
    target = _safe_target(session_id, name)
    target.unlink(missing_ok=True)
    return {"deleted": target.name}
