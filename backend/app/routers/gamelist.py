"""Apply a gamelist.xml (uploaded to DATA) as a Korean-rename batch."""
from __future__ import annotations

import unicodedata
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from .. import db
from ..services import gamelist, renames, storage
from .sessions import require_korean_mode, require_session

router = APIRouter(prefix="/api", tags=["gamelist"])


def _resolve(session_id: str, filename: str) -> Path:
    """Find a DATA file by name, tolerant of NFC/NFD unicode (macOS uploads are
    NFD, so a byte-exact match would miss)."""
    base = storage.scratch_dir(session_id).resolve()
    want = unicodedata.normalize("NFC", storage.safe_name(filename))
    if base.exists():
        for p in base.iterdir():
            if p.is_file() and unicodedata.normalize("NFC", p.name) == want:
                return p
    raise HTTPException(status_code=404, detail="gamelist 파일을 찾을 수 없습니다 (DATA에 먼저 올리세요)")


@router.post("/sessions/{session_id}/gamelist/preview")
def preview(session_id: str, payload: dict = Body(...)) -> dict:
    """Dry-run: how many library roms would be renamed, and to what."""
    require_korean_mode()
    fn = (payload.get("filename") or "").strip()
    system = payload.get("system") or gamelist.system_from_filename(fn)
    with db.connect() as conn:
        require_session(conn, session_id)
        path = _resolve(session_id, fn)
        try:
            result = gamelist.build_plan(conn, session_id, path, system)
        except Exception as exc:  # malformed XML, etc.
            raise HTTPException(status_code=400, detail=f"gamelist 파싱 실패: {exc}") from exc
    return {"matched": len(result["plan"]), "system": result["system"], "plan": result["plan"][:300]}


@router.post("/sessions/{session_id}/gamelist/apply")
def apply(session_id: str, payload: dict = Body(...)) -> dict:
    """Rename every matched library rom file (+ its cover) to the Korean name."""
    require_korean_mode()
    fn = (payload.get("filename") or "").strip()
    system = payload.get("system") or gamelist.system_from_filename(fn)
    with db.connect() as conn:
        require_session(conn, session_id)
        path = _resolve(session_id, fn)
        try:
            result = gamelist.build_plan(conn, session_id, path, system)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"gamelist 파싱 실패: {exc}") from exc
        plan = result["plan"]

        renamed = 0
        skipped: list[str] = []
        for item in plan:
            row = conn.execute(
                "SELECT id, system_key, stored_name, rom_path, cover_path FROM roms WHERE id = ?",
                (item["rom_id"],),
            ).fetchone()
            if not row:
                continue
            try:
                renames.rename_rom(conn, session_id, dict(row), item["new"], suffix_on_clash=True)
                renamed += 1
            except ValueError:
                # One desynced row (its file is gone) must not abort the rest of the
                # batch — rename what we can and report what we couldn't.
                skipped.append(row["stored_name"])
    return {"renamed": renamed, "matched": len(plan), "skipped": skipped}
