"""Chunked / resumable upload flow for large ROMs and videos.

Flow:
  1. POST   /sessions/{sid}/uploads          init → upload_id
  2. PUT    /sessions/{sid}/uploads/{uid}/chunk?index=N   send chunk
  3. GET    /sessions/{sid}/uploads/{uid}    status (received, total, complete)
  4. POST   /sessions/{sid}/uploads/{uid}/complete  finalise → run pipeline

Small files can still use the direct upload endpoints (roms / videos).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile

from .. import config, db
from ..services import artfetch, covers, covers_pico8, jobs, metadata, storage, video
from ..systems import accepts_extension, get_system
from .sessions import require_session

router = APIRouter(prefix="/api", tags=["uploads"])

# ── helpers ──────────────────────────────────────────────────────────────────

_VALID_KINDS = {"rom", "video"}


def _require_upload(conn, session_id: str, upload_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM uploads WHERE id = ? AND session_id = ?",
        (upload_id, session_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Upload not found in session")
    return dict(row)


def _tmp_path_for(upload_id: str) -> Path:
    return config.TMP_DIR / f"{upload_id}.part"


# ── init ─────────────────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/uploads")
def init_upload(
    session_id: str,
    filename: str = Body(...),
    total_size: int = Body(...),
    kind: str = Body(...),
    system: str | None = Body(None),
) -> dict:
    """Initialise a chunked upload.  Returns upload_id to use in subsequent calls."""
    if kind not in _VALID_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(_VALID_KINDS)}")
    if total_size <= 0 or total_size > config.MAX_UPLOAD_TOTAL_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"total_size must be 1..{config.MAX_UPLOAD_TOTAL_BYTES}",
        )
    if kind == "rom":
        if not system:
            raise HTTPException(status_code=400, detail="system is required when kind=rom")
        try:
            sys_obj = get_system(system)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Unknown system: {system}")
        if not accepts_extension(sys_obj, filename):
            raise HTTPException(status_code=400, detail="File extension not accepted for system")
        if total_size > config.MAX_ROM_BYTES:
            raise HTTPException(status_code=400, detail="ROM exceeds maximum allowed size")
    if kind == "video" and total_size > config.MAX_VIDEO_BYTES:
        raise HTTPException(status_code=400, detail="Video exceeds maximum allowed size")

    with db.connect() as conn:
        require_session(conn, session_id)

    upload_id = storage.new_id()
    tmp_path = _tmp_path_for(upload_id)
    # Create the empty part file now so chunks can be appended.
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_bytes(b"")

    with db.connect() as conn:
        conn.execute(
            """INSERT INTO uploads
               (id, session_id, filename, total_size, received, kind, system_key, tmp_path, status)
               VALUES (?,?,?,?,0,?,?,?,'receiving')""",
            (upload_id, session_id, filename, total_size, kind, system, str(tmp_path)),
        )

    return {
        "upload_id": upload_id,
        "filename": filename,
        "total_size": total_size,
        "kind": kind,
        "received": 0,
    }


# ── chunk PUT ────────────────────────────────────────────────────────────────

@router.put("/sessions/{session_id}/uploads/{upload_id}/chunk")
async def put_chunk(
    session_id: str,
    upload_id: str,
    index: int = Query(..., ge=0),
    file: UploadFile = File(...),
) -> dict:
    """Append a chunk to the temp part file.

    Chunks must arrive in order (index 0, 1, 2…).  Each chunk may be at most
    GNW_MAX_CHUNK_BYTES.  The server validates the expected offset so accidental
    re-sends are caught rather than silently corrupting data.
    """
    with db.connect() as conn:
        require_session(conn, session_id)
        upload = _require_upload(conn, session_id, upload_id)

    if upload["status"] != "receiving":
        raise HTTPException(status_code=409, detail=f"Upload is already '{upload['status']}'")

    chunk_data = await file.read()
    if len(chunk_data) == 0:
        raise HTTPException(status_code=400, detail="Empty chunk")
    if len(chunk_data) > config.MAX_CHUNK_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Chunk too large (max {config.MAX_CHUNK_BYTES} bytes)",
        )

    current_received: int = upload["received"]
    total_size: int = upload["total_size"]

    # Validate this chunk's expected byte offset matches index * max_chunk.
    # (This is a simple sequential-order guard, not a full range-request impl.)
    expected_offset = index * config.MAX_CHUNK_BYTES
    if current_received != expected_offset:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Unexpected chunk index {index}: "
                f"expected offset {expected_offset}, have {current_received} bytes"
            ),
        )

    new_received = current_received + len(chunk_data)
    if new_received > total_size:
        raise HTTPException(
            status_code=400,
            detail=f"Chunk would exceed declared total_size ({total_size})",
        )

    tmp_path = Path(upload["tmp_path"])
    with tmp_path.open("ab") as fh:
        fh.write(chunk_data)

    with db.connect() as conn:
        conn.execute(
            "UPDATE uploads SET received = ? WHERE id = ?",
            (new_received, upload_id),
        )

    return {
        "upload_id": upload_id,
        "received": new_received,
        "total_size": total_size,
        "complete": new_received >= total_size,
    }


# ── status GET ───────────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/uploads/{upload_id}")
def get_upload_status(session_id: str, upload_id: str) -> dict:
    """Query how many bytes have been received for a chunked upload."""
    with db.connect() as conn:
        require_session(conn, session_id)
        upload = _require_upload(conn, session_id, upload_id)

    return {
        "upload_id": upload_id,
        "filename": upload["filename"],
        "total_size": upload["total_size"],
        "received": upload["received"],
        "kind": upload["kind"],
        "status": upload["status"],
        "complete": upload["received"] >= upload["total_size"],
    }


# ── finalise ─────────────────────────────────────────────────────────────────

def _rom_stored_name(meta: metadata.GameMeta, original: str) -> str:
    ext = original.rsplit(".", 1)[-1] if "." in original else ""
    base = storage.safe_name(meta.title)
    return f"{base}.{ext}" if ext else base


async def _make_cover_from_path(sys_obj, rom_path: Path, meta: metadata.GameMeta) -> bytes | None:
    try:
        if sys_obj.pico8:
            return covers_pico8.render_pico8_cover(rom_path)
        if meta.art_url:
            art = await artfetch.fetch_image(meta.art_url)
            if art:
                return covers.render_cover(art)
    except covers.CoverError:
        return None
    return None


async def _run_encode(
    job_id: str,
    video_id: str,
    src: Path,
    dst: Path,
    session_id: str,
) -> None:
    await jobs.update(job_id, status="running", progress=0.05, message="encoding")
    try:
        await video.encode_to_mjpeg_avi(src, dst)
    except video.VideoEncodeError as exc:
        dst.unlink(missing_ok=True)  # drop any partial/zero-byte .avi ffmpeg left
        await jobs.update(job_id, status="failed", message=str(exc))
        with db.connect() as conn:
            conn.execute("UPDATE videos SET status='failed' WHERE id=?", (video_id,))
        return
    finally:
        src.unlink(missing_ok=True)

    rel = storage.relative_to_session(session_id, dst)
    with db.connect() as conn:
        conn.execute("UPDATE videos SET status='ok', avi_path=? WHERE id=?", (rel, video_id))
    await jobs.update(
        job_id,
        status="done",
        progress=1.0,
        message="done",
        result={"video_id": video_id, "avi_path": rel},
    )


@router.post("/sessions/{session_id}/uploads/{upload_id}/complete")
async def complete_upload(session_id: str, upload_id: str) -> dict:
    """Finalise a chunked upload and run the appropriate processing pipeline.

    For kind=rom : name → cover → store → DB (same as the direct upload endpoint).
    For kind=video: kick off the MJPEG encode job (same as the direct upload endpoint).
    Returns the same shape as the corresponding direct-upload endpoint.
    """
    with db.connect() as conn:
        require_session(conn, session_id)
        upload = _require_upload(conn, session_id, upload_id)

    if upload["status"] != "receiving":
        raise HTTPException(status_code=409, detail=f"Upload is already '{upload['status']}'")

    received: int = upload["received"]
    total_size: int = upload["total_size"]
    if received < total_size:
        raise HTTPException(
            status_code=409,
            detail=f"Upload incomplete: {received}/{total_size} bytes received",
        )

    tmp_path = Path(upload["tmp_path"])
    if not tmp_path.exists():
        raise HTTPException(status_code=500, detail="Temp file missing; upload may have been lost")

    kind: str = upload["kind"]

    try:
        if kind == "rom":
            result = await _finalise_rom(session_id, upload, tmp_path)
        else:
            result = await _finalise_video(session_id, upload, tmp_path)
    except Exception:
        # Mark failed so the client knows not to retry with the same upload_id.
        with db.connect() as conn:
            conn.execute("UPDATE uploads SET status='failed' WHERE id=?", (upload_id,))
        tmp_path.unlink(missing_ok=True)
        raise

    with db.connect() as conn:
        conn.execute("UPDATE uploads SET status='complete' WHERE id=?", (upload_id,))
    tmp_path.unlink(missing_ok=True)
    return result


async def _finalise_rom(session_id: str, upload: dict, tmp_path: Path) -> dict:
    original: str = upload["filename"]
    system_key: str = upload["system_key"]
    sys_obj = get_system(system_key)

    meta = metadata.resolve_metadata(sys_obj.key, original)
    stored_name = _rom_stored_name(meta, original)
    rom_path = storage.roms_dir(session_id, sys_obj.dirname) / stored_name

    # Move assembled temp file into the library.
    rom_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.rename(rom_path)

    cover_bytes = await _make_cover_from_path(sys_obj, rom_path, meta)
    cover_rel: str | None = None
    cover_status = "none"
    if cover_bytes:
        cover_name = covers.cover_filename(stored_name)
        cover_path = storage.covers_dir(session_id, sys_obj.dirname) / cover_name
        storage.write_bytes(cover_path, cover_bytes)
        cover_rel = storage.relative_to_session(session_id, cover_path)
        cover_status = "ok"

    rom_id = storage.new_id()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO roms
               (id, session_id, system_key, original_name,
                stored_name, korean_name, rom_path, cover_path, cover_status)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                rom_id, session_id, sys_obj.key, meta.original_name,
                stored_name, meta.korean_name,
                storage.relative_to_session(session_id, rom_path),
                cover_rel, cover_status,
            ),
        )

    return {
        "rom_id": rom_id,
        "name": original,
        "ok": True,
        "stored_name": stored_name,
        "korean_name": meta.korean_name,
        "screenshot_url": meta.screenshot_url,
        "cover_status": cover_status,
    }


async def _finalise_video(session_id: str, upload: dict, tmp_path: Path) -> dict:
    if not video.ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg not installed on server")

    original: str = upload["filename"]
    avi_name = f"{storage.safe_name(Path(original).stem)}.avi"
    src_path = storage.media_dir(session_id) / f".src_{storage.new_id()}"
    dst_path = storage.media_dir(session_id) / avi_name

    src_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.rename(src_path)

    video_id = storage.new_id()
    job_id = storage.new_id()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO videos (id, session_id, original_name, avi_name, job_id, status)
               VALUES (?,?,?,?,?, 'encoding')""",
            (video_id, session_id, original, avi_name, job_id),
        )
    await jobs.create(job_id, "video_encode")
    asyncio.create_task(_run_encode(job_id, video_id, src_path, dst_path, session_id))

    return {
        "video_id": video_id,
        "job_id": job_id,
        "avi_name": avi_name,
        "status": "encoding",
    }
