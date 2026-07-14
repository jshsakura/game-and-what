# -*- coding: utf-8 -*-
"""Router-level tests for the SD-package/download surface: downloads.py (single
ROM/video/music download + in-browser serving), package.py (SD ZIP build,
per-ROM SD flags, size estimate, async build job, ETag caching) and data.py
(scratch "DATA" file upload/list/download/delete).

Everything here goes through `client` (the real ASGI app), so header shaping,
status codes and REAL zip contents (opened with zipfile, arcnames asserted)
are pinned end to end — not just "packaging produced some bytes".

The async build job (POST .../package/build) is driven deterministically —
no `time.sleep` anywhere in this file:
  - the "ready" (already cached) branch is exercised by warming the cache
    with a prior GET first.
  - the ordinary job-runs-to-completion path polls GET /api/jobs/{id} in a
    bounded, sleep-free loop (the worker runs on a real thread via
    run_in_threadpool and finishes within a handful of round trips).
  - the cancellation path replaces packaging.run_sd_zip_build_job with a fake
    that coordinates with the test via threading.Event — it still runs on a
    real background thread (asyncio.create_task fire-and-forget), so an
    Event wait (not a fixed sleep) is what proves the worker has actually
    started before we cancel it.
"""
from __future__ import annotations

import json
import threading
import zipfile
from io import BytesIO

import pytest
from fastapi import HTTPException

from app import config, db
from app.routers import downloads as downloads_router
from app.routers import package as package_router
from app.services import jobs as jobs_service
from app.services import storage
from app.services.video import VideoEncodeError
from app.systems import get_system


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _zip_names(content: bytes) -> set[str]:
    with zipfile.ZipFile(BytesIO(content)) as zf:
        return set(zf.namelist())


def _add_cover(session_id: str, system_key: str, filename: str, content: bytes = b"cover-bytes") -> str:
    """Write a real cover file on disk and return its session-relative path."""
    system = get_system(system_key)
    cover_dir = storage.covers_dir(session_id, system.dirname)
    cover_dir.mkdir(parents=True, exist_ok=True)
    path = cover_dir / filename
    path.write_bytes(content)
    return storage.relative_to_session(session_id, path)


def _insert_video(session_id: str, *, avi_name: str = "clip.avi", status: str = "ok",
                  with_file: bool = True, content: bytes = b"AVI-BYTES") -> dict:
    video_id = storage.new_id()
    avi_rel = None
    if with_file:
        media_dir = storage.media_dir(session_id)
        media_dir.mkdir(parents=True, exist_ok=True)
        avi_path = media_dir / avi_name
        avi_path.write_bytes(content)
        avi_rel = storage.relative_to_session(session_id, avi_path)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO videos (id, session_id, original_name, avi_name, avi_path, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (video_id, session_id, avi_name, avi_name, avi_rel, status),
        )
    return {"id": video_id, "avi_path": avi_rel}


def _insert_music(session_id: str, *, name: str = "song.mp3", with_file: bool = True,
                  content: bytes = b"ID3-BYTES") -> dict:
    music_id = storage.new_id()
    rel = None
    if with_file:
        music_dir = storage.music_dir(session_id)
        music_dir.mkdir(parents=True, exist_ok=True)
        path = music_dir / name
        path.write_bytes(content)
        rel = storage.relative_to_session(session_id, path)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO music (id, session_id, original_name, stored_name, music_path, size_bytes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (music_id, session_id, name, name, rel or f"music/{name}", len(content)),
        )
    return {"id": music_id, "music_path": rel}


def _poll_job(client, job_id: str, max_attempts: int = 500) -> dict:
    """Bounded, sleep-free re-poll: the worker runs on a real background thread
    (run_in_threadpool), so it reaches a terminal state within a handful of
    round trips without ever needing to sleep for it."""
    for _ in range(max_attempts):
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "failed", "cancelled"):
            return body
    raise AssertionError(f"job {job_id} did not reach a terminal state in time")


# ---------------------------------------------------------------------------
# downloads.py — /roms/{id}/download (ROM + cover ZIP)
# ---------------------------------------------------------------------------

def test_download_rom_zip_bundles_rom_and_cover(client, make_rom, session_id):
    cover_rel = _add_cover(session_id, "nes", "Game.img")
    rom = make_rom(system_key="nes", name="Game.nes", cover_path=cover_rel)

    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/download")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert _zip_names(resp.content) == {rom["rom_path"], cover_rel}


def test_download_rom_zip_without_cover_ships_rom_only(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Game.nes")

    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/download")

    assert resp.status_code == 200
    assert _zip_names(resp.content) == {rom["rom_path"]}


def test_download_rom_zip_includes_extra_files(client, make_rom, session_id):
    rom = make_rom(system_key="homebrew", name="zelda3.ro",
                    extra_files=json.dumps([{"name": "zelda3_assets.dat"}]))
    extra_path = storage.session_root(session_id) / "roms/homebrew/zelda3_assets.dat"
    extra_path.parent.mkdir(parents=True, exist_ok=True)
    extra_path.write_bytes(b"assets")

    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/download")

    assert _zip_names(resp.content) == {rom["rom_path"], "roms/homebrew/zelda3_assets.dat"}


def test_download_rom_zip_skips_homebrew_bin_by_default(client, make_rom, session_id):
    cover_rel = _add_cover(session_id, "homebrew", "App.img")
    rom = make_rom(system_key="homebrew", name="App.bin", cover_path=cover_rel)

    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/download")

    # .bin lives in the flashed firmware, not on the card — only the cover ships.
    assert _zip_names(resp.content) == {cover_rel}


def test_download_rom_zip_includes_homebrew_bin_when_opted_in(client, make_rom, session_id):
    rom = make_rom(system_key="homebrew", name="App.bin", sd_include=1)

    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/download")

    assert _zip_names(resp.content) == {rom["rom_path"]}


def test_download_rom_404_when_nothing_to_download(client, make_rom, session_id):
    rom = make_rom(system_key="homebrew", name="App.bin")  # no cover, sd_include=0 default
    (storage.session_root(session_id) / rom["rom_path"]).unlink()  # and the .bin itself is gone

    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/download")

    assert resp.status_code == 404
    assert "Nothing to download" in resp.json()["detail"]


def test_download_rom_unknown_id_404s(client, session_id):
    resp = client.get(f"/api/sessions/{session_id}/roms/doesnotexist/download")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "ROM not found in session"


def test_download_rom_unknown_session_404s(client, make_rom):
    rom = make_rom()

    resp = client.get(f"/api/sessions/unknown-session/roms/{rom['id']}/download")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown session"


def test_download_rom_korean_filename_falls_back_to_ascii_header(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="젤다의 전설.nes")

    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/download")

    assert resp.status_code == 200
    disposition = resp.headers["content-disposition"]
    assert 'filename="' in disposition
    assert "filename*=UTF-8''" in disposition


# ---------------------------------------------------------------------------
# downloads.py — /roms/{id}/rom (raw bytes, in-browser emulation)
# ---------------------------------------------------------------------------

def test_serve_rom_returns_raw_bytes(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Game.nes", content=b"raw-rom-bytes")

    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/rom")

    assert resp.status_code == 200
    assert resp.content == b"raw-rom-bytes"
    assert resp.headers["content-type"] == "application/octet-stream"
    assert resp.headers["cache-control"] == "public, max-age=86400"


def test_serve_rom_missing_file_404s(client, make_rom, session_id):
    rom = make_rom()
    (storage.session_root(session_id) / rom["rom_path"]).unlink()

    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/rom")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "ROM file missing from disk"


# ---------------------------------------------------------------------------
# downloads.py — /roms/{id}/cdfile (CD track sidecar files)
# ---------------------------------------------------------------------------

def test_serve_cd_track_returns_sibling_file(client, make_rom, session_id):
    dest_dir = storage.roms_dir(session_id, "pcecd")
    (dest_dir / "Game").mkdir(parents=True, exist_ok=True)
    rom = make_rom(system_key="pcecd", name="Game/Game.cue")
    (dest_dir / "Game" / "track1.bin").write_bytes(b"track-bytes")

    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cdfile",
                       params={"name": "track1.bin"})

    assert resp.status_code == 200
    assert resp.content == b"track-bytes"


def test_serve_cd_track_name_is_basename_only_no_traversal(client, make_rom, session_id):
    dest_dir = storage.roms_dir(session_id, "pcecd")
    (dest_dir / "Game").mkdir(parents=True, exist_ok=True)
    rom = make_rom(system_key="pcecd", name="Game/Game.cue")
    (dest_dir / "Game" / "track1.bin").write_bytes(b"track-bytes")

    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cdfile",
                       params={"name": "../../../etc/track1.bin"})

    # basename-only resolution keeps it inside the game's own folder, not an escape.
    assert resp.status_code == 200
    assert resp.content == b"track-bytes"


def test_serve_cd_track_missing_file_404s(client, make_rom, session_id):
    dest_dir = storage.roms_dir(session_id, "pcecd")
    (dest_dir / "Game").mkdir(parents=True, exist_ok=True)
    rom = make_rom(system_key="pcecd", name="Game/Game.cue")

    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cdfile",
                       params={"name": "missing.bin"})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Track file missing from disk"


# ---------------------------------------------------------------------------
# downloads.py — /videos/{id}/download
# ---------------------------------------------------------------------------

def test_download_video_streams_avi_bytes(client, session_id):
    v = _insert_video(session_id, content=b"AVI-PAYLOAD")

    resp = client.get(f"/api/sessions/{session_id}/videos/{v['id']}/download")

    assert resp.status_code == 200
    assert resp.content == b"AVI-PAYLOAD"
    assert resp.headers["content-type"] == "video/avi"
    assert resp.headers["content-length"] == str(len(b"AVI-PAYLOAD"))


def test_download_video_not_ready_404s(client, session_id):
    v = _insert_video(session_id, status="encoding")

    resp = client.get(f"/api/sessions/{session_id}/videos/{v['id']}/download")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Video not ready yet"


def test_download_video_avi_missing_from_disk_404s(client, session_id):
    v = _insert_video(session_id)
    (storage.session_root(session_id) / v["avi_path"]).unlink()

    resp = client.get(f"/api/sessions/{session_id}/videos/{v['id']}/download")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "AVI file missing from disk"


# ---------------------------------------------------------------------------
# downloads.py — /music/{id}/download and /stream
# ---------------------------------------------------------------------------

def test_download_music_returns_bytes(client, session_id):
    m = _insert_music(session_id, content=b"MP3-PAYLOAD")

    resp = client.get(f"/api/sessions/{session_id}/music/{m['id']}/download")

    assert resp.status_code == 200
    assert resp.content == b"MP3-PAYLOAD"
    assert resp.headers["content-type"] == "audio/mpeg"


def test_download_music_missing_file_404s(client, session_id):
    m = _insert_music(session_id)
    (storage.session_root(session_id) / m["music_path"]).unlink()

    resp = client.get(f"/api/sessions/{session_id}/music/{m['id']}/download")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "MP3 file missing from disk"


def test_music_stream_serves_file(client, session_id):
    m = _insert_music(session_id)

    resp = client.get(f"/api/sessions/{session_id}/music/{m['id']}/stream")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"


def test_music_stream_missing_file_404s(client, session_id):
    m = _insert_music(session_id)
    (storage.session_root(session_id) / m["music_path"]).unlink()

    resp = client.get(f"/api/sessions/{session_id}/music/{m['id']}/stream")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "mp3 missing"


# ---------------------------------------------------------------------------
# downloads.py — /videos/{id}/thumb + /preview and /music/{id}/cover
# (encode/extract calls are monkeypatched — no real ffmpeg in this test file)
# ---------------------------------------------------------------------------

def test_video_thumb_serves_existing_cached_thumb_without_reencoding(client, session_id, monkeypatch):
    v = _insert_video(session_id)
    thumb = storage.media_thumb_path(session_id, v["id"])
    thumb.parent.mkdir(parents=True, exist_ok=True)
    thumb.write_bytes(b"cached-thumb")

    def _must_not_run(*_a, **_kw):
        raise AssertionError("make_thumb must not run when a cached thumb already exists")
    monkeypatch.setattr(downloads_router.video, "make_thumb", _must_not_run)

    resp = client.get(f"/api/sessions/{session_id}/videos/{v['id']}/thumb")

    assert resp.status_code == 200
    assert resp.content == b"cached-thumb"


def test_video_thumb_generates_when_missing(client, session_id, monkeypatch):
    v = _insert_video(session_id)

    async def fake_make_thumb(input_path, output_path, w=480, h=270):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"generated-thumb")
        return output_path
    monkeypatch.setattr(downloads_router.video, "make_thumb", fake_make_thumb)

    resp = client.get(f"/api/sessions/{session_id}/videos/{v['id']}/thumb")

    assert resp.status_code == 200
    assert resp.content == b"generated-thumb"


def test_video_thumb_encode_failure_404s(client, session_id, monkeypatch):
    v = _insert_video(session_id)

    async def fake_make_thumb(*_a, **_kw):
        raise VideoEncodeError("boom")
    monkeypatch.setattr(downloads_router.video, "make_thumb", fake_make_thumb)

    resp = client.get(f"/api/sessions/{session_id}/videos/{v['id']}/thumb")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "thumbnail failed"


def test_video_thumb_not_ready_404s(client, session_id):
    v = _insert_video(session_id, status="encoding")

    resp = client.get(f"/api/sessions/{session_id}/videos/{v['id']}/thumb")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "no thumbnail"


def test_video_thumb_avi_missing_404s(client, session_id):
    v = _insert_video(session_id)
    (storage.session_root(session_id) / v["avi_path"]).unlink()

    resp = client.get(f"/api/sessions/{session_id}/videos/{v['id']}/thumb")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "avi missing"


def test_video_preview_generates_when_missing(client, session_id, monkeypatch):
    v = _insert_video(session_id)

    async def fake_make_web_preview(input_path, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"generated-preview")
        return output_path
    monkeypatch.setattr(downloads_router.video, "make_web_preview", fake_make_web_preview)

    resp = client.get(f"/api/sessions/{session_id}/videos/{v['id']}/preview")

    assert resp.status_code == 200
    assert resp.content == b"generated-preview"


def test_video_preview_encode_failure_404s(client, session_id, monkeypatch):
    v = _insert_video(session_id)

    async def fake_make_web_preview(*_a, **_kw):
        raise VideoEncodeError("boom")
    monkeypatch.setattr(downloads_router.video, "make_web_preview", fake_make_web_preview)

    resp = client.get(f"/api/sessions/{session_id}/videos/{v['id']}/preview")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "preview failed"


def test_video_preview_not_ready_404s(client, session_id):
    v = _insert_video(session_id, status="encoding")

    resp = client.get(f"/api/sessions/{session_id}/videos/{v['id']}/preview")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "not ready"


def test_video_preview_avi_missing_404s(client, session_id):
    v = _insert_video(session_id)
    (storage.session_root(session_id) / v["avi_path"]).unlink()

    resp = client.get(f"/api/sessions/{session_id}/videos/{v['id']}/preview")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "avi missing"


def test_music_cover_extracts_when_missing(client, session_id, monkeypatch):
    m = _insert_music(session_id)

    async def fake_extract_cover(mp3_path, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"cover-jpg")
        return output_path
    monkeypatch.setattr(downloads_router.video, "extract_cover", fake_extract_cover)

    resp = client.get(f"/api/sessions/{session_id}/music/{m['id']}/cover")

    assert resp.status_code == 200
    assert resp.content == b"cover-jpg"


def test_music_cover_no_art_404s(client, session_id, monkeypatch):
    m = _insert_music(session_id)

    async def fake_extract_cover(*_a, **_kw):
        raise VideoEncodeError("no art")
    monkeypatch.setattr(downloads_router.video, "extract_cover", fake_extract_cover)

    resp = client.get(f"/api/sessions/{session_id}/music/{m['id']}/cover")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "no cover art"


def test_music_cover_missing_mp3_404s(client, session_id):
    m = _insert_music(session_id)
    (storage.session_root(session_id) / m["music_path"]).unlink()

    resp = client.get(f"/api/sessions/{session_id}/music/{m['id']}/cover")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "mp3 missing"


# ---------------------------------------------------------------------------
# shared error paths: unknown id / unknown session, across every GET endpoint
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("suffix", [
    "roms/{id}/download",
    "roms/{id}/rom",
    "roms/{id}/cdfile?name=track1.bin",
    "videos/{id}/download",
    "videos/{id}/thumb",
    "videos/{id}/preview",
    "music/{id}/download",
    "music/{id}/stream",
    "music/{id}/cover",
])
def test_unknown_id_returns_404_across_download_endpoints(client, session_id, suffix):
    url = f"/api/sessions/{session_id}/{suffix.format(id='does-not-exist')}"

    resp = client.get(url)

    assert resp.status_code == 404


def test_downloads_unknown_session_404s(client):
    resp = client.get("/api/sessions/nope/roms/x/download")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown session"


# ---------------------------------------------------------------------------
# package.py — per-ROM SD flags (sd-include / sd-exclude / favorite / pico8-compat)
# ---------------------------------------------------------------------------

def test_set_sd_include_toggles_flag(client, make_rom, session_id):
    rom = make_rom(system_key="homebrew", name="App.bin")

    resp = client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/sd-include",
                         json={"include": True})

    assert resp.status_code == 200
    assert resp.json() == {"rom_id": rom["id"], "sd_include": True}
    with db.connect() as conn:
        row = conn.execute("SELECT sd_include FROM roms WHERE id = ?", (rom["id"],)).fetchone()
    assert row["sd_include"] == 1


def test_set_sd_include_unknown_rom_404s(client, session_id):
    resp = client.patch(f"/api/sessions/{session_id}/roms/nope/sd-include", json={"include": True})

    assert resp.status_code == 404


def test_set_sd_exclude_toggles_flag(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Game.nes")

    resp = client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/sd-exclude",
                         json={"exclude": True})

    assert resp.status_code == 200
    assert resp.json() == {"rom_id": rom["id"], "sd_exclude": True}


def test_set_sd_exclude_unknown_rom_404s(client, session_id):
    resp = client.patch(f"/api/sessions/{session_id}/roms/nope/sd-exclude", json={"exclude": True})

    assert resp.status_code == 404


def test_set_sd_exclude_bulk_updates_only_matching_session_rows(client, make_rom, session_id):
    a = make_rom(system_key="nes", name="A.nes")
    b = make_rom(system_key="nes", name="B.nes")

    resp = client.patch(f"/api/sessions/{session_id}/sd-exclude",
                         json={"rom_ids": [a["id"], b["id"], "not-a-real-id"], "exclude": True})

    assert resp.status_code == 200
    assert resp.json() == {"updated": 2, "exclude": True}


def test_set_sd_exclude_bulk_requires_a_non_empty_list(client, session_id):
    empty = client.patch(f"/api/sessions/{session_id}/sd-exclude", json={"rom_ids": [], "exclude": True})
    assert empty.status_code == 400

    not_a_list = client.patch(f"/api/sessions/{session_id}/sd-exclude", json={"rom_ids": "oops"})
    assert not_a_list.status_code == 400


def test_set_favorite_toggles_flag(client, make_rom, session_id):
    rom = make_rom()

    resp = client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/favorite", json={"favorite": True})

    assert resp.status_code == 200
    assert resp.json() == {"rom_id": rom["id"], "favorite": True}


def test_set_favorite_unknown_rom_404s(client, session_id):
    resp = client.patch(f"/api/sessions/{session_id}/roms/nope/favorite", json={"favorite": True})

    assert resp.status_code == 404


def test_set_pico8_compat_accepts_known_values(client, make_rom, session_id):
    rom = make_rom(system_key="pico8", name="cart.p8")

    resp = client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/pico8-compat",
                         json={"status": "broken"})

    assert resp.status_code == 200
    assert resp.json() == {"rom_id": rom["id"], "pico8_compat": "broken"}


def test_set_pico8_compat_null_clears_status(client, make_rom, session_id):
    rom = make_rom(system_key="pico8", name="cart.p8", pico8_compat="good")

    resp = client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/pico8-compat",
                         json={"status": None})

    assert resp.status_code == 200
    assert resp.json()["pico8_compat"] is None


def test_set_pico8_compat_rejects_unknown_status(client, make_rom, session_id):
    rom = make_rom(system_key="pico8", name="cart.p8")

    resp = client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/pico8-compat",
                         json={"status": "amazing"})

    assert resp.status_code == 400


def test_set_pico8_compat_rejects_non_pico8_rom(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Game.nes")

    resp = client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/pico8-compat",
                         json={"status": "good"})

    assert resp.status_code == 400


def test_set_pico8_compat_unknown_rom_404s(client, session_id):
    resp = client.patch(f"/api/sessions/{session_id}/roms/nope/pico8-compat", json={"status": "good"})

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# package.py — /package/size (estimated bytes)
# ---------------------------------------------------------------------------

def test_package_size_reflects_full_library(client, make_rom, session_id):
    make_rom(system_key="nes", name="A.nes", content=b"x" * 100)
    make_rom(system_key="gb", name="B.gb", content=b"y" * 50)

    resp = client.get(f"/api/sessions/{session_id}/package/size")

    assert resp.status_code == 200
    assert resp.json()["bytes"] >= 150


def test_package_size_system_filter_shrinks_the_estimate(client, make_rom, session_id):
    make_rom(system_key="nes", name="A.nes", content=b"x" * 100)
    make_rom(system_key="gb", name="B.gb", content=b"y" * 50)

    full = client.get(f"/api/sessions/{session_id}/package/size").json()["bytes"]
    nes_only = client.get(f"/api/sessions/{session_id}/package/size",
                          params={"system": "nes"}).json()["bytes"]

    assert 0 < nes_only < full


def test_package_size_reports_the_zip_size_only_once_that_zip_exists(client, make_rom, session_id):
    """Two different questions: `bytes` is what the files take ON THE CARD, `zip_bytes`
    is what you download. How well a selection compresses depends on what's in it, so
    the zip size is reported from the built file — never guessed. Before the build it
    is null; the build fills it in."""
    make_rom(system_key="nes", name="Game.nes", content=b"compress me " * 500)

    first = client.get(f"/api/sessions/{session_id}/package/size").json()
    assert first["bytes"] > 0
    assert first["zip_bytes"] is None          # nothing built yet — no guess offered

    client.get(f"/api/sessions/{session_id}/package")          # builds + caches the zip
    after = client.get(f"/api/sessions/{session_id}/package/size").json()

    assert after["bytes"] == first["bytes"]                    # the card size didn't move
    assert 0 < after["zip_bytes"] < after["bytes"]             # …and the zip is smaller


def test_package_size_flag_filter_drops_the_other_flags(client, make_rom, session_id):
    make_rom(system_key="nes", name="Korean.nes", content=b"k" * 100, cover_flag="ko")
    make_rom(system_key="nes", name="Other.nes", content=b"o" * 100)

    full = client.get(f"/api/sessions/{session_id}/package/size").json()["bytes"]
    ko_only = client.get(f"/api/sessions/{session_id}/package/size",
                         params={"flags": "ko"}).json()["bytes"]

    assert 0 < ko_only < full


def test_package_size_drops_broken_pico8_cart(client, make_rom, session_id):
    rom = make_rom(system_key="pico8", name="cart.p8", content=b"z" * 200)

    before = client.get(f"/api/sessions/{session_id}/package/size").json()["bytes"]
    client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/pico8-compat", json={"status": "broken"})
    after = client.get(f"/api/sessions/{session_id}/package/size").json()["bytes"]

    assert after < before


def test_package_size_drops_sd_excluded_rom(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Game.nes", content=b"x" * 200)

    before = client.get(f"/api/sessions/{session_id}/package/size").json()["bytes"]
    client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/sd-exclude", json={"exclude": True})
    after = client.get(f"/api/sessions/{session_id}/package/size").json()["bytes"]

    assert after < before


def test_package_size_drops_sd_excluded_rom_and_its_cover(client, make_rom, session_id):
    """Same as above but WITH a cover on the excluded rom, so
    _rom_and_cover_paths' `if r["cover_path"]:` branch (adding the cover path
    too) is exercised, not just the rom_path one."""
    cover_rel = _add_cover(session_id, "nes", "Game.img", content=b"c" * 300)
    rom = make_rom(system_key="nes", name="Game.nes", content=b"x" * 200, cover_path=cover_rel)

    before = client.get(f"/api/sessions/{session_id}/package/size").json()["bytes"]
    client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/sd-exclude", json={"exclude": True})
    after = client.get(f"/api/sessions/{session_id}/package/size").json()["bytes"]

    assert after <= before - 300  # both the ROM AND its cover dropped


def test_package_size_unknown_session_404s(client):
    resp = client.get("/api/sessions/nope/package/size")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# package.py — GET /package (the SD ZIP itself)
# ---------------------------------------------------------------------------

def test_download_package_zip_mirrors_sd_layout(client, make_rom, session_id):
    cover_rel = _add_cover(session_id, "nes", "Game.img")
    rom = make_rom(system_key="nes", name="Game.nes", cover_path=cover_rel)

    resp = client.get(f"/api/sessions/{session_id}/package")

    assert resp.status_code == 200
    names = _zip_names(resp.content)
    assert rom["rom_path"] in names
    assert cover_rel in names


def test_download_package_404s_when_session_is_empty(client, session_id):
    resp = client.get(f"/api/sessions/{session_id}/package")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Nothing to package yet"


def test_download_package_system_filter_keeps_only_that_system(client, make_rom, session_id):
    nes = make_rom(system_key="nes", name="A.nes")
    gb = make_rom(system_key="gb", name="B.gb")

    resp = client.get(f"/api/sessions/{session_id}/package", params={"system": "nes"})

    names = _zip_names(resp.content)
    assert nes["rom_path"] in names
    assert gb["rom_path"] not in names
    assert "-nes-" in resp.headers["content-disposition"]


def test_download_package_multi_system_selection(client, make_rom, session_id):
    nes = make_rom(system_key="nes", name="A.nes")
    gb = make_rom(system_key="gb", name="B.gb")
    md = make_rom(system_key="md", name="C.md")

    resp = client.get(f"/api/sessions/{session_id}/package", params={"system": "nes,gb"})

    names = _zip_names(resp.content)
    assert nes["rom_path"] in names
    assert gb["rom_path"] in names
    assert md["rom_path"] not in names
    assert "-selected" in resp.headers["content-disposition"]


def test_download_package_flag_filter_and_filename_suffix(client, make_rom, session_id):
    ko = make_rom(system_key="nes", name="Korean.nes", cover_flag="ko")
    other = make_rom(system_key="nes", name="Other.nes")

    resp = client.get(f"/api/sessions/{session_id}/package", params={"flags": "ko"})

    names = _zip_names(resp.content)
    assert ko["rom_path"] in names
    assert other["rom_path"] not in names
    assert "-filtered" in resp.headers["content-disposition"]


def test_flag_filter_takes_several_flags_and_can_ask_for_unflagged(client, make_rom, session_id):
    """The flags are a multi-select, and "none" is a category of its own — an unflagged
    ROM is a real thing to want, not a missing value."""
    ko = make_rom(system_key="nes", name="Korean.nes", cover_flag="ko")
    ja = make_rom(system_key="nes", name="Japanese.nes", cover_flag="ja")
    plain = make_rom(system_key="nes", name="Plain.nes")

    both = _zip_names(client.get(f"/api/sessions/{session_id}/package",
                                 params={"flags": "ko,ja"}).content)
    unflagged = _zip_names(client.get(f"/api/sessions/{session_id}/package",
                                      params={"flags": "none"}).content)

    assert {ko["rom_path"], ja["rom_path"]} <= both
    assert plain["rom_path"] not in both
    assert plain["rom_path"] in unflagged
    assert ko["rom_path"] not in unflagged


def test_size_cap_drops_the_roms_that_are_too_big(client, make_rom, session_id):
    small = make_rom(system_key="nes", name="Small.nes", content=b"s" * 1024)
    big = make_rom(system_key="nes", name="Big.nes", content=b"b" * (3 * 1024 * 1024))

    names = _zip_names(client.get(f"/api/sessions/{session_id}/package",
                                  params={"max_mb": 2}).content)

    assert small["rom_path"] in names
    assert big["rom_path"] not in names


def test_rating_floor_drops_low_and_unrated_roms(client, make_rom, session_id):
    """An unrated ROM has no score, so it cannot clear a floor — otherwise a rating
    filter would quietly ship the very ROMs it was meant to weed out."""
    good = make_rom(system_key="nes", name="Good.nes", igdb_score=88)
    weak = make_rom(system_key="nes", name="Weak.nes", igdb_score=42)
    unrated = make_rom(system_key="nes", name="Unrated.nes", igdb_score=-1)
    never = make_rom(system_key="nes", name="Never.nes")          # NULL score

    names = _zip_names(client.get(f"/api/sessions/{session_id}/package",
                                  params={"min_score": 70}).content)

    assert good["rom_path"] in names
    for rom in (weak, unrated, never):
        assert rom["rom_path"] not in names


def test_favorite_and_patched_conditions_are_anded(client, make_rom, session_id):
    both = make_rom(system_key="nes", name="Both.nes", favorite=1, is_korean_patched=1)
    fav_only = make_rom(system_key="nes", name="Fav.nes", favorite=1)
    patched_only = make_rom(system_key="nes", name="Patched.nes", is_korean_patched=1)

    names = _zip_names(client.get(f"/api/sessions/{session_id}/package",
                                  params={"favorite": "1", "patched": "1"}).content)

    assert both["rom_path"] in names
    assert fav_only["rom_path"] not in names
    assert patched_only["rom_path"] not in names


def test_no_conditions_ships_everything(client, make_rom, session_id):
    """Blank/zero params mean "no constraint", not "exclude everything"."""
    rom = make_rom(system_key="nes", name="Game.nes")

    names = _zip_names(client.get(f"/api/sessions/{session_id}/package",
                                  params={"flags": "", "max_mb": 0, "min_score": -1}).content)

    assert rom["rom_path"] in names


def test_excluding_a_cd_game_takes_its_track_sidecars_with_it(client, make_rom, session_id):
    """A CD game is a FOLDER: the .cue is the DB row, the tracks beside it are not.
    Excluding the row used to drop the .cue alone and ship the tracks — gigabytes of
    audio for a game that isn't on the card — and that hole was in sd_exclude too."""
    folder = storage.roms_dir(session_id, "pcecd") / "Game"
    folder.mkdir(parents=True, exist_ok=True)
    cue = make_rom(system_key="pcecd", name="Game/Game.cue")
    (folder / "Game (Track 2).bin").write_bytes(b"audio" * 100)
    make_rom(system_key="nes", name="Keep.nes")          # so there is still a zip

    client.patch(f"/api/sessions/{session_id}/roms/{cue['id']}/sd-exclude",
                 json={"exclude": True})
    names = _zip_names(client.get(f"/api/sessions/{session_id}/package").content)

    assert not [n for n in names if n.startswith("roms/pcecd/")]


def test_conditions_never_drop_homebrew(client, make_rom, session_id):
    """Homebrew is not a release with a flag, a rating or a patch: the .dat / .smc on
    the card are what the firmware's built-in apps need to boot. Any condition that
    dropped them would kill those menu entries, so they are exempt from all of them."""
    ko = make_rom(system_key="nes", name="Korean.nes", cover_flag="ko")
    plain = make_rom(system_key="nes", name="Other.nes")
    assets = make_rom(system_key="homebrew", name="smw_assets.dat")   # no flag, ever

    names = _zip_names(client.get(f"/api/sessions/{session_id}/package", params={
        "flags": "ko", "favorite": "1", "min_score": 90, "max_mb": 1,
    }).content)

    assert assets["rom_path"] in names
    assert ko["rom_path"] not in names       # it fails the other conditions
    assert plain["rom_path"] not in names


def test_download_package_drops_sd_excluded_rom(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Game.nes")
    kept = make_rom(system_key="nes", name="Keep.nes")   # or the build has nothing left to do
    client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/sd-exclude", json={"exclude": True})

    resp = client.get(f"/api/sessions/{session_id}/package")

    names = _zip_names(resp.content)
    assert rom["rom_path"] not in names
    assert kept["rom_path"] in names


def test_download_package_homebrew_bin_covers_only_by_default(client, make_rom, session_id):
    cover_rel = _add_cover(session_id, "homebrew", "App.img")
    rom = make_rom(system_key="homebrew", name="App.bin", cover_path=cover_rel)

    resp = client.get(f"/api/sessions/{session_id}/package")

    names = _zip_names(resp.content)
    assert rom["rom_path"] not in names
    assert cover_rel in names


def test_download_package_homebrew_bin_opted_in(client, make_rom, session_id):
    # A cover rides along with the .bin, mirroring a realistic homebrew upload.
    cover_rel = _add_cover(session_id, "homebrew", "App.img")
    rom = make_rom(system_key="homebrew", name="App.bin", cover_path=cover_rel)
    client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/sd-include", json={"include": True})

    resp = client.get(f"/api/sessions/{session_id}/package")

    assert rom["rom_path"] in _zip_names(resp.content)


def test_download_package_ships_a_lone_opted_in_homebrew_bin_without_cover(client, make_rom, session_id):
    """The "is there anything to package?" gate has to ask the same question the zip
    builder answers. It used to run _excluded() WITHOUT homebrew_roms, so it couldn't
    see that a homebrew .bin had been opted into the SD — and a cover-less opted-in
    .bin as the session's only content 404'd on a build that would have contained it."""
    rom = make_rom(system_key="homebrew", name="App.bin")
    client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/sd-include", json={"include": True})

    resp = client.get(f"/api/sessions/{session_id}/package")

    assert resp.status_code == 200
    assert rom["rom_path"] in _zip_names(resp.content)


def test_download_package_still_404s_when_the_only_rom_is_excluded_from_sd(client, make_rom, session_id):
    """The mirror image: the gate must also honour sd_exclude, or it would promise a
    build whose every file the builder then filters out."""
    rom = make_rom(system_key="nes", name="Game.nes")
    client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/sd-exclude", json={"exclude": True})

    resp = client.get(f"/api/sessions/{session_id}/package")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Nothing to package yet"


def test_download_package_etag_returns_304_when_unchanged(client, make_rom, session_id):
    make_rom(system_key="nes", name="Game.nes")

    first = client.get(f"/api/sessions/{session_id}/package")
    etag = first.headers["etag"]

    second = client.get(f"/api/sessions/{session_id}/package", headers={"if-none-match": etag})

    assert second.status_code == 304


def test_download_package_etag_changes_when_library_changes(client, make_rom, session_id):
    make_rom(system_key="nes", name="Game.nes")
    first = client.get(f"/api/sessions/{session_id}/package")
    etag = first.headers["etag"]

    make_rom(system_key="gb", name="New.gb")
    second = client.get(f"/api/sessions/{session_id}/package", headers={"if-none-match": etag})

    assert second.status_code == 200
    assert second.headers["etag"] != etag


def test_download_package_unknown_session_404s(client):
    resp = client.get("/api/sessions/nope/package")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown session"


# ---------------------------------------------------------------------------
# package.py + packaging service — experimental-mode gating, end to end
# ---------------------------------------------------------------------------

def test_download_package_video_opt_in_requires_experimental_mode(client, make_rom, session_id, monkeypatch):
    make_rom(system_key="nes", name="Game.nes")
    media_dir = storage.media_dir(session_id)
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "clip.avi").write_bytes(b"AVI")

    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    official = client.get(f"/api/sessions/{session_id}/package", params={"video": "1"})
    assert f"{config.MEDIA_DIR_NAME}/clip.avi" not in _zip_names(official.content)

    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    lab_with_video = client.get(f"/api/sessions/{session_id}/package", params={"video": "1"})
    assert f"{config.MEDIA_DIR_NAME}/clip.avi" in _zip_names(lab_with_video.content)

    lab_default = client.get(f"/api/sessions/{session_id}/package")  # video not opted in
    assert f"{config.MEDIA_DIR_NAME}/clip.avi" not in _zip_names(lab_default.content)


def test_download_package_experimental_system_folders_gated(client, make_rom, session_id, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    ngp = make_rom(system_key="ngp", name="Game.ngp")

    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    official = client.get(f"/api/sessions/{session_id}/package")
    assert official.status_code == 404  # ngp is the ONLY content, and it's fork-only

    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    lab = client.get(f"/api/sessions/{session_id}/package")
    assert ngp["rom_path"] in _zip_names(lab.content)


# ---------------------------------------------------------------------------
# package.py — POST /package/build (async job) + poll/cancel via jobs.py
# ---------------------------------------------------------------------------

def test_start_package_build_404s_when_nothing_to_package(client, session_id):
    resp = client.post(f"/api/sessions/{session_id}/package/build")

    assert resp.status_code == 404


def test_start_package_build_ready_true_when_already_cached(client, make_rom, session_id):
    make_rom(system_key="nes", name="Game.nes")
    cached = client.get(f"/api/sessions/{session_id}/package")
    etag = cached.headers["etag"].strip('"')

    resp = client.post(f"/api/sessions/{session_id}/package/build")

    assert resp.status_code == 200
    assert resp.json() == {"ready": True, "job_id": None, "etag": etag}


def test_start_package_build_runs_a_real_job_to_completion_and_matches_download(client, make_rom, session_id):
    make_rom(system_key="nes", name="Game.nes", content=b"g" * 500)

    resp = client.post(f"/api/sessions/{session_id}/package/build")
    body = resp.json()
    assert resp.status_code == 200
    assert body["ready"] is False
    assert body["job_id"]

    final = _poll_job(client, body["job_id"])
    assert final["status"] == "done"
    assert final["progress"] == 1.0
    assert final["result"]["etag"]

    # The cached build is now reused by the plain download endpoint (no rebuild).
    downloaded = client.get(f"/api/sessions/{session_id}/package")
    assert downloaded.status_code == 200
    assert downloaded.headers["etag"].strip('"') == final["result"]["etag"]


def test_start_package_build_can_be_cancelled(client, make_rom, session_id, monkeypatch):
    make_rom(system_key="nes", name="Game.nes")
    started = threading.Event()
    proceed = threading.Event()

    def fake_run_job(job_id, _session_id, *_a, **_kw):
        jobs_service.update(job_id, status="running", progress=0.1)
        started.set()
        proceed.wait(timeout=5)
        if jobs_service.is_cancelled(job_id):
            jobs_service.update(job_id, status="cancelled")
        else:
            jobs_service.update(job_id, status="done", progress=1.0, result={"etag": "stub"})

    monkeypatch.setattr(package_router.packaging, "run_sd_zip_build_job", fake_run_job)

    resp = client.post(f"/api/sessions/{session_id}/package/build")
    job_id = resp.json()["job_id"]
    assert resp.json()["ready"] is False

    assert started.wait(timeout=5), "background worker never started"
    cancel_resp = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel_resp.json() == {"ok": True}
    proceed.set()

    final = _poll_job(client, job_id)
    assert final["status"] == "cancelled"


# ---------------------------------------------------------------------------
# data.py — scratch "DATA" file upload / list / download / delete
# ---------------------------------------------------------------------------

def test_list_data_empty_session(client, session_id):
    resp = client.get(f"/api/sessions/{session_id}/data")

    assert resp.status_code == 200
    assert resp.json() == {"files": []}


def test_upload_list_download_delete_round_trip(client, session_id):
    upload = client.post(
        f"/api/sessions/{session_id}/data",
        files=[
            ("files", ("notes.txt", b"hello world", "text/plain")),
            ("files", ("readme.md", b"# title", "text/markdown")),
        ],
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["stored"] == 2
    assert {f["name"] for f in body["files"]} == {"notes.txt", "readme.md"}

    listed = client.get(f"/api/sessions/{session_id}/data").json()
    assert {f["name"] for f in listed["files"]} == {"notes.txt", "readme.md"}

    downloaded = client.get(f"/api/sessions/{session_id}/data/notes.txt/download")
    assert downloaded.status_code == 200
    assert downloaded.content == b"hello world"

    deleted = client.delete(f"/api/sessions/{session_id}/data/notes.txt")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": "notes.txt"}

    after = client.get(f"/api/sessions/{session_id}/data").json()
    assert {f["name"] for f in after["files"]} == {"readme.md"}


def test_upload_data_reports_the_actual_streamed_size(client, session_id):
    payload = b"x" * 10_000
    resp = client.post(f"/api/sessions/{session_id}/data", files=[("files", ("big.bin", payload))])

    assert resp.status_code == 200
    assert resp.json()["files"][0]["size"] == len(payload)


def test_delete_data_missing_file_does_not_raise(client, session_id):
    resp = client.delete(f"/api/sessions/{session_id}/data/never-existed.txt")

    assert resp.status_code == 200
    assert resp.json() == {"deleted": "never-existed.txt"}


def test_download_data_missing_file_404s(client, session_id):
    resp = client.get(f"/api/sessions/{session_id}/data/nope.txt/download")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "파일이 없습니다"


def test_data_endpoints_unknown_session_404s(client):
    assert client.get("/api/sessions/nope/data").status_code == 404
    assert client.get("/api/sessions/nope/data/x/download").status_code == 404
    assert client.delete("/api/sessions/nope/data/x").status_code == 404


def test_safe_target_rejects_a_name_that_would_escape_the_scratch_dir(monkeypatch, session_id):
    """storage.safe_name() already strips '/'/'\\' from any name, so a real HTTP
    caller can never reach this guard through the public API — cover it
    directly by forcing safe_name to (hypothetically) hand back an escaping
    relative path, proving the defense-in-depth check itself works."""
    from app.routers.data import _safe_target

    monkeypatch.setattr(storage, "safe_name", lambda _name: "../escaped.txt")

    with pytest.raises(HTTPException) as exc:
        _safe_target(session_id, "whatever")
    assert exc.value.status_code == 400
