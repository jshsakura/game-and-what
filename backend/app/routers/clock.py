"""The firmware Clock app's three media folders, as a library.

The device's Clock app reads /clock/gif (background GIFs), /clock/album (320×240
photos) and /clock/alarm (the sound it rings). This router keeps all three in the
session library — listed, previewable, renameable, and packed into the SD zip —
so a converted background is not something that exists only in the browser's
Downloads folder.

Who converts what, and why:

* gif   — the SERVER converts (ffmpeg palette/fps/gifsicle ladder). Any image or
          video goes in; a 320×240 GIF inside the device's byte budget comes out.
* album — the BROWSER converts. A .565 is raw RGB565 with no header, so the
          canvas that previews the crop already IS the output; sending pixels
          through a server round-trip could only make them different. We store
          the bytes it produced (and render a PNG for the web preview, since no
          browser can display a headerless .565).
* alarm — the BROWSER converts (ffmpeg.wasm, mono 48 kHz MP3). Same reasoning:
          the clip the user auditions is the file the device loops.

POST /api/clock/background stays stateless on purpose: convert, download, keep
nothing — for the one-off you are about to drag onto the card yourself.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .. import config, db
from ..services import storage, video
from .sessions import require_session

router = APIRouter(prefix="/api", tags=["clock"])

# Per-kind rules. `suffixes` = what may be uploaded (first one is the default the
# stored name gets); `media_type` = how it is served back inline.
KIND_RULES = {
    "gif":   {"suffixes": (".gif",), "media_type": "image/gif", "fallback": "bg"},
    "album": {"suffixes": (".565", ".bmp"), "media_type": "application/octet-stream",
              "fallback": "photo"},
    "alarm": {"suffixes": (".mp3",), "media_type": "audio/mpeg", "fallback": "alarm"},
}
# A .565 is exactly one screen of raw RGB565 — no header, no padding. Anything of
# a different length is not a clock photo, whatever it is called.
ALBUM_RAW_BYTES = video.SCREEN_WIDTH * video.SCREEN_HEIGHT * 2


def _require_kind(kind: str) -> dict:
    if kind not in KIND_RULES:
        raise HTTPException(status_code=404, detail=f"Unknown clock folder '{kind}'")
    return KIND_RULES[kind]


def _parse_crop(raw: str | None) -> video.ClockCrop | None:
    """Validate the cropper's fraction rectangle ("x,y,w,h", fractions of the
    source frame). Malformed or outside the frame → None (falls back to fit)."""
    if not raw:
        return None
    try:
        x, y, w, h = (float(v) for v in raw.split(","))
    except ValueError:
        return None
    eps = 0.001   # cropper rounding slack
    if w <= 0 or h <= 0 or x < -eps or y < -eps or x + w > 1 + eps or y + h > 1 + eps:
        return None
    x, y = max(x, 0.0), max(y, 0.0)
    return (x, y, min(w, 1.0 - x), min(h, 1.0 - y))


def _stem(name: str, fallback: str) -> str:
    """A safe filename stem from whatever the user typed or uploaded. Falls back
    to the kind's default name when nothing meaningful survives sanitising — a
    name made only of the underscores safe_name substituted in ('???' → '___')
    carries nothing, so the device default beats it."""
    stem = storage.safe_name(Path(name or "").stem).strip()
    return stem if stem.strip("_-. ") else fallback


def _is_animated(path: Path) -> bool:
    """Does the encoded GIF have more than one frame? A still source becomes a
    1-frame background, and the list says which is which. Unreadable → assume
    animated (the common case; nothing depends on this but a badge)."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return bool(getattr(im, "is_animated", False))
    except Exception:
        return True


def _render_album_png(src: Path, dst: Path) -> bool:
    """Render a stored album photo to PNG for the web list. A .565 is raw RGB565
    little-endian (Pillow's 'BGR;16'), exactly what the browser canvas wrote; a
    .bmp just gets re-encoded. False if it can't be read."""
    try:
        from PIL import Image
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower() == ".565":
            data = src.read_bytes()
            if len(data) != ALBUM_RAW_BYTES:
                return False
            im = Image.frombytes("RGB", (video.SCREEN_WIDTH, video.SCREEN_HEIGHT),
                                 data, "raw", "BGR;16")
        else:
            im = Image.open(src).convert("RGB")
        im.save(dst, "PNG")
        return True
    except Exception:
        return False


async def _convert_gif(file: UploadFile, mode: str, crop: str) -> tuple[Path, Path, int]:
    """Shared front half of both GIF paths: validate, convert into a throwaway
    workspace. Returns (work_dir, gif_path, source_bytes) — the CALLER owns the
    workspace and must remove it."""
    crop_box = _parse_crop(crop)
    if mode not in video.CLOCK_FIT_MODES or (mode == "custom" and crop_box is None):
        mode = video.DEFAULT_FIT_MODE
    if not video.ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg is not installed on the server")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(data) > config.MAX_VIDEO_BYTES:
        raise HTTPException(status_code=413, detail="file too large")

    work = Path(tempfile.mkdtemp(prefix="clockbg_"))
    src = work / f"src_{storage.safe_name(Path(file.filename or 'input').name)}"
    out = work / "bg.gif"
    storage.write_bytes(src, data)
    try:
        await video.encode_to_clock_gif(src, out, mode=mode, crop=crop_box)
    except video.VideoEncodeError as exc:
        shutil.rmtree(work, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc))
    return work, out, len(data)


@router.post("/clock/background")
async def clock_background(
    file: UploadFile = File(...),
    mode: str = Form(video.DEFAULT_FIT_MODE),  # fit | fill | stretch | custom (user crop)
    crop: str = Form(""),                      # custom mode: "x,y,w,h" source fractions
) -> FileResponse:
    """Convert an uploaded image or video into a clock-ready bg.gif and return it
    as a download, storing nothing. A still image becomes a 1-frame static
    background; a video/GIF is length-capped and loops on-device. The temp
    workspace is removed once the response has been sent."""
    work, out, _ = await _convert_gif(file, mode, crop)
    # FileResponse streams `out`, then the background task tidies the workspace.
    return FileResponse(
        out, media_type="image/gif", filename="bg.gif",
        background=BackgroundTask(shutil.rmtree, work, ignore_errors=True),
    )


def _row(session_id: str, kind: str, file_id: str) -> dict:
    _require_kind(kind)
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            "SELECT * FROM clock_files WHERE id = ? AND session_id = ? AND kind = ?",
            (file_id, session_id, kind),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown clock {kind}")
    return dict(row)


def _insert(session_id: str, kind: str, dst: Path, original: str, *,
            source_bytes: int = 0, fit_mode: str | None = None,
            animated: bool = False, duration_s: float | None = None) -> dict:
    rel = storage.relative_to_session(session_id, dst)
    size_bytes = dst.stat().st_size
    file_id = storage.new_id()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO clock_files (id, session_id, kind, original_name, stored_name,
                                        file_path, size_bytes, source_bytes, fit_mode,
                                        animated, duration_s)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (file_id, session_id, kind, original, dst.name, rel, size_bytes,
             source_bytes, fit_mode, int(animated), duration_s),
        )
    return {
        "id": file_id, "kind": kind, "original_name": original, "stored_name": dst.name,
        "file_path": rel, "size_bytes": size_bytes, "source_bytes": source_bytes,
        "fit_mode": fit_mode, "animated": int(animated), "duration_s": duration_s,
    }


@router.post("/sessions/{session_id}/clock/{kind}")
async def save_clock_file(
    session_id: str,
    kind: str,                                 # gif | album | alarm
    file: UploadFile = File(...),
    mode: str = Form(video.DEFAULT_FIT_MODE),  # gif/album: how the source was framed
    crop: str = Form(""),                      # gif custom mode: "x,y,w,h" source fractions
    name: str = Form(""),                      # optional output name (default: source stem)
    seconds: float = Form(0.0),                # alarm: clip length, for the list read-out
) -> dict:
    """Keep a clock file in the library under /clock/<kind>.

    A GIF is converted here (see _convert_gif); album photos and alarm sounds
    arrive already converted by the browser and are stored as they are — the
    upload IS the device file, so re-encoding it server-side could only degrade
    it."""
    rules = _require_kind(kind)
    with db.connect() as conn:
        require_session(conn, session_id)

    original = storage.nfc(file.filename) or rules["fallback"]
    target = storage.clock_dir(session_id, kind)
    target.mkdir(parents=True, exist_ok=True)

    if kind == "gif":
        work, out, source_bytes = await _convert_gif(file, mode, crop)
        try:
            stored = storage.unique_name(target, _stem(name or original, rules["fallback"]), ".gif")
            dst = target / stored
            shutil.move(str(out), dst)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return _insert(session_id, kind, dst, original, source_bytes=source_bytes,
                       fit_mode=mode, animated=_is_animated(dst))

    suffix = Path(original).suffix.lower()
    if suffix not in rules["suffixes"]:
        raise HTTPException(
            status_code=415,
            detail=f"/clock/{kind} takes {' or '.join(rules['suffixes'])} — convert it first",
        )
    limit = config.MAX_CLOCK_IMAGE_BYTES if kind == "album" else config.MAX_MUSIC_BYTES
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(data) > limit:
        raise HTTPException(status_code=413, detail="file too large")
    if suffix == ".565" and len(data) != ALBUM_RAW_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"a .565 photo is exactly {ALBUM_RAW_BYTES} bytes "
                   f"({video.SCREEN_WIDTH}×{video.SCREEN_HEIGHT} RGB565), got {len(data)}",
        )

    stored = storage.unique_name(target, _stem(name or original, rules["fallback"]), suffix)
    dst = storage.write_bytes(target / stored, data)
    return _insert(session_id, kind, dst, original,
                   fit_mode=mode if kind == "album" else None,
                   duration_s=seconds or None)


@router.patch("/sessions/{session_id}/clock/{kind}/{file_id}")
def rename_clock_file(session_id: str, kind: str, file_id: str, payload: dict = Body(...)) -> dict:
    """Rename a stored file, keeping its extension. Names matter on the device:
    the Clock app picks bg.gif as its default background and alarm.mp3 as its
    default ring, so promoting one of several to that name is the whole point of
    being able to rename."""
    rules = _require_kind(kind)
    row = _row(session_id, kind, file_id)
    suffix = Path(row["stored_name"]).suffix or rules["suffixes"][0]
    stored_name = f"{_stem(payload.get('name') or '', rules['fallback'])}{suffix}"
    if stored_name == row["stored_name"]:
        return {"id": file_id, "stored_name": stored_name, "file_path": row["file_path"]}

    target = storage.clock_dir(session_id, kind)
    if (target / stored_name).exists():
        raise HTTPException(status_code=409, detail=f"'{stored_name}' already exists")
    src = storage.session_root(session_id) / row["file_path"]
    if not src.exists():
        raise HTTPException(status_code=404, detail="File missing from disk")
    src.replace(target / stored_name)

    rel = storage.relative_to_session(session_id, target / stored_name)
    with db.connect() as conn:
        conn.execute(
            "UPDATE clock_files SET stored_name = ?, file_path = ? WHERE id = ?",
            (stored_name, rel, file_id),
        )
    return {"id": file_id, "stored_name": stored_name, "file_path": rel}


@router.delete("/sessions/{session_id}/clock/{kind}/{file_id}")
def delete_clock_file(session_id: str, kind: str, file_id: str) -> dict:
    """Remove a stored clock file (to _trash, so it stays recoverable) + its row."""
    row = _row(session_id, kind, file_id)
    storage.move_to_trash(session_id, row["file_path"])
    storage.clock_preview_path(session_id, file_id).unlink(missing_ok=True)
    with db.connect() as conn:
        conn.execute("DELETE FROM clock_files WHERE id = ?", (file_id,))
    return {"deleted": file_id}


@router.get("/sessions/{session_id}/clock/{kind}/{file_id}/file")
def serve_clock_file(session_id: str, kind: str, file_id: str) -> FileResponse:
    """The stored file itself, inline. For a GIF this IS the preview (320×240 and
    animated, exactly what the device shows); for an alarm it feeds the player
    (FileResponse honours Range, so scrubbing works)."""
    rules = _require_kind(kind)
    row = _row(session_id, kind, file_id)
    path = storage.session_root(session_id) / row["file_path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing from disk")
    return FileResponse(path, media_type=rules["media_type"],
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/sessions/{session_id}/clock/{kind}/{file_id}/preview")
def preview_clock_file(session_id: str, kind: str, file_id: str) -> FileResponse:
    """PNG render of an album photo, built and cached on first request. Only the
    album needs it — a headerless .565 is nothing a browser can display."""
    row = _row(session_id, kind, file_id)
    if kind != "album":
        raise HTTPException(status_code=404, detail="no preview for this kind")
    png = storage.clock_preview_path(session_id, file_id)
    if not png.exists():
        src = storage.session_root(session_id) / row["file_path"]
        if not src.exists() or not _render_album_png(src, png):
            raise HTTPException(status_code=404, detail="preview failed")
    return FileResponse(png, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/sessions/{session_id}/clock/{kind}/{file_id}/download")
def download_clock_file(session_id: str, kind: str, file_id: str) -> FileResponse:
    """Download a stored file under its on-SD filename."""
    rules = _require_kind(kind)
    row = _row(session_id, kind, file_id)
    path = storage.session_root(session_id) / row["file_path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing from disk")
    name = row["stored_name"]
    # Korean (non-latin-1) names crash a plain filename="…" header → RFC 5987.
    ascii_name = name.encode("ascii", "ignore").decode().strip() or f"clock{rules['suffixes'][0]}"
    return FileResponse(
        path, media_type=rules["media_type"],
        headers={"Content-Disposition":
                 f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"},
    )
