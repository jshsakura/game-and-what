"""Delete / rename ROMs/videos (and their files) in a session."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from .. import db
from ..services import events, renames, storage
from .sessions import require_session

router = APIRouter(prefix="/api", tags=["manage"])


def _remove(session_id: str, rel_path: str | None) -> None:
    """Soft-delete: move the file to _trash (recoverable). Never raises."""
    if rel_path:
        storage.move_to_trash(session_id, rel_path)


@router.delete("/sessions/{session_id}/roms/{rom_id}")
def delete_rom(session_id: str, rom_id: str) -> dict:
    """Remove a ROM, its cover file, and the DB row."""
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            "SELECT * FROM roms WHERE id = ? AND session_id = ?",
            (rom_id, session_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Unknown rom")
        _remove(session_id, row["rom_path"])
        _remove(session_id, row["cover_path"])
        conn.execute("DELETE FROM roms WHERE id = ?", (rom_id,))
        # Snapshot the whole row so the delete can be undone from the activity
        # feed (files move to _trash; this re-inserts the DB row on restore).
        events.log(conn, session_id, "rom_delete", rom_id=rom_id,
                   rom_name=row["stored_name"], system_key=row["system_key"],
                   meta={"snapshot": dict(row)})
    return {"deleted": rom_id}


@router.patch("/sessions/{session_id}/roms/{rom_id}")
def rename_rom(
    session_id: str, rom_id: str, payload: dict = Body(...)
) -> dict:
    """Rename a ROM's filename (extension included, freely). Moves the rom file
    AND its cover (.img) together so they stay a set. Updates the DB paths."""
    raw = (payload.get("name") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="파일명을 입력하세요")

    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            """SELECT id, system_key, stored_name, rom_path, cover_path
                 FROM roms WHERE id = ? AND session_id = ?""",
            (rom_id, session_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Unknown rom")
        try:
            result = renames.rename_rom(conn, session_id, dict(row), raw)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if result.get("stored_name") and result["stored_name"] != row["stored_name"]:
            events.log(conn, session_id, "rom_rename", rom_id=rom_id,
                       rom_name=result["stored_name"], system_key=row["system_key"],
                       meta={"from": row["stored_name"]})
    return {"id": rom_id, **result}


@router.delete("/sessions/{session_id}/videos/{video_id}")
def delete_video(session_id: str, video_id: str) -> dict:
    """Remove a video (.avi) and the DB row."""
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            "SELECT avi_path FROM videos WHERE id = ? AND session_id = ?",
            (video_id, session_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Unknown video")
        _remove(session_id, row["avi_path"])
        conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    return {"deleted": video_id}


@router.delete("/sessions/{session_id}/music/{music_id}")
def delete_music(session_id: str, music_id: str) -> dict:
    """Remove a music track (.mp3) and the DB row."""
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            "SELECT music_path FROM music WHERE id = ? AND session_id = ?",
            (music_id, session_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Unknown music")
        _remove(session_id, row["music_path"])
        conn.execute("DELETE FROM music WHERE id = ?", (music_id,))
    return {"deleted": music_id}
