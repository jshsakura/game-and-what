"""Extra passthrough files → SD root verbatim. Upload any file with a target SD
path (e.g. bios/nes/disksys.rom for FDS); it's stored under _extra mirroring that
path and added to the SD ZIP root unchanged."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from .. import config, db
from ..services import storage
from .sessions import require_session

router = APIRouter(prefix="/api", tags=["extra"])


def safe_rel_path(path: str) -> str:
    """Sanitize a user-supplied SD path: NFC, drop traversal/empty/absolute, clean
    each segment. 'bios/nes/disksys.rom' stays; '../x' → 'x'. Empty → error caller."""
    parts = [p for p in re.split(r"[\\/]+", storage.nfc(path) or "") if p and p not in (".", "..")]
    parts = [storage.safe_name(p) for p in parts]
    return "/".join(parts)


def _list(session_id: str) -> list[dict]:
    root = storage.extra_dir(session_id)
    if not root.exists():
        return []
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            out.append({"path": str(p.relative_to(root)).replace("\\", "/"),
                        "size_bytes": st.st_size,
                        # When it was put here. These files are hand-uploaded and
                        # never rewritten, so mtime IS the upload time — no DB row
                        # needs to carry it. Same UTC "YYYY-MM-DD HH:MM:SS" shape the
                        # activity feed emits, so the UI formats both the same way.
                        "uploaded_at": datetime.fromtimestamp(
                            st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")})
    return out


@router.get("/sessions/{session_id}/extra")
def list_extra(session_id: str) -> dict:
    with db.connect() as conn:
        require_session(conn, session_id)
    return {"files": _list(session_id)}


@router.post("/sessions/{session_id}/extra")
async def upload_extra(session_id: str, file: UploadFile = File(...),
                       path: str = Form(...)) -> dict:
    """Store one file at the given SD-relative path (under _extra)."""
    with db.connect() as conn:
        require_session(conn, session_id)

    rel = safe_rel_path(path)
    if not rel:
        raise HTTPException(status_code=400, detail="SD 경로를 입력하세요 (예: bios/nes/disksys.rom)")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다")
    if len(data) > config.MAX_EXTRA_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다")

    storage.write_bytes(storage.extra_dir(session_id) / rel, data)
    return {"path": rel, "size_bytes": len(data)}


@router.get("/sessions/{session_id}/extra/download")
def download_extra(session_id: str, path: str) -> Response:
    with db.connect() as conn:
        require_session(conn, session_id)
    rel = safe_rel_path(path)
    abs_path = storage.extra_dir(session_id) / rel
    if not rel or not abs_path.exists():
        raise HTTPException(status_code=404, detail="파일이 없습니다")
    name = Path(rel).name
    from urllib.parse import quote
    ascii_name = name.encode("ascii", "ignore").decode() or "file"
    return Response(content=abs_path.read_bytes(), media_type="application/octet-stream",
                    headers={"Content-Disposition":
                             f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"})


@router.delete("/sessions/{session_id}/extra")
def delete_extra(session_id: str, path: str) -> dict:
    with db.connect() as conn:
        require_session(conn, session_id)
    rel = safe_rel_path(path)
    abs_path = storage.extra_dir(session_id) / rel
    if rel and abs_path.exists():
        # soft-delete → _trash (recoverable) instead of permanent unlink.
        storage.move_to_trash(session_id, f"{storage.EXTRA_DIR_NAME}/{rel}")
    return {"deleted": rel}
