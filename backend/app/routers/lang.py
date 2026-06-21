"""Language / Korean-patch metadata for library ROMs.

Detection is fully automatic — at upload time (roms router) and a one-time
startup backfill (services/langfill) — so there is NO scan button. This router
exposes only the occasional MANUAL override, protected from auto re-derivation.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from .. import db
from ..services import events, langtag
from .sessions import require_session

router = APIRouter(prefix="/api", tags=["lang"])


@router.patch("/sessions/{session_id}/roms/{rom_id}/lang")
def set_lang(session_id: str, rom_id: str, payload: dict = Body(...)) -> dict:
    """Manual override of a rom's user-patch flag. Marks lang_source='manual' so
    a later scan won't revert it. Body: {"is_korean_patched": true|false}.
    (Generic "user patch applied" toggle — not gated to Korean deploys.)"""
    if "is_korean_patched" not in payload:
        raise HTTPException(status_code=400, detail="is_korean_patched 값이 필요합니다")
    patched = bool(payload["is_korean_patched"])
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            "SELECT orig_lang, play_lang, is_korean_patched, stored_name, system_key "
            "FROM roms WHERE id = ? AND session_id = ?",
            (rom_id, session_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="ROM을 찾을 수 없습니다")
        base = langtag.LangInfo(
            orig_lang=row["orig_lang"], play_lang=row["play_lang"],
            is_korean_patched=bool(row["is_korean_patched"]),
        )
        updated = langtag.manual_patch(base, patched)
        conn.execute(
            """UPDATE roms SET play_lang = ?, is_korean_patched = ?, lang_source = 'manual'
               WHERE id = ?""",
            (updated.play_lang, int(updated.is_korean_patched), rom_id),
        )
        if bool(row["is_korean_patched"]) != updated.is_korean_patched:
            events.log(conn, session_id, "lang_patch", rom_id=rom_id,
                       rom_name=row["stored_name"], system_key=row["system_key"],
                       meta={"patched": updated.is_korean_patched})
    return {
        "rom_id": rom_id, "orig_lang": updated.orig_lang, "play_lang": updated.play_lang,
        "is_korean_patched": updated.is_korean_patched, "lang_source": "manual",
    }
