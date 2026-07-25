"""Cover management endpoints.

GET  /sessions/{sid}/roms/{rom_id}/cover              → serve cover image (preview)
POST /sessions/{sid}/roms/{rom_id}/cover              → upload user image → render+save
POST /sessions/{sid}/roms/{rom_id}/cover/regenerate   → re-attempt art fetch (best-effort)
"""
from __future__ import annotations

import logging
from pathlib import Path

import json
import re
from urllib.parse import quote

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from .. import db
from ..services import artfetch, covers, covers_pico8, gamelist, igdb, metadata, name_index, renames, storage, tgdb, titlematch
from ..systems import cover_target, get_system
from .sessions import require_korean_mode, require_session

_HANGUL = re.compile(r"[가-힣]")

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["covers"])

# Cover uploads are validated by actually DECODING the bytes (Pillow), not by
# trusting the extension — "whatever comes in" works as long as Pillow can read
# it. This list is just a friendly hint / fast-path for common types; an unknown
# extension is NOT rejected here, the decode step is the real gate.
_ALLOWED_COVER_SUFFIXES = {
    ".png", ".apng", ".jpg", ".jpeg", ".jpe", ".jfif", ".webp", ".bmp", ".dib",
    ".gif", ".tif", ".tiff", ".ico", ".cur", ".ppm", ".pgm", ".pbm", ".pnm",
    ".tga", ".jp2", ".j2k", ".jpx", ".jpf", ".jpc", ".j2c", ".qoi", ".pcx",
    ".sgi", ".rgb", ".rgba", ".bw", ".xbm", ".xpm", ".psd", ".dds", ".icns",
    ".im", ".ftc", ".ftu", ".blp", ".pxr", ".ras",
}

# Hard ceiling on a single cover upload (pre-resize source). Generous — a phone
# photo or hi-res box scan fits easily; blocks accidental multi-hundred-MB files.
_MAX_COVER_UPLOAD_BYTES = 40 * 1024 * 1024


def _parse_crop(crop) -> tuple[float, float, float, float] | None:
    """Accept {x,y,width,height} (0..1 fractions) → (x,y,w,h) tuple, else None."""
    if not crop:
        return None
    if isinstance(crop, str):
        try:
            crop = json.loads(crop)
        except (ValueError, TypeError):
            return None
    try:
        box = (float(crop["x"]), float(crop["y"]), float(crop["width"]), float(crop["height"]))
    except (KeyError, TypeError, ValueError):
        return None
    return box if box[2] > 0 and box[3] > 0 else None


def _require_rom(conn, session_id: str, rom_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM roms WHERE id = ? AND session_id = ?",
        (rom_id, session_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="ROM not found in session")
    return dict(row)


def _cover_abs(session_id: str, rom: dict) -> Path | None:
    """Absolute path to the cover .img file, or None if no cover recorded."""
    cover_rel: str | None = rom.get("cover_path")
    if not cover_rel:
        return None
    return storage.session_root(session_id) / cover_rel


def _dirname_of(rom: dict) -> str:
    parts = Path(rom["rom_path"]).parts        # ('roms', 'nes', 'Game.nes')
    return parts[1] if len(parts) >= 3 else "unknown"


def _rom_lang(rom: dict) -> "str | None":
    """The cover's corner flag, chosen EXPLICITLY per rom (cover_flag) and
    independent of the Korean-patch toggle. NULL/empty = no flag."""
    return (rom.get("cover_flag") or "").lower() or None


def rebake_cover_img(session_id: str, rom: dict) -> bool:
    """Re-render ONLY the device .img from the stored preview using the rom's
    current crop_box + flag (so the baked corner flag reflects the latest choice).
    The web preview / original is never touched. False if there's no cover yet."""
    if rom.get("cover_status") != "ok":
        return False
    preview = _preview_path(session_id, rom)
    if not preview.exists():
        return False
    cb = None
    if rom.get("crop_box"):
        try:
            cb = tuple(json.loads(rom["crop_box"]))
        except (ValueError, TypeError):
            cb = None
    try:
        cover_bytes = _render_cover(rom, preview.read_bytes(), crop_box=cb)
    except covers.CoverError:
        return False
    _save_cover(session_id, rom, cover_bytes)   # device .img only; preview untouched
    return True


def _render_cover(rom: dict, source, crop_box=None) -> bytes:
    """Render a device cover at this system's fixed size (3:4 box art or 1:1
    square) so all covers in the system share one size — see systems.cover_target."""
    tw, th = cover_target(rom["system_key"])
    return covers.render_cover(source, target_width=tw, target_height=th,
                               crop_box=crop_box, lang=_rom_lang(rom))


def _cover_basename(rom: dict) -> str:
    """The device cover's .img basename. A system's stored_name stands for the
    game, so the cover keeps rom-name → .img."""
    return covers.cover_filename(rom["stored_name"])


def _save_cover(session_id: str, rom: dict, cover_bytes: bytes, raw: bytes | None = None) -> str:
    """Write the device cover (186x100 .img). If `raw` (original source bytes) is
    given, also write the high-res WebP web preview. Returns the .img rel path."""
    cover_name = _cover_basename(rom)
    cover_path = storage.covers_dir(session_id, _dirname_of(rom)) / cover_name
    storage.write_bytes(cover_path, cover_bytes)
    if raw:
        _save_preview(session_id, rom, raw)
    return storage.relative_to_session(session_id, cover_path)


def _preview_path(session_id: str, rom: dict) -> Path:
    name = Path(rom["stored_name"]).stem + ".webp"
    return storage.previews_dir(session_id, _dirname_of(rom)) / name


def _save_preview(session_id: str, rom: dict, raw: bytes) -> None:
    """Best-effort high-res web preview from the ORIGINAL source bytes."""
    try:
        storage.write_bytes(_preview_path(session_id, rom), covers.render_preview(raw, lang=_rom_lang(rom)))
    except covers.CoverError:
        pass


def _update_cover_db(conn, rom_id: str, cover_rel: str, status: str, source: str,
                     crop_box: tuple[float, float, float, float] | None = None) -> None:
    conn.execute(
        "UPDATE roms SET cover_path = ?, cover_status = ?, cover_source = ?, crop_box = ? WHERE id = ?",
        (cover_rel, status, source, json.dumps(list(crop_box)) if crop_box else None, rom_id),
    )


@router.get("/sessions/{session_id}/roms/{rom_id}/cover")
def get_cover(session_id: str, rom_id: str, device: bool = False, full: bool = False) -> Response:
    """Serve the cover for the UI. Default = high-res DISPLAY image: the original
    art cropped to the system's fixed ratio (same framing the device shows, crisp,
    consistent). Pass ?full=1 for the UNTOUCHED full original (the crop tool's
    source — never modified). Pass ?device=1 for the raw device .img. 404 if none."""
    with db.connect() as conn:
        require_session(conn, session_id)
        rom = _require_rom(conn, session_id, rom_id)

    if not device:
        preview = _preview_path(session_id, rom)
        if preview.exists():
            raw = preview.read_bytes()
            if not full:
                try:
                    tw, th = cover_target(rom["system_key"])
                    cb = None
                    if rom.get("crop_box"):
                        try:
                            cb = tuple(json.loads(rom["crop_box"]))
                        except (ValueError, TypeError):
                            cb = None
                    raw = covers.render_display(raw, tw, th, crop_box=cb, lang=_rom_lang(rom))
                except covers.CoverError:
                    pass   # fall back to serving the full preview as-is
            return Response(content=raw, media_type="image/webp",
                            headers={"Cache-Control": "no-cache"})

    cover_abs = _cover_abs(session_id, rom)
    if cover_abs is None or not cover_abs.exists():
        raise HTTPException(status_code=404, detail="No cover available for this ROM")
    return Response(content=cover_abs.read_bytes(), media_type="image/jpeg",
                    headers={"Cache-Control": "no-cache"})


@router.get("/sessions/{session_id}/roms/{rom_id}/cover/download")
def download_cover(session_id: str, rom_id: str, variant: str = "device") -> Response:
    """Download a cover as a file attachment. variant=device → the actual
    device .img (the fixed-size art the hardware shows); variant=original →
    the high-res source art (full, uncropped WebP preview)."""
    with db.connect() as conn:
        require_session(conn, session_id)
        rom = _require_rom(conn, session_id, rom_id)

    stem = Path(rom["stored_name"]).stem
    if variant == "original":
        preview = _preview_path(session_id, rom)
        if not preview.exists():
            raise HTTPException(status_code=404, detail="No original art stored for this ROM")
        body, media, fname = preview.read_bytes(), "image/webp", f"{stem} (원본).webp"
    else:
        cover_abs = _cover_abs(session_id, rom)
        if cover_abs is None or not cover_abs.exists():
            raise HTTPException(status_code=404, detail="No device cover for this ROM")
        body, media, fname = cover_abs.read_bytes(), "image/jpeg", f"{stem}.img"

    ascii_name = fname.encode("ascii", "ignore").decode() or "cover"
    quoted = quote(fname)
    return Response(content=body, media_type=media, headers={
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted}",
        "Cache-Control": "no-cache",
    })


@router.post("/sessions/{session_id}/roms/{rom_id}/cover")
async def upload_cover(
    session_id: str,
    rom_id: str,
    file: UploadFile = File(...),
    crop: str | None = Form(None),
) -> dict:
    """Replace/set the cover from ANY user-supplied image.

    The format is validated by actually decoding the bytes (Pillow), so any
    raster image Pillow can read works — png, jpg, webp, gif, bmp, tiff, ico,
    heic-via-plugin, etc. — regardless of (or without) a file extension.

    Default fit-within (186x100); pass `crop` JSON {x,y,width,height} (0..1) to
    use a hand-picked crop region. Overwrites the .img, sets cover_status='ok'.
    """
    with db.connect() as conn:
        require_session(conn, session_id)
        rom = _require_rom(conn, session_id, rom_id)

    # Reject oversized uploads before slurping the whole thing into memory when
    # the client gave us a size; otherwise check after read as a backstop.
    if file.size is not None and file.size > _MAX_COVER_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다 (최대 40MB)")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다")
    if len(raw) > _MAX_COVER_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다 (최대 40MB)")

    crop_box = _parse_crop(crop)
    try:
        cover_bytes = _render_cover(rom, raw, crop_box=crop_box)
    except covers.CoverError as exc:
        # Stable Korean string = the frontend i18n key; technical cause is logged,
        # not shown, so the message stays translatable.
        log.info("cover render failed for rom %s: %s", rom_id, exc)
        raise HTTPException(
            status_code=422,
            detail="이미지를 읽을 수 없습니다 — 지원하지 않는 형식이거나 손상된 파일입니다",
        ) from exc

    cover_rel = _save_cover(session_id, rom, cover_bytes, raw)

    with db.connect() as conn:
        _update_cover_db(conn, rom_id, cover_rel, "ok", "manual", crop_box)

    return {
        "rom_id": rom_id,
        "cover_status": "ok",
        "cover_path": cover_rel,
        "cover_size": len(cover_bytes),
    }


@router.post("/sessions/{session_id}/roms/{rom_id}/cover/regenerate")
async def regenerate_cover(session_id: str, rom_id: str) -> dict:
    """Re-attempt art fetch + cover generation for a ROM (best-effort).

    Useful when the original upload failed to get artwork (cover_status='none'
    or 'failed'). Does not raise on failure — returns the new status instead.
    """
    with db.connect() as conn:
        require_session(conn, session_id)
        rom = _require_rom(conn, session_id, rom_id)

    system_key: str = rom["system_key"]
    try:
        sys_obj = get_system(system_key)
    except KeyError:
        raise HTTPException(status_code=500, detail=f"Unknown system key: {system_key}")

    rom_abs = storage.session_root(session_id) / rom["rom_path"]
    meta = metadata.resolve_metadata(system_key, rom["original_name"])

    cover_bytes: bytes | None = None
    try:
        if sys_obj.pico8:
            cover_bytes = covers_pico8.render_pico8_cover(rom_abs)
        elif meta.art_url:
            art = await artfetch.fetch_image(meta.art_url)
            if art:
                cover_bytes = _render_cover(rom, art)
    except covers.CoverError:
        cover_bytes = None

    if cover_bytes:
        cover_rel = _save_cover(session_id, rom, cover_bytes, art if not sys_obj.pico8 else None)
        with db.connect() as conn:
            _update_cover_db(conn, rom_id, cover_rel, "ok", "auto")
        return {"rom_id": rom_id, "cover_status": "ok", "cover_path": cover_rel}

    # best-effort: mark failed if previously none so callers know we tried
    new_status = "failed" if rom["cover_status"] == "none" else rom["cover_status"]
    with db.connect() as conn:
        conn.execute(
            "UPDATE roms SET cover_status = ? WHERE id = ?",
            (new_status, rom_id),
        )
    return {"rom_id": rom_id, "cover_status": new_status, "cover_path": rom.get("cover_path")}


# No-Intro region/dump tags — these live in filename parens but are NOT titles.
_REGION_WORD = re.compile(
    r"^(japan|usa|world|europe|korea|asia|france|germany|spain|italy|netherlands|"
    r"sweden|australia|brazil|china|taiwan|unl|proto|beta|sample|demo|pd|rev\b.*|"
    r"en|jp|us|eu|ko|j|u|e|k)$", re.I)


def _is_region_tag(s: str) -> bool:
    """True when a parenthetical is only region/dump markers (Japan, USA,
    World, 'Japan, USA', Korea-patch …) rather than an English game title."""
    parts = [p.strip() for p in re.split(r"[,/]", s) if p.strip()]
    return bool(parts) and all(_REGION_WORD.match(p) for p in parts)


def _strip_tags(stem: str) -> str:
    return re.sub(r"\s*[\(\[][^)\]]*[\)\]]", "", stem).strip(" -._")


def _search_term(korean: str | None, stored: str) -> str:
    """Best English search term. The '한글 (English)' convention only holds when
    the part BEFORE the parens actually contains Hangul — otherwise the parens
    hold a region tag like '(Japan)' (NOT a title), so we use the latin stem
    instead. Checking for Hangul (not "no latin at all") matters because a
    Korean title can itself carry a trailing Latin abbreviation — "파이널 파이트
    CD (Final Fight CD)" — and a plain "no latin" check would wrongly treat that
    prefix as a latin stem and miss the real English title in the parens."""
    stem = stored.rsplit(".", 1)[0]
    m = re.search(r"\(([A-Za-z0-9][^)]*)\)", stem)
    if m and _HANGUL.search(stem[:m.start()]) and not _is_region_tag(m.group(1)):
        return m.group(1).strip()
    base = _strip_tags(stem)          # drop trailing (Japan)/[!]/(Rev 1) tags
    if _has_searchable(base):          # latin OR numeric title (e.g. "1942")
        return base
    return korean or stem


def _term_variants(term: str) -> list[str]:
    """Progressively looser ENGLISH queries to raise the scraper hit rate:
      - the full title
      - alt title before a '~' separator  (Sonic 3D Blast ~ Flickies → Sonic 3D Blast)
      - ', The'/', A' article moved to front + bare  (Story of Thor, The → The Story of Thor)
      - without the ' - subtitle'  (… - Hikari o Tsugumono → …)
      - with bracket/paren tags stripped  (Banana (VTech…) → Banana)
    """
    out: list[str] = []
    def add(t: str) -> None:
        t = re.sub(r"\s+", " ", t).strip(" -:~'")
        if t and t not in out:
            out.append(t)
    add(term)
    if "~" in term:                       # "Bare Knuckle ~ Streets of Rage"
        for part in term.split("~"):      # → try BOTH localized titles
            add(part)
    art = re.match(r"^(.*),\s+(The|A|An)\b(.*)$", term, re.I)
    if art:
        add(f"{art.group(2)} {art.group(1)}{art.group(3)}")
        add(f"{art.group(1)}{art.group(3)}")
    if " - " in term:
        add(term.split(" - ")[0])
    add(re.sub(r"[\(\[].*?[\)\]]", " ", term))
    return out


_ROM_EXT = re.compile(r"\.(nes|fds|gb|gbc|gg|sms|md|gen|bin|pce|col|sg|rom|mx1|mx2|"
                      r"dsk|cdk|a26|a78|wsv|sv|min|gw|mgw|p8|zip|7z)$", re.I)


def _clean_original(name: str) -> str:
    """Strip noise from an uploaded filename to get a searchable romaji title:
    drop extension, parenthetical tags ((Korea-patch …)/(Japan)/[!]), version
    tokens, the '한글_' prefix and J-K patch markers."""
    s = _ROM_EXT.sub("", name or "")
    s = re.sub(r"[\(\[].*?[\)\]]", " ", s)        # (Korea-patch …), (Japan), [!]
    s = re.sub(r"\bv?\d{6,}\w*", " ", s)           # version tokens like v20160324
    s = re.sub(r"한글[_\s]*", " ", s)              # Korean-patch prefix
    s = re.sub(r"\bJ-?K\b", " ", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" -._")


def _has_latin(s: str) -> bool:
    return bool(re.search(r"[A-Za-z]", s or ""))


def _has_searchable(s: str) -> bool:
    """A usable English/scraper query: has Latin letters, OR is a numeric-only
    title like '1942'/'1943' (digits, no Hangul) — those have no Korean form and
    ARE searchable, but the letters-only check used to drop them."""
    s = s or ""
    if re.search(r"[A-Za-z]", s):
        return True
    return bool(re.search(r"[0-9]", s)) and not _HANGUL.search(s)


def _rom_terms(rom: dict) -> list[str]:
    """Ordered, de-duped ENGLISH/romaji search candidates for a ROM: the English
    title in the stored '한글 (English)' name, plus the cleaned ORIGINAL upload
    name (often romaji even when the display name is Korean), plus looser forms.
    Returns [] when nothing latin is available (→ caller can web-search instead)."""
    out: list[str] = []
    def add(t: str) -> None:
        t = re.sub(r"\s+", " ", t or "").strip(" -:._")
        if t and _has_searchable(t) and not _is_region_tag(t) and t not in out:
            out.append(t)
    add(_search_term(rom.get("korean_name"), rom["stored_name"]))
    add(_clean_original(rom.get("original_name") or ""))
    for base in list(out):
        for v in _term_variants(base):
            add(v)
    return out


# libretro-thumbnails files are named by No-Intro set name → probe common region
# tags. Keyless/immediate (raw.githubusercontent) — our free fallback source.
_LIBRETRO_REGIONS = ("(USA)", "(World)", "(USA, Europe)", "(Europe)", "(Japan, USA)", "(Japan)", "")


async def _libretro_probe(system_key: str, terms: list[str]) -> bytes | None:
    """Try libretro-thumbnails box art (No-Intro-keyed). Probes each candidate
    title × common region tag. Keyless/immediate (raw.githubusercontent), great
    coverage for Sega/retro systems IGDB & TheGamesDB miss. None if nothing hits."""
    if not metadata._LIBRETRO_REPO.get(system_key):
        return None
    seen: set[str] = set()
    for base in terms[:3]:
        for region in _LIBRETRO_REGIONS:
            stem = f"{base} {region}".strip()
            url = metadata._libretro_url(system_key, "Named_Boxarts", stem)
            if not url or url in seen:
                continue
            seen.add(url)
            raw = await artfetch.fetch_image(url)
            if raw:
                return raw
    return None


@router.post("/sessions/{session_id}/autocover")
async def autocover(session_id: str, payload: dict = Body(default={})) -> dict:
    """Batch-fetch covers from IGDB. By default only fills roms that still lack a
    cover. With force=1 it RE-fetches every auto cover too (regenerating the .img
    AND the high-res WebP preview) — but NEVER touches a 'manual' cover the user
    set by hand. Scoped to a system when given."""
    system = payload.get("system")
    force = bool(payload.get("force"))
    limit = min(int(payload.get("limit", 60)), 600)
    with db.connect() as conn:
        require_session(conn, session_id)
        # force → everything EXCEPT user-set covers (uploaded 'manual' or hand-
        # cropped 'crop'); normal → only the ones still missing a cover.
        cover_filter = (
            "(cover_source IS NULL OR cover_source NOT IN ('manual','crop'))"
            if force else "cover_status != 'ok'"
        )
        sql = f"SELECT * FROM roms WHERE session_id = ? AND {cover_filter}"
        args = [session_id]
        if system:
            sql += " AND system_key = ?"
            args.append(system)
        rows = [dict(r) for r in conn.execute(sql + " LIMIT ?", (*args, limit)).fetchall()]

    covered = 0
    for rom in rows:
        if await autofill_rom(session_id, rom):
            covered += 1
    return {"checked": len(rows), "covered": covered, "force": force}


async def autofill_rom(session_id: str, rom: dict) -> bool:
    """Fetch ONE rom's cover from IGDB → TheGamesDB (title-matched so a fuzzy hit
    can't stamp the wrong art) and save it. Returns True if a cover was set.
    Pico-8 is skipped (its cover comes from the .p8 cart). Reusable by autocover
    AND by the background auto-fill that runs right after an upload."""
    if get_system(rom["system_key"]).pico8:
        return False
    terms = _rom_terms(rom)   # English/romaji candidates (stored + original name)
    raw = None
    for cand in terms:        # 1) IGDB — only accept a result whose name matches
        res = await igdb.search_covers(cand, rom["system_key"], limit=8)
        items = res.get("results") or []
        hit = titlematch.best(cand, [(it["name"], it["cover_url"]) for it in items
                                     if it.get("name") and it.get("cover_url")])
        if hit:
            raw = await artfetch.fetch_image(hit[1])
            if raw:
                break
    if not raw:               # 2) TheGamesDB box art, same title-match guard
        for cand in terms:
            cands = await tgdb.cover_candidates(cand, rom["system_key"])
            hit = titlematch.best(cand, cands)
            if hit:
                raw = await artfetch.fetch_image(hit[1])
                if raw:
                    break
    if not raw:               # 3) libretro-thumbnails (No-Intro keyed, keyless) —
        raw = await _libretro_probe(rom["system_key"], terms)   # covers Sega/retro gaps
    if not raw:               # 4) IGDB WITHOUT the platform filter — IGDB frequently
        for cand in terms:    #    fails to tag MSX/SMS/Famicom games with the platform
            res = await igdb.search_covers(cand, None, limit=8)  #    yet HAS the game.
            items = res.get("results") or []                      #    Title-matched → right
            hit = titlematch.best(cand, [(it["name"], it["cover_url"]) for it in items  # game,
                                         if it.get("name") and it.get("cover_url")])     # maybe
            if hit:                                               #    another platform's art.
                raw = await artfetch.fetch_image(hit[1])
                if raw:
                    break
    if not raw:               # 5) TheGamesDB without platform filter (same gap)
        for cand in terms:
            cands = await tgdb.cover_candidates(cand, "")   # "" → no platform filter
            hit = titlematch.best(cand, cands)
            if hit:
                raw = await artfetch.fetch_image(hit[1])
                if raw:
                    break
    if not raw:
        return False
    try:
        cover_bytes = _render_cover(rom, raw)
    except covers.CoverError:
        return False
    cover_rel = _save_cover(session_id, rom, cover_bytes, raw)
    with db.connect() as conn:
        _update_cover_db(conn, rom["id"], cover_rel, "ok", "auto")
    return True


@router.post("/sessions/{session_id}/autoresolve")
async def autoresolve(session_id: str, payload: dict = Body(default={})) -> dict:
    """For roms still WITHOUT a Korean name: ask IGDB. If it has a Korean
    alternative name → rename to 'Korean (English)'. Also fills missing covers.
    Returns counts + the list IGDB couldn't find at all (→ need another source)."""
    require_korean_mode()
    system = payload.get("system")
    limit = min(int(payload.get("limit", 80)), 300)
    with db.connect() as conn:
        require_session(conn, session_id)
        sql = "SELECT * FROM roms WHERE session_id = ?"
        args = [session_id]
        if system:
            sql += " AND system_key = ?"
            args.append(system)
        rows = [dict(r) for r in conn.execute(sql, args).fetchall()]

    targets = [r for r in rows
               if not _HANGUL.search(r["stored_name"]) and not get_system(r["system_key"]).pico8][:limit]
    renamed = covered = 0
    missing: list[str] = []
    for rom in targets:
        term = _search_term(rom.get("korean_name"), rom["stored_name"])
        res = await igdb.resolve(term, rom["system_key"])
        if not res:
            missing.append(rom["stored_name"])
            continue
        if res.get("korean"):                       # IGDB had a Korean name → rename
            base = gamelist.compose_name(res["korean"], res.get("name") or term)
            ext = rom["stored_name"].rsplit(".", 1)[-1] if "." in rom["stored_name"] else ""
            new = f"{storage.safe_name(base)}.{ext}" if ext else storage.safe_name(base)
            with db.connect() as conn:
                row = conn.execute(
                    "SELECT id, system_key, stored_name, rom_path, cover_path FROM roms WHERE id = ?",
                    (rom["id"],)).fetchone()
                if row and new != row["stored_name"]:
                    upd = renames.rename_rom(conn, session_id, dict(row), new, suffix_on_clash=True)
                    rom.update(stored_name=upd["stored_name"], rom_path=upd["rom_path"],
                               cover_path=upd["cover_path"])
                    name_index.store(conn, name_index.hash_file(storage.session_root(session_id) / upd["rom_path"]),
                                     rom["system_key"], base, "igdb")
                    renamed += 1
        if (rom["cover_status"] != "ok" and res.get("cover_url")
                and titlematch.matches(term, res.get("name") or "")):   # fill cover
            raw = await artfetch.fetch_image(res["cover_url"])
            if raw:
                try:
                    cb = _render_cover(rom, raw)
                except covers.CoverError:
                    cb = None
                if cb:
                    rel = _save_cover(session_id, rom, cb, raw)
                    with db.connect() as conn:
                        _update_cover_db(conn, rom["id"], rel, "ok", "auto")
                    covered += 1
    return {"checked": len(targets), "renamed": renamed, "covered": covered,
            "missing_count": len(missing), "missing": missing[:300]}


@router.delete("/sessions/{session_id}/roms/{rom_id}/cover")
def delete_cover(session_id: str, rom_id: str) -> dict:
    """Remove ONLY the cover (device .img + web preview), keep the ROM — so you can
    re-fill it (auto-cover / search / upload)."""
    with db.connect() as conn:
        require_session(conn, session_id)
        rom = _require_rom(conn, session_id, rom_id)
        cover_abs = _cover_abs(session_id, rom)
        if cover_abs:
            cover_abs.unlink(missing_ok=True)
        _preview_path(session_id, rom).unlink(missing_ok=True)
        conn.execute(
            "UPDATE roms SET cover_path = NULL, cover_status = 'none' WHERE id = ?",
            (rom_id,),
        )
    return {"rom_id": rom_id, "cover_status": "none"}


@router.post("/sessions/{session_id}/roms/{rom_id}/cover/recrop")
def recrop_cover(session_id: str, rom_id: str, payload: dict = Body(default={})) -> dict:
    """Re-pick the region that goes on the DEVICE — no re-download. Crops the
    stored full-art preview and writes ONLY the device .img. The web preview (the
    ORIGINAL full art) is NEVER modified, so you can always re-crop differently or
    keep the original. crop=null → reset the device img to fit-within. Marks the
    cover 'manual' so the crop choice isn't auto-overwritten."""
    crop = _parse_crop(payload.get("crop"))
    with db.connect() as conn:
        require_session(conn, session_id)
        rom = _require_rom(conn, session_id, rom_id)
    if rom["cover_status"] != "ok":
        raise HTTPException(status_code=400, detail="먼저 커버를 설정하세요")

    preview = _preview_path(session_id, rom)
    cover_abs = _cover_abs(session_id, rom)
    src_path = preview if preview.exists() else cover_abs
    if src_path is None or not src_path.exists():
        raise HTTPException(status_code=404, detail="원본 이미지를 찾을 수 없습니다")
    src = src_path.read_bytes()

    try:
        cover_bytes = _render_cover(rom, src, crop_box=crop)
    except covers.CoverError as exc:
        raise HTTPException(status_code=422, detail=f"이미지 처리 실패: {exc}") from exc

    cover_rel = _save_cover(session_id, rom, cover_bytes)   # device .img ONLY; preview untouched
    with db.connect() as conn:
        # 'crop' = device img hand-cropped from the kept original → distinguishable
        # from 'manual' (uploaded) and protected from force re-fetch.
        _update_cover_db(conn, rom_id, cover_rel, "ok", "crop", crop)
    return {"rom_id": rom_id, "cover_status": "ok", "cover_path": cover_rel}


@router.patch("/sessions/{session_id}/roms/{rom_id}/cover/flag")
def set_cover_flag(session_id: str, rom_id: str, payload: dict = Body(...)) -> dict:
    """Set the cover's corner flag/country EXPLICITLY (independent of the
    Korean-patch toggle). Body: {"cover_flag": "ko"|"ja"|...|null}. null/"" clears
    it. Re-bakes the device .img so the baked flag updates; the web preview /
    original is never touched."""
    if "cover_flag" not in payload:
        raise HTTPException(status_code=400, detail="cover_flag 값이 필요합니다")
    raw = payload["cover_flag"]
    flag = (raw or "").strip().lower() or None
    if flag is not None and flag not in covers.FLAG_CODES:
        raise HTTPException(status_code=400,
                            detail=f"지원하지 않는 국기: {flag} (가능: {sorted(covers.FLAG_CODES)})")
    with db.connect() as conn:
        require_session(conn, session_id)
        rom = _require_rom(conn, session_id, rom_id)
        conn.execute("UPDATE roms SET cover_flag = ? WHERE id = ?", (flag, rom_id))
        rom["cover_flag"] = flag
    rebaked = rebake_cover_img(session_id, rom)   # update the baked .img if a cover exists
    return {"rom_id": rom_id, "cover_flag": flag, "rebaked": rebaked}


@router.post("/sessions/{session_id}/roms/{rom_id}/cover/from-url")
async def cover_from_url(session_id: str, rom_id: str, payload: dict = Body(...)) -> dict:
    """Set the cover from an image URL (e.g. an IGDB cover picked in the popup).
    Fetches, runs render_cover (186x100 .img), overwrites, cover_status='ok'."""
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url required")

    with db.connect() as conn:
        require_session(conn, session_id)
        rom = _require_rom(conn, session_id, rom_id)

    raw = await artfetch.fetch_image(url)
    if not raw:
        raise HTTPException(status_code=422, detail="이미지를 가져오지 못했습니다")
    crop_box = _parse_crop(payload.get("crop"))
    try:
        cover_bytes = _render_cover(rom, raw, crop_box=crop_box)
    except covers.CoverError as exc:
        raise HTTPException(status_code=422, detail=f"이미지 처리 실패: {exc}") from exc

    cover_rel = _save_cover(session_id, rom, cover_bytes, raw)
    with db.connect() as conn:
        _update_cover_db(conn, rom_id, cover_rel, "ok", "manual", crop_box)
    return {"rom_id": rom_id, "cover_status": "ok", "cover_path": cover_rel}


@router.post("/sessions/{session_id}/roms/{rom_id}/igdb-meta")
async def fetch_igdb_meta(session_id: str, rom_id: str) -> dict:
    """Fetch rich IGDB detail for ONE rom (release date, genres, developer,
    rating, summary, screenshots, videos), title-matched so a fuzzy hit can't
    attach the wrong game, and cache it as JSON on the row."""
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute("SELECT * FROM roms WHERE id=? AND session_id=?",
                            (rom_id, session_id)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="ROM을 찾을 수 없습니다")
        rom = dict(row)

    meta = None
    for cand in _rom_terms(rom):
        metas = await igdb.fetch_meta(cand, rom["system_key"])
        if not metas:                                   # IGDB platform-tag gap: retry unfiltered
            metas = await igdb.fetch_meta(cand, None)
        hit = titlematch.best(cand, [(m["name"], m) for m in metas if m.get("name")])
        if hit:
            meta = hit[1]
            break
    if meta is None:
        raise HTTPException(status_code=404, detail="IGDB에서 정보를 찾지 못했습니다")

    with db.connect() as conn:
        conn.execute("UPDATE roms SET igdb_meta=? WHERE id=?",
                     (json.dumps(meta, ensure_ascii=False), rom_id))
    return meta


@router.get("/sessions/{session_id}/roms/{rom_id}/igdb-meta")
def get_igdb_meta(session_id: str, rom_id: str) -> dict:
    """Return the cached IGDB detail for a rom (or {} if never fetched). Kept out
    of the library list to keep that payload lean — loaded when a detail opens."""
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute("SELECT igdb_meta FROM roms WHERE id=? AND session_id=?",
                            (rom_id, session_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="ROM을 찾을 수 없습니다")
    try:
        return json.loads(row[0]) if row[0] else {}
    except (ValueError, TypeError):
        return {}
