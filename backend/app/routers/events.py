"""Activity feed API — recent library changes (newest-first) + restore-from-trash
for deleted ROMs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import db
from ..services import events, storage
from .sessions import require_session

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/sessions/{session_id}/events")
def list_events(session_id: str, limit: int = events.DEFAULT_LIMIT) -> dict:
    """Newest-first activity log (uploads, renames, PICO-8 compat edits, deletes…).
    `limit` is clamped so a bad client can't ask for everything at once."""
    limit = max(1, min(int(limit or events.DEFAULT_LIMIT), events.QUERY_MAX))
    with db.connect() as conn:
        require_session(conn, session_id)
        return {"events": events.recent(conn, session_id, limit)}


def _reinsert_rom(conn, snapshot: dict) -> None:
    """Re-insert a ROM row from a delete snapshot, using only columns that still
    exist (robust to schema drift since the snapshot was taken)."""
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(roms)")]
    use = [c for c in cols if c in snapshot]
    placeholders = ",".join("?" * len(use))
    conn.execute(
        f"INSERT INTO roms ({','.join(use)}) VALUES ({placeholders})",
        [snapshot[c] for c in use],
    )


@router.post("/sessions/{session_id}/events/{event_id}/restore")
def restore_event(session_id: str, event_id: str) -> dict:
    """Undo a ROM deletion: move its files back out of _trash and re-add the DB
    row. Only works on a rom_delete event that's not already restored and still
    within the recovery window."""
    with db.connect() as conn:
        require_session(conn, session_id)
        ev = events.get(conn, session_id, event_id)
        if ev is None or ev["event_type"] != "rom_delete":
            raise HTTPException(status_code=404, detail="복구할 삭제 기록이 없습니다")
        meta = ev["meta"] or {}
        if meta.get("restored"):
            raise HTTPException(status_code=409, detail="이미 복구되었습니다")
        if not ev["within_window"]:
            raise HTTPException(status_code=410, detail="복구 보관 기간(30일)이 지났습니다")
        snap = meta.get("snapshot")
        if not snap or not snap.get("id"):
            raise HTTPException(status_code=410, detail="복구 정보가 없습니다")
        if conn.execute("SELECT 1 FROM roms WHERE id = ?", (snap["id"],)).fetchone():
            raise HTTPException(status_code=409, detail="이미 라이브러리에 있습니다")

        # Move the ROM file back first (the cover is best-effort).
        if not storage.restore_from_trash(session_id, snap.get("rom_path")):
            raise HTTPException(status_code=410, detail="휴지통에서 파일을 찾을 수 없습니다 (보관 기간 만료)")
        storage.restore_from_trash(session_id, snap.get("cover_path"))

        _reinsert_rom(conn, snap)
        events.mark_restored(conn, event_id)
        events.log(conn, session_id, "rom_restore", rom_id=snap["id"],
                   rom_name=snap.get("stored_name"), system_key=snap.get("system_key"))
    return {"restored": event_id, "rom_id": snap["id"]}
