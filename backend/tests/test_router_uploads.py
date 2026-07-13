# -*- coding: utf-8 -*-
"""app/routers/uploads.py (chunked/resumable ROM+video upload pipeline),
app/routers/extra.py (passthrough "extra" files → SD root, path sanitization)
and app/routers/firmware.py (single retro-go_update.bin slot).

Pinned behaviour:
  - uploads.py only exposes the CHUNKED flow (init → PUT chunk → GET status →
    POST complete); there is no direct single/multipart ROM-upload endpoint in
    this file (that lives in routers/roms.py, out of scope here). Every branch
    below is driven end to end through `client` except `_run_encode`: it is
    scheduled via `asyncio.create_task` (fire-and-forget) inside
    `complete_upload`, so the request returns before it necessarily finishes —
    exercising its RUN-TO-COMPLETION behaviour deterministically (success /
    VideoEncodeError cleanup) requires calling it directly rather than racing
    a background task against test teardown.
  - Real .env for this deploy sets GNW_EXPERIMENTAL_MODE=true (personal lab),
    so every experimental-mode-sensitive test below explicitly monkeypatches
    `config.EXPERIMENTAL_MODE` rather than relying on its default (same
    approach as test_app_core.py / test_experimental_mode.py).
  - Cover generation network calls (`artfetch.fetch_image`) and image encoding
    (`covers.render_cover` / `covers_pico8.render_pico8_cover`) are mocked at
    the service boundary — `no_network` would otherwise blow up any real
    outbound HTTP, and we don't need real JPEG/WebP encoding to prove the
    router's control flow.
  - extra.py's `safe_rel_path` is the security-relevant boundary: path
    traversal segments ('..', '.') and absolute-path leading empties are
    dropped per-segment, never merely rejected, so a POST body path like
    "../../../etc/passwd" resolves to "etc/passwd" *inside* the session's
    `_extra` dir — pinned explicitly below.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app import config, db
from app.routers import uploads
from app.routers.extra import safe_rel_path
from app.services import artfetch, covers, jobs, metadata, storage
from app.services import covers_pico8 as covers_pico8_service
from app.services import video as video_service


# ── shared helpers ───────────────────────────────────────────────────────────

def _init(client, session_id, filename, total_size, kind="rom", system=None):
    body = {"filename": filename, "total_size": total_size, "kind": kind}
    if system is not None:
        body["system"] = system
    return client.post(f"/api/sessions/{session_id}/uploads", json=body)


def _put_chunk(client, session_id, upload_id, index, data):
    return client.put(
        f"/api/sessions/{session_id}/uploads/{upload_id}/chunk",
        params={"index": index},
        files={"file": ("chunk.bin", data)},
    )


def _init_and_fill(client, session_id, filename, payload, kind="rom", system=None):
    """Init an upload and push `payload` in as a single chunk. Returns upload_id."""
    init = _init(client, session_id, filename, len(payload), kind=kind, system=system)
    assert init.status_code == 200, init.text
    upload_id = init.json()["upload_id"]
    chunk = _put_chunk(client, session_id, upload_id, 0, payload)
    assert chunk.status_code == 200, chunk.text
    return upload_id


def _upload_row(upload_id: str) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()
    return dict(row)


async def _fake_fetch_image(_url):
    return b"art-bytes"


def _mock_rom_cover_pipeline(monkeypatch, *, art: bool = True, cover_bytes: bytes | None = b"cover-bytes"):
    """Skip real network + image encoding for the rom-cover pipeline."""
    if art:
        monkeypatch.setattr(artfetch, "fetch_image", _fake_fetch_image)
    else:
        async def _no_art(_url):
            return None
        monkeypatch.setattr(artfetch, "fetch_image", _no_art)
    if cover_bytes is not None:
        monkeypatch.setattr(covers, "render_cover", lambda *a, **k: cover_bytes)


# ── init_upload ───────────────────────────────────────────────────────────────

def test_init_upload_rejects_unknown_session(client):
    r = _init(client, "no-such-session", "Game.nes", 10, kind="rom", system="nes")
    assert r.status_code == 404


def test_init_upload_rejects_invalid_kind(client, session_id):
    r = _init(client, session_id, "Game.nes", 10, kind="bogus")
    assert r.status_code == 400


@pytest.mark.parametrize("total_size", [0, -5])
def test_init_upload_rejects_non_positive_total_size(client, session_id, total_size):
    r = _init(client, session_id, "Game.nes", total_size, kind="rom", system="nes")
    assert r.status_code == 400


def test_init_upload_rejects_total_size_over_global_max(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_TOTAL_BYTES", 100)
    r = _init(client, session_id, "Game.nes", 1000, kind="rom", system="nes")
    assert r.status_code == 400


def test_init_upload_rom_requires_system(client, session_id):
    r = _init(client, session_id, "Game.nes", 10, kind="rom", system=None)
    assert r.status_code == 400
    assert "system is required" in r.json()["detail"]


def test_init_upload_rom_rejects_unknown_system(client, session_id):
    r = _init(client, session_id, "Game.nes", 10, kind="rom", system="not-a-system")
    assert r.status_code == 400


def test_init_upload_rom_rejects_experimental_system_when_flag_off(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    r = _init(client, session_id, "Game.ngp", 10, kind="rom", system="ngp")
    assert r.status_code == 403


def test_init_upload_rom_allows_experimental_system_when_flag_on(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    r = _init(client, session_id, "Game.ngp", 10, kind="rom", system="ngp")
    assert r.status_code == 200


def test_init_upload_rom_rejects_disallowed_extension(client, session_id):
    r = _init(client, session_id, "Game.exe", 10, kind="rom", system="nes")
    assert r.status_code == 400
    assert "extension" in r.json()["detail"]


def test_init_upload_rom_rejects_declared_size_over_rom_max(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "MAX_ROM_BYTES", 50)
    r = _init(client, session_id, "Game.nes", 51, kind="rom", system="nes")
    assert r.status_code == 400
    assert "exceeds maximum" in r.json()["detail"]


def test_init_upload_video_requires_experimental_mode(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    r = _init(client, session_id, "clip.mp4", 10, kind="video")
    assert r.status_code == 403


def test_init_upload_video_rejects_declared_size_over_video_max(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(config, "MAX_VIDEO_BYTES", 50)
    r = _init(client, session_id, "clip.mp4", 51, kind="video")
    assert r.status_code == 400


def test_init_upload_success_creates_receiving_row_and_empty_tmp_file(client, session_id):
    r = _init(client, session_id, "Game.nes", 10, kind="rom", system="nes")
    assert r.status_code == 200
    body = r.json()
    assert body["received"] == 0
    assert body["kind"] == "rom"

    row = _upload_row(body["upload_id"])
    assert row["status"] == "receiving"
    assert row["received"] == 0
    assert row["system_key"] == "nes"
    tmp_path = Path(row["tmp_path"])
    assert tmp_path.exists()
    assert tmp_path.read_bytes() == b""


# ── put_chunk ─────────────────────────────────────────────────────────────────

def test_put_chunk_rejects_unknown_session(client, session_id):
    upload_id = _init(client, session_id, "Game.nes", 10, kind="rom", system="nes").json()["upload_id"]
    r = _put_chunk(client, "no-such-session", upload_id, 0, b"1234")
    assert r.status_code == 404


def test_put_chunk_rejects_unknown_upload(client, session_id):
    r = _put_chunk(client, session_id, "no-such-upload", 0, b"1234")
    assert r.status_code == 404


def test_put_chunk_sequential_happy_path_and_completion_flag(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "MAX_CHUNK_BYTES", 4)
    payload = b"0123456789"  # 10 bytes -> chunks of 4, 4, 2
    upload_id = _init(client, session_id, "Game.nes", len(payload), kind="rom", system="nes").json()["upload_id"]

    r1 = _put_chunk(client, session_id, upload_id, 0, payload[0:4])
    assert r1.json() == {"upload_id": upload_id, "received": 4, "total_size": 10, "complete": False}

    r2 = _put_chunk(client, session_id, upload_id, 1, payload[4:8])
    assert r2.json()["received"] == 8
    assert r2.json()["complete"] is False

    r3 = _put_chunk(client, session_id, upload_id, 2, payload[8:10])
    assert r3.json()["received"] == 10
    assert r3.json()["complete"] is True

    tmp_path = Path(_upload_row(upload_id)["tmp_path"])
    assert tmp_path.read_bytes() == payload


def test_put_chunk_rejects_empty_chunk(client, session_id):
    upload_id = _init(client, session_id, "Game.nes", 10, kind="rom", system="nes").json()["upload_id"]
    r = _put_chunk(client, session_id, upload_id, 0, b"")
    assert r.status_code == 400


def test_put_chunk_rejects_chunk_larger_than_max_chunk_bytes(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "MAX_CHUNK_BYTES", 4)
    upload_id = _init(client, session_id, "Game.nes", 10, kind="rom", system="nes").json()["upload_id"]
    r = _put_chunk(client, session_id, upload_id, 0, b"12345")
    assert r.status_code == 413


def test_put_chunk_rejects_out_of_order_index(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "MAX_CHUNK_BYTES", 4)
    upload_id = _init(client, session_id, "Game.nes", 10, kind="rom", system="nes").json()["upload_id"]
    # index 1 implies offset 4, but 0 bytes have been received yet.
    r = _put_chunk(client, session_id, upload_id, 1, b"1234")
    assert r.status_code == 409


def test_put_chunk_rejects_chunk_that_would_exceed_declared_total(client, session_id):
    upload_id = _init(client, session_id, "Game.nes", 5, kind="rom", system="nes").json()["upload_id"]
    r = _put_chunk(client, session_id, upload_id, 0, b"123456")
    assert r.status_code == 400


def test_put_chunk_rejects_once_upload_no_longer_receiving(client, session_id, monkeypatch):
    _mock_rom_cover_pipeline(monkeypatch, art=False)
    upload_id = _init_and_fill(client, session_id, "Game.nes", b"12345", system="nes")
    complete = client.post(f"/api/sessions/{session_id}/uploads/{upload_id}/complete")
    assert complete.status_code == 200

    r = _put_chunk(client, session_id, upload_id, 0, b"more")
    assert r.status_code == 409


# ── get_upload_status ─────────────────────────────────────────────────────────

def test_get_upload_status_unknown_session(client, session_id):
    upload_id = _init(client, session_id, "Game.nes", 10, kind="rom", system="nes").json()["upload_id"]
    r = client.get(f"/api/sessions/no-such-session/uploads/{upload_id}")
    assert r.status_code == 404


def test_get_upload_status_unknown_upload(client, session_id):
    r = client.get(f"/api/sessions/{session_id}/uploads/no-such-upload")
    assert r.status_code == 404


def test_get_upload_status_reports_progress(client, session_id):
    upload_id = _init(client, session_id, "Game.nes", 10, kind="rom", system="nes").json()["upload_id"]
    _put_chunk(client, session_id, upload_id, 0, b"12345")

    r = client.get(f"/api/sessions/{session_id}/uploads/{upload_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["received"] == 5
    assert body["total_size"] == 10
    assert body["status"] == "receiving"
    assert body["complete"] is False


# ── complete_upload: cross-cutting error paths ────────────────────────────────

def test_complete_upload_rejects_unknown_session(client, session_id):
    upload_id = _init(client, session_id, "Game.nes", 5, kind="rom", system="nes").json()["upload_id"]
    r = client.post(f"/api/sessions/no-such-session/uploads/{upload_id}/complete")
    assert r.status_code == 404


def test_complete_upload_rejects_unknown_upload(client, session_id):
    r = client.post(f"/api/sessions/{session_id}/uploads/no-such-upload/complete")
    assert r.status_code == 404


def test_complete_upload_rejects_incomplete_bytes(client, session_id):
    upload_id = _init(client, session_id, "Game.nes", 10, kind="rom", system="nes").json()["upload_id"]
    _put_chunk(client, session_id, upload_id, 0, b"12345")  # only 5 of 10 bytes

    r = client.post(f"/api/sessions/{session_id}/uploads/{upload_id}/complete")
    assert r.status_code == 409


def test_complete_upload_returns_500_when_tmp_file_lost(client, session_id):
    upload_id = _init_and_fill(client, session_id, "Game.nes", b"12345", system="nes")
    Path(_upload_row(upload_id)["tmp_path"]).unlink()

    r = client.post(f"/api/sessions/{session_id}/uploads/{upload_id}/complete")
    assert r.status_code == 500
    # Never entered the try/except that flips status to 'failed'.
    assert _upload_row(upload_id)["status"] == "receiving"


def test_complete_upload_rejects_when_already_complete(client, session_id, monkeypatch):
    _mock_rom_cover_pipeline(monkeypatch, art=False)
    upload_id = _init_and_fill(client, session_id, "Game.nes", b"12345", system="nes")
    first = client.post(f"/api/sessions/{session_id}/uploads/{upload_id}/complete")
    assert first.status_code == 200

    second = client.post(f"/api/sessions/{session_id}/uploads/{upload_id}/complete")
    assert second.status_code == 409


def test_complete_upload_rom_finalize_error_marks_upload_failed_and_reraises(
    client, session_id, monkeypatch
):
    def _boom(*_a, **_k):
        raise RuntimeError("boom")
    monkeypatch.setattr(metadata, "resolve_metadata", _boom)

    upload_id = _init_and_fill(client, session_id, "Game.nes", b"12345", system="nes")
    tmp_path = Path(_upload_row(upload_id)["tmp_path"])
    assert tmp_path.exists()

    with pytest.raises(RuntimeError, match="boom"):
        client.post(f"/api/sessions/{session_id}/uploads/{upload_id}/complete")

    assert _upload_row(upload_id)["status"] == "failed"
    assert not tmp_path.exists()


# ── complete_upload: rom finalize (cover pipeline) ────────────────────────────

def test_complete_upload_rom_success_with_cover_art(client, session_id, monkeypatch):
    _mock_rom_cover_pipeline(monkeypatch, art=True, cover_bytes=b"cover-bytes")
    upload_id = _init_and_fill(client, session_id, "Mario.nes", b"nes-bytes", system="nes")

    r = client.post(f"/api/sessions/{session_id}/uploads/{upload_id}/complete")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["cover_status"] == "ok"
    assert body["stored_name"].endswith(".nes")

    with db.connect() as conn:
        rom = dict(conn.execute("SELECT * FROM roms WHERE id = ?", (body["rom_id"],)).fetchone())
    assert rom["cover_status"] == "ok"
    assert rom["cover_path"] is not None
    assert (storage.session_root(session_id) / rom["cover_path"]).read_bytes() == b"cover-bytes"
    assert (storage.session_root(session_id) / rom["rom_path"]).read_bytes() == b"nes-bytes"
    assert _upload_row(upload_id)["status"] == "complete"


def test_complete_upload_rom_no_art_url_yields_cover_status_none(client, session_id, monkeypatch):
    # "tama" has no libretro-thumbnails repo entry, so meta.art_url is None and
    # the pico8/art branches are never entered — no need to mock artfetch/covers.
    upload_id = _init_and_fill(client, session_id, "Game.b", b"tama-bytes", system="tama")

    r = client.post(f"/api/sessions/{session_id}/uploads/{upload_id}/complete")
    assert r.status_code == 200
    body = r.json()
    assert body["cover_status"] == "none"

    with db.connect() as conn:
        rom = dict(conn.execute("SELECT * FROM roms WHERE id = ?", (body["rom_id"],)).fetchone())
    assert rom["cover_path"] is None


def test_complete_upload_rom_missing_art_bytes_yields_cover_status_none(client, session_id, monkeypatch):
    _mock_rom_cover_pipeline(monkeypatch, art=False)  # fetch_image resolves to None
    upload_id = _init_and_fill(client, session_id, "Mario.nes", b"nes-bytes", system="nes")

    r = client.post(f"/api/sessions/{session_id}/uploads/{upload_id}/complete")
    assert r.status_code == 200
    assert r.json()["cover_status"] == "none"


def test_complete_upload_rom_cover_error_is_swallowed_as_status_none(client, session_id, monkeypatch):
    monkeypatch.setattr(artfetch, "fetch_image", _fake_fetch_image)

    def _raise_cover_error(*_a, **_k):
        raise covers.CoverError("bad crop")
    monkeypatch.setattr(covers, "render_cover", _raise_cover_error)

    upload_id = _init_and_fill(client, session_id, "Mario.nes", b"nes-bytes", system="nes")
    r = client.post(f"/api/sessions/{session_id}/uploads/{upload_id}/complete")
    assert r.status_code == 200
    assert r.json()["cover_status"] == "none"


def test_complete_upload_pico8_uses_pico8_cover_renderer(client, session_id, monkeypatch):
    monkeypatch.setattr(covers_pico8_service, "render_pico8_cover", lambda *_a, **_k: b"pico-cover")
    upload_id = _init_and_fill(client, session_id, "cart.p8", b"pico8-cart-bytes", system="pico8")

    r = client.post(f"/api/sessions/{session_id}/uploads/{upload_id}/complete")
    assert r.status_code == 200
    body = r.json()
    assert body["cover_status"] == "ok"

    with db.connect() as conn:
        rom = dict(conn.execute("SELECT * FROM roms WHERE id = ?", (body["rom_id"],)).fetchone())
    assert (storage.session_root(session_id) / rom["cover_path"]).read_bytes() == b"pico-cover"


def test_rom_stored_name_keeps_original_extension():
    meta = metadata.GameMeta(
        original_name="Mario", title="Mario Bros", korean_name=None,
        screenshot_url=None, boxart_url=None, source="none",
    )
    assert uploads._rom_stored_name(meta, "Mario.nes") == "Mario Bros.nes"


def test_rom_stored_name_handles_extensionless_original():
    meta = metadata.GameMeta(
        original_name="Cart", title="Cart Title", korean_name=None,
        screenshot_url=None, boxart_url=None, source="none",
    )
    assert uploads._rom_stored_name(meta, "CartNoExt") == "Cart Title"


# ── complete_upload: video finalize (kick off background encode) ─────────────

def test_complete_upload_video_requires_ffmpeg(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(video_service, "ffmpeg_available", lambda: False)
    upload_id = _init_and_fill(client, session_id, "clip.mp4", b"video-bytes", kind="video")

    r = client.post(f"/api/sessions/{session_id}/uploads/{upload_id}/complete")
    assert r.status_code == 503
    assert _upload_row(upload_id)["status"] == "failed"


def test_complete_upload_video_success_schedules_encode_job(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(video_service, "ffmpeg_available", lambda: True)

    async def _fake_encode(_src, dst, mode=None):  # pragma: no cover - not awaited by the request
        dst.write_bytes(b"AVI")
        return dst
    monkeypatch.setattr(video_service, "encode_to_mjpeg_avi", _fake_encode)

    upload_id = _init_and_fill(client, session_id, "clip.mp4", b"video-bytes", kind="video")
    r = client.post(f"/api/sessions/{session_id}/uploads/{upload_id}/complete")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "encoding"
    assert body["avi_name"] == "clip.avi"

    with db.connect() as conn:
        video_row = dict(conn.execute(
            "SELECT * FROM videos WHERE id = ?", (body["video_id"],)
        ).fetchone())
    # The encode itself runs as a fire-and-forget asyncio.create_task, so by the
    # time this request returns it may already have finished (fast, mocked
    # encoder) or still be pending — either is a correct outcome here; the
    # dedicated _run_encode tests below pin its actual state transitions.
    assert video_row["status"] in ("encoding", "ok")
    assert video_row["job_id"] == body["job_id"]
    assert _upload_row(upload_id)["status"] == "complete"


# ── _run_encode: the background pipeline itself, called directly ─────────────

@pytest.mark.asyncio
async def test_run_encode_success_marks_job_and_video_done(session_id, monkeypatch, tmp_path):
    video_id, job_id = storage.new_id(), storage.new_id()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO videos (id, session_id, original_name, avi_name, job_id, status) "
            "VALUES (?,?,?,?,?, 'encoding')",
            (video_id, session_id, "clip.mp4", "clip.avi", job_id),
        )
    jobs.create(job_id, "video_encode")

    src = storage.media_dir(session_id) / ".src_test"
    dst = storage.media_dir(session_id) / "clip.avi"
    storage.write_bytes(src, b"raw-video-bytes")

    async def _fake_encode(_src, _dst):
        _dst.parent.mkdir(parents=True, exist_ok=True)
        _dst.write_bytes(b"AVI-DATA")
    monkeypatch.setattr(video_service, "encode_to_mjpeg_avi", _fake_encode)

    await uploads._run_encode(job_id, video_id, src, dst, session_id)

    job = jobs.get(job_id)
    assert job.status == "done"
    assert job.progress == 1.0
    assert job.result["video_id"] == video_id
    assert not src.exists()  # temp input cleaned up

    with db.connect() as conn:
        row = dict(conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone())
    assert row["status"] == "ok"
    assert row["avi_path"] == storage.relative_to_session(session_id, dst)


@pytest.mark.asyncio
async def test_run_encode_failure_cleans_partial_output_and_marks_failed(
    session_id, monkeypatch
):
    video_id, job_id = storage.new_id(), storage.new_id()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO videos (id, session_id, original_name, avi_name, job_id, status) "
            "VALUES (?,?,?,?,?, 'encoding')",
            (video_id, session_id, "clip.mp4", "clip.avi", job_id),
        )
    jobs.create(job_id, "video_encode")

    src = storage.media_dir(session_id) / ".src_test"
    dst = storage.media_dir(session_id) / "clip.avi"
    storage.write_bytes(src, b"raw-video-bytes")
    storage.write_bytes(dst, b"partial-garbage-ffmpeg-left-behind")

    async def _fake_encode(_src, _dst):
        raise video_service.VideoEncodeError("ffmpeg exploded")
    monkeypatch.setattr(video_service, "encode_to_mjpeg_avi", _fake_encode)

    await uploads._run_encode(job_id, video_id, src, dst, session_id)

    job = jobs.get(job_id)
    assert job.status == "failed"
    assert "ffmpeg exploded" in job.message
    assert not dst.exists()   # partial output removed
    assert not src.exists()  # temp input still cleaned up (finally)

    with db.connect() as conn:
        row = dict(conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone())
    assert row["status"] == "failed"


# ── extra.py: safe_rel_path (pure function, security boundary) ───────────────

def test_safe_rel_path_keeps_a_normal_relative_path():
    assert safe_rel_path("bios/nes/disksys.rom") == "bios/nes/disksys.rom"


def test_safe_rel_path_strips_parent_traversal_segments():
    assert safe_rel_path("../../x") == "x"


def test_safe_rel_path_strips_leading_absolute_slash():
    assert safe_rel_path("/bios/x") == "bios/x"


def test_safe_rel_path_deep_traversal_confines_to_final_segments():
    # Every '..'/'.' component is dropped, not merely blocked — this is the
    # security-relevant guarantee: a crafted path can never climb above _extra.
    assert safe_rel_path("../../../etc/passwd") == "etc/passwd"


def test_safe_rel_path_empty_or_all_traversal_yields_empty_string():
    assert safe_rel_path("") == ""
    assert safe_rel_path("../..") == ""
    assert safe_rel_path(".") == ""


def test_safe_rel_path_sanitizes_illegal_chars_per_segment():
    assert safe_rel_path("bios/nes/bad*name?.rom") == "bios/nes/bad_name_.rom"


# ── extra.py: router endpoints ────────────────────────────────────────────────

def test_list_extra_empty_for_fresh_session(client, session_id):
    r = client.get(f"/api/sessions/{session_id}/extra")
    assert r.status_code == 200
    assert r.json() == {"files": []}


def test_list_extra_unknown_session(client):
    r = client.get("/api/sessions/no-such-session/extra")
    assert r.status_code == 404


def test_upload_extra_stores_file_at_given_sd_path(client, session_id):
    r = client.post(
        f"/api/sessions/{session_id}/extra",
        data={"path": "bios/nes/disksys.rom"},
        files={"file": ("disksys.rom", b"bios-bytes")},
    )
    assert r.status_code == 200
    assert r.json() == {"path": "bios/nes/disksys.rom", "size_bytes": len(b"bios-bytes")}

    stored = storage.extra_dir(session_id) / "bios" / "nes" / "disksys.rom"
    assert stored.read_bytes() == b"bios-bytes"

    listing = client.get(f"/api/sessions/{session_id}/extra").json()["files"]
    assert len(listing) == 1
    assert listing[0]["path"] == "bios/nes/disksys.rom"
    assert listing[0]["size_bytes"] == len(b"bios-bytes")


def test_list_extra_reports_when_the_file_was_uploaded(client, session_id):
    """The file list shows an upload time. These files are hand-uploaded and never
    rewritten, so the file's own mtime IS that time — no DB row needed. It goes out
    in the same UTC "YYYY-MM-DD HH:MM:SS" shape as the activity feed, so the UI
    formats both with one formatter."""
    import re
    from datetime import datetime, timezone

    before = datetime.now(tz=timezone.utc).replace(microsecond=0)
    client.post(
        f"/api/sessions/{session_id}/extra",
        data={"path": "bios/nes/disksys.rom"},
        files={"file": ("disksys.rom", b"bios-bytes")},
    )

    stamp = client.get(f"/api/sessions/{session_id}/extra").json()["files"][0]["uploaded_at"]

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", stamp)
    uploaded = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    assert (uploaded - before).total_seconds() >= -1        # stamped now, not epoch 0
    assert (uploaded - before).total_seconds() < 60


def test_upload_extra_path_traversal_is_confined_under_extra_dir(client, session_id):
    """A crafted '../../../etc/passwd' target must land inside _extra, never
    escape the session root — the exact security property safe_rel_path pins."""
    r = client.post(
        f"/api/sessions/{session_id}/extra",
        data={"path": "../../../etc/passwd"},
        files={"file": ("passwd", b"not-actually-passwd")},
    )
    assert r.status_code == 200
    assert r.json()["path"] == "etc/passwd"

    escaped_target = storage.session_root(session_id).parent.parent / "etc" / "passwd"
    assert not escaped_target.exists()
    confined_target = storage.extra_dir(session_id) / "etc" / "passwd"
    assert confined_target.read_bytes() == b"not-actually-passwd"


def test_upload_extra_rejects_path_that_sanitizes_to_empty(client, session_id):
    r = client.post(
        f"/api/sessions/{session_id}/extra",
        data={"path": "../.."},
        files={"file": ("x.bin", b"data")},
    )
    assert r.status_code == 400


def test_upload_extra_rejects_empty_file(client, session_id):
    r = client.post(
        f"/api/sessions/{session_id}/extra",
        data={"path": "a.bin"},
        files={"file": ("a.bin", b"")},
    )
    assert r.status_code == 400


def test_upload_extra_rejects_oversized_file(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "MAX_EXTRA_BYTES", 4)
    r = client.post(
        f"/api/sessions/{session_id}/extra",
        data={"path": "a.bin"},
        files={"file": ("a.bin", b"12345")},
    )
    assert r.status_code == 413


def test_download_extra_returns_bytes_with_content_disposition(client, session_id):
    client.post(
        f"/api/sessions/{session_id}/extra",
        data={"path": "bios/x.rom"},
        files={"file": ("x.rom", b"payload-bytes")},
    )
    r = client.get(f"/api/sessions/{session_id}/extra/download", params={"path": "bios/x.rom"})
    assert r.status_code == 200
    assert r.content == b"payload-bytes"
    assert "x.rom" in r.headers["content-disposition"]


def test_download_extra_404_when_missing(client, session_id):
    r = client.get(f"/api/sessions/{session_id}/extra/download", params={"path": "nope.bin"})
    assert r.status_code == 404


def test_delete_extra_moves_file_to_trash_not_permanent_delete(client, session_id):
    client.post(
        f"/api/sessions/{session_id}/extra",
        data={"path": "bios/x.rom"},
        files={"file": ("x.rom", b"payload-bytes")},
    )
    r = client.delete(f"/api/sessions/{session_id}/extra", params={"path": "bios/x.rom"})
    assert r.status_code == 200
    assert r.json() == {"deleted": "bios/x.rom"}

    assert not (storage.extra_dir(session_id) / "bios" / "x.rom").exists()
    # move_to_trash flattens the FULL session-relative path (including the
    # "_extra" prefix), joined with "__".
    trashed = storage.trash_dir(session_id) / "_extra__bios__x.rom"
    assert trashed.read_bytes() == b"payload-bytes"


def test_delete_extra_missing_file_is_a_noop(client, session_id):
    r = client.delete(f"/api/sessions/{session_id}/extra", params={"path": "never/uploaded.bin"})
    assert r.status_code == 200
    assert r.json() == {"deleted": "never/uploaded.bin"}


# ── firmware.py: router endpoints ─────────────────────────────────────────────

def test_firmware_info_absent_before_any_upload(client, session_id):
    r = client.get(f"/api/sessions/{session_id}/firmware")
    assert r.status_code == 200
    assert r.json() == {
        "present": False, "filename": "retro-go_update.bin",
        "size_bytes": 0, "uploaded_at": None,
    }


def test_firmware_get_unknown_session(client):
    r = client.get("/api/sessions/no-such-session/firmware")
    assert r.status_code == 404


def test_firmware_upload_then_info_reports_present_and_size(client, session_id):
    r = client.post(
        f"/api/sessions/{session_id}/firmware",
        files={"file": ("retro-go_update.bin", b"firmware-bytes-v1")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["present"] is True
    assert body["size_bytes"] == len(b"firmware-bytes-v1")
    assert body["uploaded_at"] is not None
    assert body["original_name"] == "retro-go_update.bin"

    info = client.get(f"/api/sessions/{session_id}/firmware").json()
    assert info["present"] is True
    assert info["size_bytes"] == len(b"firmware-bytes-v1")


def test_firmware_upload_replaces_existing_file(client, session_id):
    client.post(
        f"/api/sessions/{session_id}/firmware",
        files={"file": ("retro-go_update.bin", b"short")},
    )
    r = client.post(
        f"/api/sessions/{session_id}/firmware",
        files={"file": ("retro-go_update.bin", b"a-much-longer-payload")},
    )
    assert r.status_code == 200
    assert r.json()["size_bytes"] == len(b"a-much-longer-payload")
    # Replaced in place, not appended alongside — one file on disk.
    assert storage.firmware_path(session_id).read_bytes() == b"a-much-longer-payload"


def test_firmware_upload_rejects_non_bin_extension(client, session_id):
    r = client.post(
        f"/api/sessions/{session_id}/firmware",
        files={"file": ("firmware.zip", b"data")},
    )
    assert r.status_code == 400


def test_firmware_upload_accepts_uppercase_bin_suffix(client, session_id):
    r = client.post(
        f"/api/sessions/{session_id}/firmware",
        files={"file": ("Firmware.BIN", b"data")},
    )
    assert r.status_code == 200


def test_firmware_upload_rejects_empty_file(client, session_id):
    r = client.post(
        f"/api/sessions/{session_id}/firmware",
        files={"file": ("retro-go_update.bin", b"")},
    )
    assert r.status_code == 400


def test_firmware_upload_rejects_oversized_file(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "MAX_FIRMWARE_BYTES", 4)
    r = client.post(
        f"/api/sessions/{session_id}/firmware",
        files={"file": ("retro-go_update.bin", b"12345")},
    )
    assert r.status_code == 413


def test_firmware_download_returns_bytes_and_headers(client, session_id):
    client.post(
        f"/api/sessions/{session_id}/firmware",
        files={"file": ("retro-go_update.bin", b"firmware-payload")},
    )
    r = client.get(f"/api/sessions/{session_id}/firmware/download")
    assert r.status_code == 200
    assert r.content == b"firmware-payload"
    assert "retro-go_update.bin" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"


def test_firmware_download_404_when_absent(client, session_id):
    r = client.get(f"/api/sessions/{session_id}/firmware/download")
    assert r.status_code == 404


def test_firmware_delete_removes_file(client, session_id):
    client.post(
        f"/api/sessions/{session_id}/firmware",
        files={"file": ("retro-go_update.bin", b"firmware-payload")},
    )
    r = client.delete(f"/api/sessions/{session_id}/firmware")
    assert r.status_code == 200
    assert r.json() == {"present": False}
    assert not storage.firmware_path(session_id).exists()


def test_firmware_delete_is_a_noop_when_nothing_uploaded(client, session_id):
    r = client.delete(f"/api/sessions/{session_id}/firmware")
    assert r.status_code == 200
    assert r.json() == {"present": False}
