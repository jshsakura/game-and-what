"""Download the session library as an SD-ready ZIP."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse, Response

from .. import db
from ..services import events, packaging
from .sessions import require_session

router = APIRouter(prefix="/api", tags=["package"])


@router.patch("/sessions/{session_id}/roms/{rom_id}/sd-include")
def set_sd_include(session_id: str, rom_id: str, payload: dict = Body(...)) -> dict:
    """Opt a homebrew ROM into the SD ZIP (its ROM file, not just the cover).
    Body: {"include": true|false}. Default for homebrew is false (covers only)."""
    include = bool(payload.get("include"))
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            "SELECT id FROM roms WHERE id = ? AND session_id = ?", (rom_id, session_id)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="ROM을 찾을 수 없습니다")
        conn.execute("UPDATE roms SET sd_include = ? WHERE id = ?", (int(include), rom_id))
    return {"rom_id": rom_id, "sd_include": include}


@router.patch("/sessions/{session_id}/roms/{rom_id}/sd-exclude")
def set_sd_exclude(session_id: str, rom_id: str, payload: dict = Body(...)) -> dict:
    """Opt a (non-homebrew) ROM OUT of the SD ZIP without deleting it.
    Body: {"exclude": true|false}. exclude=1 → ROM file + cover dropped from the
    card, but the library keeps the entry."""
    exclude = bool(payload.get("exclude"))
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            "SELECT stored_name, system_key FROM roms WHERE id = ? AND session_id = ?", (rom_id, session_id)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="ROM을 찾을 수 없습니다")
        conn.execute("UPDATE roms SET sd_exclude = ? WHERE id = ?", (int(exclude), rom_id))
        events.log(conn, session_id, "sd_exclude", rom_id=rom_id,
                   rom_name=row["stored_name"], system_key=row["system_key"],
                   meta={"exclude": exclude})
    return {"rom_id": rom_id, "sd_exclude": exclude}


@router.patch("/sessions/{session_id}/sd-exclude")
def set_sd_exclude_bulk(session_id: str, payload: dict = Body(...)) -> dict:
    """Bulk opt many ROMs in/out of the SD ZIP. Body: {"rom_ids": [...],
    "exclude": true|false}. Used to slim a bloated set in one call."""
    rom_ids = payload.get("rom_ids")
    if not isinstance(rom_ids, list) or not rom_ids:
        raise HTTPException(status_code=400, detail="rom_ids가 필요합니다")
    exclude = bool(payload.get("exclude"))
    with db.connect() as conn:
        require_session(conn, session_id)
        # Only touch rows that belong to this session (filter, don't trust input).
        placeholders = ",".join("?" * len(rom_ids))
        cur = conn.execute(
            f"UPDATE roms SET sd_exclude = ? WHERE session_id = ? AND id IN ({placeholders})",
            (int(exclude), session_id, *rom_ids),
        )
        updated = cur.rowcount
    return {"updated": updated, "exclude": exclude}


@router.patch("/sessions/{session_id}/roms/{rom_id}/favorite")
def set_favorite(session_id: str, rom_id: str, payload: dict = Body(...)) -> dict:
    """Mark/unmark a ROM as a favorite (★). UI-only — sorts favorites first and
    shows a star on the cover. Body: {"favorite": true|false}."""
    favorite = bool(payload.get("favorite"))
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            "SELECT id FROM roms WHERE id = ? AND session_id = ?", (rom_id, session_id)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="ROM을 찾을 수 없습니다")
        conn.execute("UPDATE roms SET favorite = ? WHERE id = ?", (int(favorite), rom_id))
    return {"rom_id": rom_id, "favorite": favorite}


PICO8_COMPAT_VALUES = {"good", "slow", "partial", "broken"}


@router.patch("/sessions/{session_id}/roms/{rom_id}/pico8-compat")
def set_pico8_compat(session_id: str, rom_id: str, payload: dict = Body(...)) -> dict:
    """Manually set a PICO-8 cart's compatibility on the real G&W (z8lua) device.
    Body: {"status": "good"|"slow"|"partial"|"broken"|null}. null clears it back
    to untested. Display-only — it does not affect what ships in the SD package."""
    status = payload.get("status")
    if status is not None and status not in PICO8_COMPAT_VALUES:
        raise HTTPException(status_code=400, detail="알 수 없는 호환 상태입니다")
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            "SELECT system_key, stored_name FROM roms WHERE id = ? AND session_id = ?", (rom_id, session_id)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="ROM을 찾을 수 없습니다")
        if row["system_key"] != "pico8":
            raise HTTPException(status_code=400, detail="PICO-8 롬에만 설정할 수 있습니다")
        conn.execute("UPDATE roms SET pico8_compat = ? WHERE id = ?", (status, rom_id))
        events.log(conn, session_id, "pico8_compat", rom_id=rom_id,
                   rom_name=row["stored_name"], system_key="pico8",
                   meta={"status": status})
    return {"rom_id": rom_id, "pico8_compat": status}


def _parse_systems(system: str | None) -> "set[str] | None":
    """`?system=` accepts one dirname or a comma-separated list (selected systems).
    None / empty → the full SD package."""
    if not system:
        return None
    picked = {s.strip() for s in system.split(",") if s.strip()}
    return picked or None


def _homebrew_roms(conn, session_id: str) -> "set[str]":
    """Relative paths of homebrew ROM files the user opted INTO the SD (sd_include=1).
    Homebrew ships covers-only by default; these are the ROMs to also include."""
    rows = conn.execute(
        "SELECT rom_path FROM roms WHERE session_id = ? AND system_key = 'homebrew' "
        "AND sd_include = 1", (session_id,)).fetchall()
    return {r["rom_path"] for r in rows}


def _excluded_roms(conn, session_id: str) -> "set[str]":
    """Relative paths (ROM file + its cover) dropped from the SD card while kept
    in the library. Two sources:
      • sd_exclude=1 — the user opted this ROM out manually.
      • pico8_compat='broken' — a PICO-8 cart that doesn't run on the real G&W
        (구동불가); never worth shipping, so it's auto-excluded."""
    rows = conn.execute(
        "SELECT rom_path, cover_path FROM roms WHERE session_id = ? "
        "AND (sd_exclude = 1 OR pico8_compat = 'broken')",
        (session_id,)).fetchall()
    out: set[str] = set()
    for r in rows:
        if r["rom_path"]:
            out.add(r["rom_path"])
        if r["cover_path"]:
            out.add(r["cover_path"])
    return out


@router.get("/sessions/{session_id}/package/size")
def package_size(session_id: str, video: bool = False, system: str | None = None) -> dict:
    """Estimated on-SD byte size for the (optionally filtered) package."""
    with db.connect() as conn:
        require_session(conn, session_id)
        homebrew = _homebrew_roms(conn, session_id)
        excluded = _excluded_roms(conn, session_id)
    systems = _parse_systems(system)
    return {"bytes": packaging.sd_content_size(session_id, include_video=video, systems=systems,
                                               homebrew_roms=homebrew, excluded_roms=excluded)}


@router.get("/sessions/{session_id}/package")
def download_package(request: Request, session_id: str, video: bool = False,
                     system: str | None = None) -> Response:
    """ZIP mirroring the SD card (/roms, /covers). Video (/media) is excluded by
    default — pass ?video=1 to include it. Pass ?system=<dirname> (or a
    comma-separated list) to package only those systems.

    Cached & ETagged: the zip is built to disk only when the library/params change
    (not on every download), and an unchanged client gets a 304."""
    with db.connect() as conn:
        require_session(conn, session_id)
        homebrew = _homebrew_roms(conn, session_id)
        excluded = _excluded_roms(conn, session_id)
    systems = _parse_systems(system)
    if not packaging.session_has_content(session_id, include_video=video, systems=systems):
        raise HTTPException(status_code=404, detail="Nothing to package yet")

    # ETag = content fingerprint. If the client already has this exact build, skip.
    etag = packaging.sd_fingerprint(session_id, include_video=video, systems=systems,
                                    homebrew_roms=homebrew, excluded_roms=excluded)
    cache_headers = {"ETag": f'"{etag}"', "Cache-Control": "private, no-cache"}
    if (request.headers.get("if-none-match") or "").strip('"') == etag:
        return Response(status_code=304, headers=cache_headers)

    # Built to a disk cache (NOT RAM → no OOM), reused until the content changes.
    zip_path, _ = packaging.build_sd_zip_cached(session_id, include_video=video, systems=systems,
                                                homebrew_roms=homebrew, excluded_roms=excluded)
    # filename suffix: single system → its name; multiple → "-selected"; full → none
    if systems and len(systems) == 1:
        suffix = f"-{next(iter(systems))}"
    elif systems:
        suffix = "-selected"
    else:
        suffix = ""
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"gnw-sd{suffix}-{session_id[:8]}.zip",
        headers=cache_headers,
    )
