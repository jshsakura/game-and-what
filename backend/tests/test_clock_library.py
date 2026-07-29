# -*- coding: utf-8 -*-
"""The STORED half of the clock tools: POST /api/sessions/{id}/clock/{kind} keeps
a background GIF, an album photo or an alarm sound under /clock/<kind>, where it
is listed, previewable, renameable and packed into the SD zip.

A gif is converted server-side (ffmpeg, stubbed here); album/alarm files arrive
already converted by the browser and are stored verbatim.

Runs against the real app (DB + session).
"""
import pytest

from app import config, db
from app.services import packaging, storage, video

ALBUM_BYTES = 320 * 240 * 2


@pytest.fixture(autouse=True)
def fake_ffmpeg(monkeypatch):
    async def fake_encode(src, out, mode="fit", crop=None):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"GIF89a-fake-" + mode.encode())
        return out

    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video, "encode_to_clock_gif", fake_encode)


@pytest.fixture
def exp_mode(monkeypatch):
    """The clock endpoints are fork-firmware-only (see main._EXPERIMENTAL_ONLY)."""
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)


def _save(client, session_id, kind="gif", filename="Sunset Clip.mp4",
          content=b"fake-source-bytes", **data):
    return client.post(
        f"/api/sessions/{session_id}/clock/{kind}",
        files={"file": (filename, content, "application/octet-stream")},
        data=data,
    )


def _save_photo(client, session_id, filename="휴가 사진.565", **data):
    return _save(client, session_id, "album", filename, b"\x1f" * ALBUM_BYTES, **data)


def _save_alarm(client, session_id, filename="alarm.mp3", **data):
    return _save(client, session_id, "alarm", filename, b"ID3-fake-mp3", **data)


# ── gif: converted here ─────────────────────────────────────────────────────

def test_saved_gif_lands_in_clock_gif_and_lists(client, session_id, exp_mode):
    r = _save(client, session_id, mode="fill")
    assert r.status_code == 200, r.text
    row = r.json()
    assert (row["kind"], row["stored_name"]) == ("gif", "Sunset Clip.gif")
    assert row["file_path"] == "clock/gif/Sunset Clip.gif"
    assert row["source_bytes"] == len(b"fake-source-bytes")

    stored = storage.clock_dir(session_id, "gif") / "Sunset Clip.gif"
    assert stored.read_bytes() == b"GIF89a-fake-fill"   # mode threaded through
    assert row["size_bytes"] == stored.stat().st_size

    lib = client.get(f"/api/sessions/{session_id}/library").json()
    assert [f["id"] for f in lib["clock_files"]] == [row["id"]]


def test_second_convert_of_the_same_name_never_overwrites(client, session_id, exp_mode):
    first = _save(client, session_id).json()
    second = _save(client, session_id).json()
    assert second["stored_name"] == "Sunset Clip_2.gif"
    assert first["id"] != second["id"]
    gif_dir = storage.clock_dir(session_id, "gif")
    assert (gif_dir / "Sunset Clip.gif").exists()
    assert (gif_dir / "Sunset Clip_2.gif").exists()


def test_name_field_overrides_the_source_stem(client, session_id, exp_mode):
    assert _save(client, session_id, name="bg").json()["stored_name"] == "bg.gif"


def test_unnameable_source_falls_back_to_the_kind_default(client, session_id, exp_mode):
    assert _save(client, session_id, filename="???.mp4").json()["stored_name"] == "bg.gif"


# ── album: stored verbatim, previewed as PNG ────────────────────────────────

def test_album_photo_is_stored_byte_for_byte(client, session_id, exp_mode):
    row = _save_photo(client, session_id).json()
    assert (row["kind"], row["stored_name"]) == ("album", "휴가 사진.565")
    stored = storage.clock_dir(session_id, "album") / "휴가 사진.565"
    assert stored.read_bytes() == b"\x1f" * ALBUM_BYTES   # not re-encoded
    assert row["size_bytes"] == ALBUM_BYTES


def test_album_rejects_a_565_that_is_not_one_screen(client, session_id, exp_mode):
    r = _save(client, session_id, "album", "short.565", b"\x00" * 100)
    assert r.status_code == 422
    assert not list(storage.clock_dir(session_id, "album").glob("*")) if \
        storage.clock_dir(session_id, "album").exists() else True


def test_album_rejects_an_unconverted_image(client, session_id, exp_mode):
    r = _save(client, session_id, "album", "holiday.jpg", b"\xff\xd8\xff-jpeg")
    assert r.status_code == 415


def test_album_preview_renders_a_png_and_caches_it(client, session_id, exp_mode):
    # a real RGB565 screen (all one colour) so Pillow can actually decode it
    row = _save(client, session_id, "album", "flat.565", b"\x00\xf8" * (320 * 240)).json()
    r = client.get(f"/api/sessions/{session_id}/clock/album/{row['id']}/preview")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert storage.clock_preview_path(session_id, row["id"]).exists()

    # the cached PNG is web-only — it must never reach the card
    arcnames = [arc for _, arc in packaging._sd_entries(session_id, False, None, None)]
    assert not [a for a in arcnames if a.endswith(".png")]


def test_only_the_album_has_a_preview(client, session_id, exp_mode):
    gif_id = _save(client, session_id).json()["id"]
    assert client.get(f"/api/sessions/{session_id}/clock/gif/{gif_id}/preview").status_code == 404


# ── alarm: stored verbatim, with the clip length ────────────────────────────

def test_alarm_is_stored_with_its_clip_length(client, session_id, exp_mode):
    row = _save_alarm(client, session_id, seconds=10).json()
    assert (row["kind"], row["stored_name"], row["duration_s"]) == ("alarm", "alarm.mp3", 10.0)
    assert (storage.clock_dir(session_id, "alarm") / "alarm.mp3").read_bytes() == b"ID3-fake-mp3"


def test_alarm_rejects_a_non_mp3(client, session_id, exp_mode):
    assert _save(client, session_id, "alarm", "song.wav", b"RIFF").status_code == 415


# ── shared: serve / rename / delete / package ───────────────────────────────

def test_serve_and_download_endpoints(client, session_id, exp_mode):
    gif_id = _save(client, session_id, name="bg").json()["id"]

    inline = client.get(f"/api/sessions/{session_id}/clock/gif/{gif_id}/file")
    assert inline.status_code == 200
    assert inline.headers["content-type"] == "image/gif"
    assert inline.content == b"GIF89a-fake-fit"

    dl = client.get(f"/api/sessions/{session_id}/clock/gif/{gif_id}/download")
    assert dl.status_code == 200
    assert 'filename="bg.gif"' in dl.headers.get("content-disposition", "")


def test_alarm_is_served_as_audio(client, session_id, exp_mode):
    alarm_id = _save_alarm(client, session_id).json()["id"]
    r = client.get(f"/api/sessions/{session_id}/clock/alarm/{alarm_id}/file")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"


def test_rename_moves_the_file_and_keeps_the_extension(client, session_id, exp_mode):
    row = _save_photo(client, session_id).json()
    r = client.patch(f"/api/sessions/{session_id}/clock/album/{row['id']}", json={"name": "제주 바다"})
    assert r.status_code == 200
    assert r.json()["stored_name"] == "제주 바다.565"      # .565 survives the rename

    album = storage.clock_dir(session_id, "album")
    assert (album / "제주 바다.565").exists()
    assert not (album / "휴가 사진.565").exists()
    with db.connect() as conn:
        stored = conn.execute("SELECT file_path FROM clock_files WHERE id=?", (row["id"],)).fetchone()
    assert stored["file_path"] == "clock/album/제주 바다.565"


def test_rename_onto_an_existing_name_is_rejected(client, session_id, exp_mode):
    _save(client, session_id, name="bg")
    other = _save(client, session_id, name="other").json()
    r = client.patch(f"/api/sessions/{session_id}/clock/gif/{other['id']}", json={"name": "bg"})
    assert r.status_code == 409
    assert (storage.clock_dir(session_id, "gif") / "other.gif").exists()


def test_a_row_is_only_reachable_under_its_own_kind(client, session_id, exp_mode):
    gif_id = _save(client, session_id).json()["id"]
    assert client.get(f"/api/sessions/{session_id}/clock/album/{gif_id}/file").status_code == 404
    assert client.delete(f"/api/sessions/{session_id}/clock/album/{gif_id}").status_code == 404


def test_delete_trashes_the_file_and_drops_the_row(client, session_id, exp_mode):
    gif_id = _save(client, session_id, name="bg").json()["id"]
    assert client.delete(f"/api/sessions/{session_id}/clock/gif/{gif_id}").status_code == 200
    assert not (storage.clock_dir(session_id, "gif") / "bg.gif").exists()
    # soft delete — recoverable from _trash like every other library file
    assert (storage.trash_dir(session_id) / "clock__gif__bg.gif").exists()
    assert client.get(f"/api/sessions/{session_id}/library").json()["clock_files"] == []


def test_unknown_kind_and_unknown_id_are_404(client, session_id, exp_mode):
    assert _save(client, session_id, "wallpaper").status_code == 404
    assert client.get(f"/api/sessions/{session_id}/clock/gif/nope/file").status_code == 404
    assert client.delete(f"/api/sessions/{session_id}/clock/gif/nope").status_code == 404


def test_official_mode_blocks_the_endpoint(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    assert _save(client, session_id).status_code == 403


def test_every_kind_ships_in_the_sd_zip_only_on_a_fork_deploy(client, session_id, exp_mode, monkeypatch):
    _save(client, session_id, name="bg")
    _save_photo(client, session_id)
    _save_alarm(client, session_id)
    arcnames = [arc for _, arc in packaging._sd_entries(session_id, False, None, None)]
    assert {"clock/gif/bg.gif", "clock/album/휴가 사진.565", "clock/alarm/alarm.mp3"} <= set(arcnames)

    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    arcnames = [arc for _, arc in packaging._sd_entries(session_id, False, None, None)]
    assert not [a for a in arcnames if a.startswith("clock/")]
