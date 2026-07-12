# -*- coding: utf-8 -*-
"""Router-level coverage for the remaining small routers, all exercised through
the real app via `client`. Pinned behaviour:

  - manage.py: deleting a ROM soft-deletes its file + cover + extra_files
    sidecars to _trash and logs a restorable snapshot event; renaming moves the
    rom (+cover) as a set and only logs an event when the name actually changes;
    videos/music delete the same way (file to _trash + DB row gone).
  - videos.py / music.py are EXPERIMENTAL-ONLY routers (whole router 403 unless
    GNW_EXPERIMENTAL_MODE is on). ffmpeg is NEVER invoked for real here -- every
    `app.services.video` entry point the router touches is monkeypatched, the
    same way backend/tests/test_clock.py stubs it.
  - gamelist.py requires Korean mode, resolves an uploaded DATA file tolerant of
    NFC/NFD unicode, 400s on malformed XML, and renames only the matched roms.
  - events.py: list is newest-first and limit-clamped; restore-from-trash only
    works once, only within the retention window, only with a live snapshot,
    only onto a file still in _trash, and only if the rom id isn't already back.
  - jobs.py: plain get/cancel by id, 404 for an unknown one.
  - igdb/tgdb/sgdb/libretro search routers are thin (or, for tgdb, slightly
    less thin) wrappers around their services -- the services are mocked so
    "configured" / "missing key" / "provider error" are exercised without any
    network access.
"""
from __future__ import annotations

import json
import unicodedata

import pytest

from app import config, db
from app.services import events, jobs as jobs_service, storage, video
from app.services import igdb, libretro, steamgriddb, tgdb


# ---------------------------------------------------------------------------
# manage.py
# ---------------------------------------------------------------------------

def test_delete_rom_trashes_files_and_logs_a_restorable_snapshot(client, make_rom, session_id):
    rom = make_rom(extra_files=json.dumps([{"name": "extra.dat", "size": 3}]))
    sidecar = (storage.session_root(session_id) / rom["rom_path"]).parent / "extra.dat"
    sidecar.write_bytes(b"xyz")
    rom_file = storage.session_root(session_id) / rom["rom_path"]
    assert rom_file.exists()

    r = client.delete(f"/api/sessions/{session_id}/roms/{rom['id']}")

    assert r.status_code == 200
    assert r.json() == {"deleted": rom["id"]}
    assert not rom_file.exists()
    assert not sidecar.exists()  # sidecar trashed alongside the primary file
    with db.connect() as conn:
        assert conn.execute("SELECT 1 FROM roms WHERE id=?", (rom["id"],)).fetchone() is None
        ev = conn.execute(
            "SELECT meta FROM events WHERE rom_id=? AND event_type='rom_delete'", (rom["id"],)
        ).fetchone()
    assert json.loads(ev["meta"])["snapshot"]["id"] == rom["id"]


def test_delete_rom_404_for_unknown_rom(client, session_id):
    r = client.delete(f"/api/sessions/{session_id}/roms/does-not-exist")
    assert r.status_code == 404


def test_rename_rom_moves_the_file_and_logs_an_event(client, make_rom, session_id):
    rom = make_rom(name="Old.nes")

    r = client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}", json={"name": "New.nes"})

    assert r.status_code == 200
    body = r.json()
    assert body["stored_name"] == "New.nes"
    assert not (storage.session_root(session_id) / rom["rom_path"]).exists()
    assert (storage.session_root(session_id) / body["rom_path"]).exists()
    with db.connect() as conn:
        row = conn.execute("SELECT stored_name FROM roms WHERE id=?", (rom["id"],)).fetchone()
        assert row["stored_name"] == "New.nes"
        logged = conn.execute(
            "SELECT 1 FROM events WHERE rom_id=? AND event_type='rom_rename'", (rom["id"],)
        ).fetchone()
    assert logged is not None


def test_rename_rom_to_the_same_name_does_not_log_a_duplicate_event(client, make_rom, session_id):
    rom = make_rom(name="Same.nes")

    r = client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}", json={"name": "Same.nes"})

    assert r.status_code == 200
    with db.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) c FROM events WHERE rom_id=? AND event_type='rom_rename'", (rom["id"],)
        ).fetchone()["c"]
    assert count == 0


def test_rename_rom_rejects_blank_name(client, make_rom, session_id):
    rom = make_rom()
    r = client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}", json={"name": "   "})
    assert r.status_code == 400


def test_rename_rom_404_for_unknown_rom(client, session_id):
    r = client.patch(f"/api/sessions/{session_id}/roms/nope", json={"name": "X.nes"})
    assert r.status_code == 404


def test_rename_rom_409_on_filename_clash(client, make_rom, session_id):
    make_rom(name="Taken.nes")
    mover = make_rom(name="Mover.nes")

    r = client.patch(f"/api/sessions/{session_id}/roms/{mover['id']}", json={"name": "Taken.nes"})

    assert r.status_code == 409


def test_delete_video_removes_file_and_row(client, session_id):
    dst = storage.media_dir(session_id) / "clip.avi"
    storage.write_bytes(dst, b"AVI")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO videos (id, session_id, original_name, avi_name, avi_path, status) "
            "VALUES ('v1', ?, 'clip.mp4', 'clip.avi', ?, 'ok')",
            (session_id, storage.relative_to_session(session_id, dst)),
        )

    r = client.delete(f"/api/sessions/{session_id}/videos/v1")

    assert r.status_code == 200
    assert r.json() == {"deleted": "v1"}
    assert not dst.exists()
    with db.connect() as conn:
        assert conn.execute("SELECT 1 FROM videos WHERE id='v1'").fetchone() is None


def test_delete_video_404_for_unknown_video(client, session_id):
    r = client.delete(f"/api/sessions/{session_id}/videos/nope")
    assert r.status_code == 404


def test_delete_music_removes_file_and_row(client, session_id):
    dst = storage.music_dir(session_id) / "song.mp3"
    storage.write_bytes(dst, b"MP3")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO music (id, session_id, original_name, stored_name, music_path, size_bytes) "
            "VALUES ('m1', ?, 'song.mp3', 'song.mp3', ?, 3)",
            (session_id, storage.relative_to_session(session_id, dst)),
        )

    r = client.delete(f"/api/sessions/{session_id}/music/m1")

    assert r.status_code == 200
    assert r.json() == {"deleted": "m1"}
    assert not dst.exists()
    with db.connect() as conn:
        assert conn.execute("SELECT 1 FROM music WHERE id='m1'").fetchone() is None


def test_delete_music_404_for_unknown_music(client, session_id):
    r = client.delete(f"/api/sessions/{session_id}/music/nope")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# videos.py (experimental-only; ffmpeg fully stubbed)
# ---------------------------------------------------------------------------

def _poll_job(client, job_id: str, max_tries: int = 30) -> dict:
    """Round-trip the in-process background task to completion. No sleeps: each
    extra request round-trip gives the TestClient's event-loop thread another
    chance to run the scheduled task (proven to finish well within a handful of
    polls for our synchronous fakes -- usually the very first one)."""
    job = {}
    for _ in range(max_tries):
        r = client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200
        job = r.json()
        if job["status"] in ("done", "failed", "cancelled"):
            return job
    pytest.fail(f"job {job_id} never finished (last status={job.get('status')!r})")


def test_video_upload_403_when_experimental_mode_off(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    r = client.post(
        f"/api/sessions/{session_id}/videos",
        files={"file": ("clip.mp4", b"fake-video", "video/mp4")},
    )
    assert r.status_code == 403


def test_video_upload_503_when_ffmpeg_missing(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(video, "ffmpeg_available", lambda: False)
    r = client.post(
        f"/api/sessions/{session_id}/videos",
        files={"file": ("clip.mp4", b"fake-video", "video/mp4")},
    )
    assert r.status_code == 503


def test_video_upload_413_when_too_large(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(config, "MAX_VIDEO_BYTES", 4)
    r = client.post(
        f"/api/sessions/{session_id}/videos",
        files={"file": ("clip.mp4", b"way-too-big", "video/mp4")},
    )
    assert r.status_code == 413


def test_video_upload_encodes_in_the_background_and_marks_the_row_ok(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)

    async def fake_encode(src, dst, mode="fit"):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"AVI-FAKE-" + mode.encode())
        return dst

    async def fake_preview(src, dst):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"MP4-FAKE")
        return dst

    async def fake_thumb(src, dst, w=480, h=270):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"JPG-FAKE")
        return dst

    monkeypatch.setattr(video, "encode_to_mjpeg_avi", fake_encode)
    monkeypatch.setattr(video, "make_web_preview", fake_preview)
    monkeypatch.setattr(video, "make_thumb", fake_thumb)

    r = client.post(
        f"/api/sessions/{session_id}/videos",
        files={"file": ("clip.mp4", b"fake-video", "video/mp4")},
        data={"mode": "nonsense"},  # invalid -> falls back to the default fit
    )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "encoding"
    assert body["avi_name"] == "clip.avi"

    job = _poll_job(client, body["job_id"])
    assert job["status"] == "done"
    assert job["result"]["video_id"] == body["video_id"]

    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, avi_path FROM videos WHERE id=?", (body["video_id"],)
        ).fetchone()
    assert row["status"] == "ok"
    avi_path = storage.session_root(session_id) / row["avi_path"]
    assert avi_path.read_bytes() == b"AVI-FAKE-fit"  # bad mode fell back to fit
    # the temp source upload is cleaned up either way
    assert list(storage.media_dir(session_id).glob(".src_*")) == []


def test_video_upload_preview_thumb_failures_are_non_fatal(client, monkeypatch, session_id):
    """make_web_preview/make_thumb failing must not fail the encode -- the row
    still ends up 'ok', the card just falls back to an icon client-side."""
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)

    async def fake_encode(src, dst, mode="fit"):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"AVI-OK")
        return dst

    async def boom(*_a, **_kw):
        raise video.VideoEncodeError("no preview")

    monkeypatch.setattr(video, "encode_to_mjpeg_avi", fake_encode)
    monkeypatch.setattr(video, "make_web_preview", boom)
    monkeypatch.setattr(video, "make_thumb", boom)

    r = client.post(
        f"/api/sessions/{session_id}/videos",
        files={"file": ("clip.mp4", b"fake-video", "video/mp4")},
    )
    body = r.json()
    job = _poll_job(client, body["job_id"])
    assert job["status"] == "done"
    with db.connect() as conn:
        row = conn.execute(
            "SELECT status FROM videos WHERE id=?", (body["video_id"],)
        ).fetchone()
    assert row["status"] == "ok"


def test_video_upload_encode_failure_marks_job_and_row_failed(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)

    async def boom(src, dst, mode="fit"):
        raise video.VideoEncodeError("ffmpeg exploded")

    monkeypatch.setattr(video, "encode_to_mjpeg_avi", boom)

    r = client.post(
        f"/api/sessions/{session_id}/videos",
        files={"file": ("clip.mp4", b"fake-video", "video/mp4")},
    )
    body = r.json()

    job = _poll_job(client, body["job_id"])

    assert job["status"] == "failed"
    assert "ffmpeg exploded" in job["message"]
    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, avi_path FROM videos WHERE id=?", (body["video_id"],)
        ).fetchone()
    assert row["status"] == "failed"
    # no partial .avi and no leftover source temp file
    assert list(storage.media_dir(session_id).glob("*.avi")) == []
    assert list(storage.media_dir(session_id).glob(".src_*")) == []


# ---------------------------------------------------------------------------
# music.py (experimental-only; ffmpeg fully stubbed)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_real_album_art(monkeypatch):
    """optimize_album_art shells out to ffmpeg/PIL -- default it to a no-op
    across every music test; individual tests override it to exercise the
    shrink-and-update / exception-swallowed branches."""
    async def noop(_path):
        return False

    monkeypatch.setattr(video, "optimize_album_art", noop)


def test_music_upload_403_when_experimental_mode_off(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    r = client.post(
        f"/api/sessions/{session_id}/music",
        files={"file": ("song.mp3", b"ID3fake", "audio/mpeg")},
    )
    assert r.status_code == 403


def test_music_upload_mp3_is_stored_verbatim(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)

    r = client.post(
        f"/api/sessions/{session_id}/music",
        files={"file": ("My Song.mp3", b"ID3fake-bytes", "audio/mpeg")},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["stored_name"] == "My Song.mp3"
    assert body["size_bytes"] == len(b"ID3fake-bytes")
    stored = storage.session_root(session_id) / body["music_path"]
    assert stored.read_bytes() == b"ID3fake-bytes"
    with db.connect() as conn:
        assert conn.execute("SELECT 1 FROM music WHERE id=?", (body["id"],)).fetchone()


def test_music_upload_mp3_rejects_empty_file(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    r = client.post(
        f"/api/sessions/{session_id}/music",
        files={"file": ("song.mp3", b"", "audio/mpeg")},
    )
    assert r.status_code == 400


def test_music_upload_mp3_rejects_oversized_file(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(config, "MAX_MUSIC_BYTES", 4)
    r = client.post(
        f"/api/sessions/{session_id}/music",
        files={"file": ("song.mp3", b"way-too-big", "audio/mpeg")},
    )
    assert r.status_code == 413


def test_music_upload_non_mp3_503_when_ffmpeg_missing(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(video, "ffmpeg_available", lambda: False)
    r = client.post(
        f"/api/sessions/{session_id}/music",
        files={"file": ("clip.mp4", b"fake-video", "video/mp4")},
    )
    assert r.status_code == 503


def test_music_upload_non_mp3_extracts_audio_track(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)

    async def fake_extract(src, dst):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"MP3-FROM-VIDEO")
        return dst

    monkeypatch.setattr(video, "extract_mp3", fake_extract)

    r = client.post(
        f"/api/sessions/{session_id}/music",
        files={"file": ("MyClip.mp4", b"fake-video", "video/mp4")},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["stored_name"] == "MyClip.mp3"
    stored = storage.session_root(session_id) / body["music_path"]
    assert stored.read_bytes() == b"MP3-FROM-VIDEO"
    # transient extraction temp files never linger
    assert list(storage.music_dir(session_id).glob(".src_*")) == []
    assert list(storage.music_dir(session_id).glob(".out_*")) == []


def test_music_upload_non_mp3_rejects_empty_file(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    r = client.post(
        f"/api/sessions/{session_id}/music",
        files={"file": ("clip.mp4", b"", "video/mp4")},
    )
    assert r.status_code == 400


def test_music_upload_non_mp3_rejects_oversized_file(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(config, "MAX_VIDEO_BYTES", 4)
    r = client.post(
        f"/api/sessions/{session_id}/music",
        files={"file": ("clip.mp4", b"way-too-big", "video/mp4")},
    )
    assert r.status_code == 413


def test_music_upload_non_mp3_extract_failure_502(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)

    async def boom(src, dst):
        raise video.VideoEncodeError("no audio track")

    monkeypatch.setattr(video, "extract_mp3", boom)

    r = client.post(
        f"/api/sessions/{session_id}/music",
        files={"file": ("clip.mp4", b"fake-video", "video/mp4")},
    )

    assert r.status_code == 502
    assert "no audio track" in r.json()["detail"]


def test_music_upload_shrinks_and_reports_optimized_album_art_size(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)

    async def grows_the_file(path):
        path.write_bytes(path.read_bytes() + b"ART")
        return True

    monkeypatch.setattr(video, "optimize_album_art", grows_the_file)

    r = client.post(
        f"/api/sessions/{session_id}/music",
        files={"file": ("song.mp3", b"ID3fake", "audio/mpeg")},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["size_bytes"] == len(b"ID3fake") + 3
    with db.connect() as conn:
        row = conn.execute("SELECT size_bytes FROM music WHERE id=?", (body["id"],)).fetchone()
    assert row["size_bytes"] == len(b"ID3fake") + 3


def test_music_upload_album_art_optimization_failure_is_swallowed(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)

    async def boom(_path):
        raise RuntimeError("PIL blew up")

    monkeypatch.setattr(video, "optimize_album_art", boom)

    r = client.post(
        f"/api/sessions/{session_id}/music",
        files={"file": ("song.mp3", b"ID3fake", "audio/mpeg")},
    )

    assert r.status_code == 200  # best-effort: the upload itself still succeeds
    assert r.json()["size_bytes"] == len(b"ID3fake")


# ---------------------------------------------------------------------------
# gamelist.py
# ---------------------------------------------------------------------------

_GAMELIST_XML = """<?xml version="1.0"?>
<gameList>
  <game>
    <path>./nes/Contra.nes</path>
    <name>(K) Contra</name>
  </game>
</gameList>
"""


def _write_scratch_file(session_id: str, filename: str, text: str) -> None:
    d = storage.scratch_dir(session_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text(text, encoding="utf-8")


def test_gamelist_preview_requires_korean_mode(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "KOREAN_MODE", False)
    r = client.post(
        f"/api/sessions/{session_id}/gamelist/preview",
        json={"filename": "gamelist-nes.xml"},
    )
    assert r.status_code == 403


def test_gamelist_preview_404_when_data_file_missing(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "KOREAN_MODE", True)
    r = client.post(
        f"/api/sessions/{session_id}/gamelist/preview",
        json={"filename": "gamelist-nes.xml"},
    )
    assert r.status_code == 404


def test_gamelist_preview_400_on_malformed_xml(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "KOREAN_MODE", True)
    _write_scratch_file(session_id, "gamelist-nes.xml", "<gameList><game>")

    r = client.post(
        f"/api/sessions/{session_id}/gamelist/preview",
        json={"filename": "gamelist-nes.xml"},
    )

    assert r.status_code == 400


def test_gamelist_preview_reports_the_match_plan(client, monkeypatch, make_rom, session_id):
    monkeypatch.setattr(config, "KOREAN_MODE", True)
    make_rom(system_key="nes", name="Contra (USA).nes")
    _write_scratch_file(session_id, "gamelist-nes.xml", _GAMELIST_XML)

    r = client.post(
        f"/api/sessions/{session_id}/gamelist/preview",
        json={"filename": "gamelist-nes.xml"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["system"] == "nes"
    assert body["matched"] == 1
    assert body["plan"][0]["new"] == "(K) Contra.nes" or "Contra" in body["plan"][0]["new"]


def test_gamelist_preview_resolves_nfd_filenames_tolerantly(client, monkeypatch, session_id):
    """macOS uploads store filenames NFD-decomposed; the lookup must still find
    the file when the request names it in NFC form (or vice versa)."""
    monkeypatch.setattr(config, "KOREAN_MODE", True)
    nfd_name = unicodedata.normalize("NFD", "gamelist-한글.xml")
    _write_scratch_file(session_id, nfd_name, _GAMELIST_XML)
    nfc_name = unicodedata.normalize("NFC", "gamelist-한글.xml")

    r = client.post(
        f"/api/sessions/{session_id}/gamelist/preview",
        json={"filename": nfc_name, "system": "nes"},
    )

    assert r.status_code == 200


def test_gamelist_apply_requires_korean_mode(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "KOREAN_MODE", False)
    r = client.post(
        f"/api/sessions/{session_id}/gamelist/apply",
        json={"filename": "gamelist-nes.xml"},
    )
    assert r.status_code == 403


def test_gamelist_apply_404_when_data_file_missing(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "KOREAN_MODE", True)
    r = client.post(
        f"/api/sessions/{session_id}/gamelist/apply",
        json={"filename": "gamelist-nes.xml"},
    )
    assert r.status_code == 404


def test_gamelist_apply_400_on_malformed_xml(client, monkeypatch, session_id):
    monkeypatch.setattr(config, "KOREAN_MODE", True)
    _write_scratch_file(session_id, "gamelist-nes.xml", "<gameList><game>")
    r = client.post(
        f"/api/sessions/{session_id}/gamelist/apply",
        json={"filename": "gamelist-nes.xml"},
    )
    assert r.status_code == 400


def test_gamelist_apply_renames_matched_roms_on_disk_and_in_the_db(client, monkeypatch, make_rom, session_id):
    monkeypatch.setattr(config, "KOREAN_MODE", True)
    rom = make_rom(system_key="nes", name="Contra (USA).nes")
    _write_scratch_file(session_id, "gamelist-nes.xml", _GAMELIST_XML)

    r = client.post(
        f"/api/sessions/{session_id}/gamelist/apply",
        json={"filename": "gamelist-nes.xml"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["renamed"] == 1
    assert body["matched"] == 1
    assert not (storage.session_root(session_id) / rom["rom_path"]).exists()
    with db.connect() as conn:
        row = conn.execute("SELECT stored_name FROM roms WHERE id=?", (rom["id"],)).fetchone()
    assert row["stored_name"] != "Contra (USA).nes"


# ---------------------------------------------------------------------------
# events.py
# ---------------------------------------------------------------------------

def test_list_events_returns_newest_first(client, session_id):
    with db.connect() as conn:
        for i in range(3):
            conn.execute(
                "INSERT INTO events (id, session_id, event_type, created_at) "
                "VALUES (?, ?, 'rom_upload', datetime('now', ?))",
                (f"e{i}", session_id, f"+{i} seconds"),
            )

    r = client.get(f"/api/sessions/{session_id}/events")

    assert r.status_code == 200
    ids = [e["id"] for e in r.json()["events"]]
    assert ids[:2] == ["e2", "e1"]


def test_list_events_clamps_limit_to_at_least_one(client, session_id):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO events (id, session_id, event_type) VALUES ('e1', ?, 'rom_upload')",
            (session_id,),
        )
        conn.execute(
            "INSERT INTO events (id, session_id, event_type) VALUES ('e2', ?, 'rom_upload')",
            (session_id,),
        )

    # limit=0 is falsy in Python, so `limit or DEFAULT_LIMIT` substitutes the
    # default -- a genuinely negative limit is what exercises max(1, ...).
    r = client.get(f"/api/sessions/{session_id}/events", params={"limit": -5})

    assert r.status_code == 200
    assert len(r.json()["events"]) == 1


def test_list_events_clamps_limit_to_the_query_max(client, session_id):
    r = client.get(f"/api/sessions/{session_id}/events", params={"limit": 999999})
    assert r.status_code == 200  # would raise if the huge limit reached sqlite raw


def test_list_events_404_for_unknown_session(client):
    r = client.get("/api/sessions/does-not-exist/events")
    assert r.status_code == 404


def _delete_rom_via_api(client, session_id, rom_id) -> str:
    """Delete a rom through the real endpoint (so the snapshot event is built
    exactly the way production does it) and return the new event's id."""
    r = client.delete(f"/api/sessions/{session_id}/roms/{rom_id}")
    assert r.status_code == 200
    events_list = client.get(f"/api/sessions/{session_id}/events").json()["events"]
    return next(e["id"] for e in events_list if e["event_type"] == "rom_delete" and e["rom_id"] == rom_id)


def test_restore_event_brings_the_rom_back(client, make_rom, session_id):
    rom = make_rom()
    event_id = _delete_rom_via_api(client, session_id, rom["id"])

    r = client.post(f"/api/sessions/{session_id}/events/{event_id}/restore")

    assert r.status_code == 200
    assert r.json() == {"restored": event_id, "rom_id": rom["id"]}
    assert (storage.session_root(session_id) / rom["rom_path"]).exists()
    with db.connect() as conn:
        assert conn.execute("SELECT 1 FROM roms WHERE id=?", (rom["id"],)).fetchone()
        restore_logged = conn.execute(
            "SELECT 1 FROM events WHERE rom_id=? AND event_type='rom_restore'", (rom["id"],)
        ).fetchone()
    assert restore_logged is not None


def test_restore_event_brings_back_extra_files_sidecars_too(client, make_rom, session_id):
    rom = make_rom(extra_files=json.dumps([{"name": "extra.dat", "size": 3}]))
    sidecar = (storage.session_root(session_id) / rom["rom_path"]).parent / "extra.dat"
    sidecar.write_bytes(b"xyz")
    event_id = _delete_rom_via_api(client, session_id, rom["id"])
    assert not sidecar.exists()  # trashed by the delete

    r = client.post(f"/api/sessions/{session_id}/events/{event_id}/restore")

    assert r.status_code == 200
    assert sidecar.exists()
    assert sidecar.read_bytes() == b"xyz"


def test_restore_event_404_for_unknown_event(client, session_id):
    r = client.post(f"/api/sessions/{session_id}/events/nope/restore")
    assert r.status_code == 404


def test_restore_event_404_for_a_non_delete_event(client, session_id):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO events (id, session_id, event_type) VALUES ('e1', ?, 'rom_upload')",
            (session_id,),
        )
    r = client.post(f"/api/sessions/{session_id}/events/e1/restore")
    assert r.status_code == 404


def test_restore_event_409_when_already_restored(client, make_rom, session_id):
    rom = make_rom()
    event_id = _delete_rom_via_api(client, session_id, rom["id"])
    client.post(f"/api/sessions/{session_id}/events/{event_id}/restore")

    r = client.post(f"/api/sessions/{session_id}/events/{event_id}/restore")

    assert r.status_code == 409


def test_restore_event_410_outside_the_retention_window(client, make_rom, session_id):
    rom = make_rom()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO events (id, session_id, event_type, rom_id, meta, created_at) "
            "VALUES ('old1', ?, 'rom_delete', ?, ?, datetime('now', '-31 days'))",
            (session_id, rom["id"], json.dumps({"snapshot": dict(rom)})),
        )
    r = client.post(f"/api/sessions/{session_id}/events/old1/restore")
    assert r.status_code == 410


def test_restore_event_410_when_snapshot_has_no_id(client, session_id):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO events (id, session_id, event_type, meta) VALUES "
            "('bad1', ?, 'rom_delete', ?)",
            (session_id, json.dumps({"snapshot": {}})),
        )
    r = client.post(f"/api/sessions/{session_id}/events/bad1/restore")
    assert r.status_code == 410


def test_restore_event_409_when_rom_id_already_back_in_the_library(client, make_rom, session_id):
    rom = make_rom()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO events (id, session_id, event_type, rom_id, meta) VALUES "
            "('dup1', ?, 'rom_delete', ?, ?)",
            (session_id, rom["id"], json.dumps({"snapshot": dict(rom)})),
        )
    # rom row still exists (never actually deleted) -> restoring on top must conflict
    r = client.post(f"/api/sessions/{session_id}/events/dup1/restore")
    assert r.status_code == 409


def test_restore_event_410_when_the_trashed_file_is_gone(client, make_rom, session_id):
    rom = make_rom()
    event_id = _delete_rom_via_api(client, session_id, rom["id"])
    # purge the trash copy for real, simulating it having expired/been swept
    trashed = storage.trash_dir(session_id) / rom["rom_path"].replace("/", "__")
    trashed.unlink()

    r = client.post(f"/api/sessions/{session_id}/events/{event_id}/restore")

    assert r.status_code == 410


# ---------------------------------------------------------------------------
# jobs.py
# ---------------------------------------------------------------------------

def test_get_job_returns_the_job_state(client):
    jobs_service.create("job-a", "sd_zip")
    jobs_service.update("job-a", status="running", progress=0.4, message="working")

    r = client.get("/api/jobs/job-a")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "running"
    assert body["progress"] == 0.4


def test_get_job_404_for_unknown_job(client):
    r = client.get("/api/jobs/does-not-exist")
    assert r.status_code == 404


def test_cancel_job_flags_a_known_job(client):
    jobs_service.create("job-b", "sd_zip")

    r = client.post("/api/jobs/job-b/cancel")

    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert jobs_service.is_cancelled("job-b") is True


def test_cancel_job_404_for_unknown_job(client):
    r = client.post("/api/jobs/does-not-exist/cancel")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# igdb.py / tgdb.py / sgdb.py / libretro.py -- thin cover-search providers
# ---------------------------------------------------------------------------

async def _fake_search_covers(q, system=None, limit=12):
    return {"available": True, "results": [{"name": q, "year": 1990,
                                             "cover_url": "http://x/big.jpg",
                                             "thumb_url": "http://x/small.jpg"}]}


def test_igdb_search_configured_passes_through_the_service_result(client, monkeypatch):
    monkeypatch.setattr(igdb, "search_covers", _fake_search_covers)
    r = client.get("/api/igdb/search", params={"q": "Mario", "system": "nes"})
    assert r.status_code == 200
    assert r.json()["results"][0]["name"] == "Mario"


def test_igdb_search_missing_credentials_reports_unavailable(client, monkeypatch):
    async def unavailable(q, system=None, limit=12):
        return {"available": False, "results": []}

    monkeypatch.setattr(igdb, "search_covers", unavailable)
    r = client.get("/api/igdb/search", params={"q": "Mario"})
    assert r.json() == {"available": False, "results": []}


def test_igdb_search_provider_error_still_returns_200_with_error_field(client, monkeypatch):
    async def errored(q, system=None, limit=12):
        return {"available": True, "results": [], "error": "IGDB 요청 실패"}

    monkeypatch.setattr(igdb, "search_covers", errored)
    r = client.get("/api/igdb/search", params={"q": "Mario"})
    assert r.status_code == 200
    assert r.json()["error"] == "IGDB 요청 실패"


def test_tgdb_search_blank_query_short_circuits_before_hitting_search(client, monkeypatch):
    """A whitespace-only query never reaches tgdb.search() (no quota spent),
    but availability is still reported so the UI can show the right state."""
    monkeypatch.setattr(tgdb, "available", lambda: True)

    async def must_not_be_called(name, system_key):
        raise AssertionError("tgdb.search() must not be called for a blank query")

    monkeypatch.setattr(tgdb, "search", must_not_be_called)

    r = client.get("/api/tgdb/search", params={"q": "   "})

    assert r.json() == {"available": True, "results": [], "quota_exceeded": False}


def test_tgdb_search_reports_unavailable_when_no_api_key(client, monkeypatch):
    monkeypatch.setattr(tgdb, "available", lambda: False)
    r = client.get("/api/tgdb/search", params={"q": "Mario"})
    assert r.json() == {"available": False, "results": [], "quota_exceeded": False}


def test_tgdb_search_maps_candidates_and_quota_flag(client, monkeypatch):
    monkeypatch.setattr(tgdb, "available", lambda: True)

    async def fake_search(name, system_key):
        return {"candidates": [("Super Mario Bros.", "http://x/mario.jpg")], "quota_exceeded": True}

    monkeypatch.setattr(tgdb, "search", fake_search)
    r = client.get("/api/tgdb/search", params={"q": "mario", "system": "nes", "limit": 5})

    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["quota_exceeded"] is True
    assert body["results"] == [{
        "name": "Super Mario Bros.", "year": None,
        "cover_url": "http://x/mario.jpg", "thumb_url": "http://x/mario.jpg",
    }]


def test_sgdb_search_passes_through_the_service_result(client, monkeypatch):
    async def fake(query, limit=12):
        return {"available": True, "results": [{"name": query, "year": None,
                                                 "cover_url": "u", "thumb_url": "u"}]}

    monkeypatch.setattr(steamgriddb, "search", fake)
    r = client.get("/api/sgdb/search", params={"q": "Zelda"})
    assert r.status_code == 200
    assert r.json()["results"][0]["name"] == "Zelda"


def test_sgdb_search_missing_key_reports_unavailable(client, monkeypatch):
    async def fake(query, limit=12):
        return {"available": False, "results": []}

    monkeypatch.setattr(steamgriddb, "search", fake)
    r = client.get("/api/sgdb/search", params={"q": "Zelda"})
    assert r.json() == {"available": False, "results": []}


def test_libretro_search_passes_through_system_and_limit(client, monkeypatch):
    captured = {}

    async def fake(q, system, limit):
        captured["args"] = (q, system, limit)
        return {"available": True, "results": []}

    monkeypatch.setattr(libretro, "search_covers", fake)
    r = client.get("/api/libretro/search", params={"q": "Contra", "system": "gamecom", "limit": 7})

    assert r.status_code == 200
    assert captured["args"] == ("Contra", "gamecom", 7)


def test_libretro_search_unavailable_system_reports_unavailable(client, monkeypatch):
    async def fake(q, system, limit):
        return {"available": False, "results": []}

    monkeypatch.setattr(libretro, "search_covers", fake)
    r = client.get("/api/libretro/search", params={"q": "Contra"})
    assert r.json() == {"available": False, "results": []}
