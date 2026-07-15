# -*- coding: utf-8 -*-
"""Router-level coverage for app.routers.covers — cover search/generation,
manual upload, auto-fill fallback chain (IGDB -> TheGamesDB -> libretro ->
platform-less retries), crop/reposition, flag baking, deletion, and every
preview/device serving + download path.

Pins: real HTTP round-trips through the FastAPI TestClient against the actual
app, with real Pillow image encode/decode (render_cover/render_preview/
render_display are genuinely exercised end-to-end). ONLY the network-facing
provider calls (igdb.search_covers/resolve, tgdb.cover_candidates,
artfetch.fetch_image, covers_pico8.render_pico8_cover) are monkeypatched at
the service boundary the router imports them through — no real network is
ever reached (see conftest's autouse `no_network`). Small real images are
built in-memory with PIL wherever decodable bytes are needed.

A handful of the router's private pure-string-processing helpers (crop
parsing, region-tag detection, English search-term derivation) are exercised
directly since they are pivotal to the auto-fill flow and are cheapest/most
precisely covered as unit tests.
"""
from __future__ import annotations

import json
from io import BytesIO

import pytest
from PIL import Image

from app import db
from app.routers import covers as covers_router
from app.services import artfetch, covers, covers_pico8, igdb, tgdb, storage


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _png_bytes(size=(300, 400), color=(120, 40, 200)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _row(rom_id: str) -> dict:
    with db.connect() as conn:
        return dict(conn.execute("SELECT * FROM roms WHERE id = ?", (rom_id,)).fetchone())


async def _fetch_ok(_url):
    return _png_bytes()


async def _fetch_none(_url):
    return None


async def _igdb_miss(_query, _system=None, limit=8):
    return {"results": []}


async def _tgdb_miss(_name, _system_key):
    return []


# --------------------------------------------------------------------------- #
# GET cover (preview / full / device serving)
# --------------------------------------------------------------------------- #

def test_get_cover_404_when_nothing_ever_uploaded(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="NoArt.nes")
    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cover")
    assert resp.status_code == 404


def test_get_cover_unknown_session_404(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="X.nes")
    resp = client.get(f"/api/sessions/does-not-exist/roms/{rom['id']}/cover")
    assert resp.status_code == 404


def test_get_cover_unknown_rom_404(client, session_id):
    resp = client.get(f"/api/sessions/{session_id}/roms/nope/cover")
    assert resp.status_code == 404


def test_get_cover_default_serves_cropped_display(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Art.nes")
    up = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    assert up.status_code == 200

    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cover")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/webp"
    # The default response is the rendered DISPLAY image, not the raw preview.
    preview_bytes = covers_router._preview_path(session_id, rom).read_bytes()
    assert resp.content != preview_bytes


def test_get_cover_full_serves_untouched_preview(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Art2.nes")
    client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cover?full=1")
    assert resp.status_code == 200
    preview_bytes = covers_router._preview_path(session_id, rom).read_bytes()
    assert resp.content == preview_bytes


def test_get_cover_device_serves_raw_img(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Art3.nes")
    client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    row = _row(rom["id"])
    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cover?device=1")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    device_bytes = covers_router._cover_abs(session_id, row).read_bytes()
    assert resp.content == device_bytes


def test_get_cover_device_404_when_only_preview_exists(client, make_rom, session_id):
    """A rom that only has a preview file on disk (no device .img recorded in
    the DB) must 404 for ?device=1 even though the plain fetch succeeds."""
    rom = make_rom(system_key="nes", name="PreviewOnly.nes")
    storage.write_bytes(covers_router._preview_path(session_id, rom), covers.render_preview(_png_bytes()))
    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cover?device=1")
    assert resp.status_code == 404


def test_get_cover_falls_back_to_raw_preview_on_render_error(client, make_rom, session_id):
    """If the stored preview bytes are corrupt, render_display raises CoverError
    internally and the handler falls back to serving the raw bytes as-is."""
    rom = make_rom(system_key="nes", name="Corrupt.nes")
    storage.write_bytes(covers_router._preview_path(session_id, rom), b"not-an-image")
    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cover")
    assert resp.status_code == 200
    assert resp.content == b"not-an-image"


def test_get_cover_tolerates_corrupt_crop_box_json(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="BadCrop.nes")
    storage.write_bytes(covers_router._preview_path(session_id, rom), covers.render_preview(_png_bytes()))
    with db.connect() as conn:
        conn.execute("UPDATE roms SET crop_box = ? WHERE id = ?", ("not-json", rom["id"]))
    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cover")
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# GET cover/download
# --------------------------------------------------------------------------- #

def test_download_cover_original_404_without_preview(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="D1.nes")
    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/download?variant=original")
    assert resp.status_code == 404


def test_download_cover_device_404_without_cover(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="D2.nes")
    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/download")
    assert resp.status_code == 404


def test_download_cover_original_attachment(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="D3.nes")
    client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/download?variant=original")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/webp"
    assert "attachment" in resp.headers["content-disposition"]
    assert "D3" in resp.headers["content-disposition"]


def test_download_cover_device_attachment(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="D4.nes")
    client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert ".img" in resp.headers["content-disposition"]


def test_download_cover_korean_name_keeps_ascii_extension_and_utf8_full_name(client, make_rom, session_id):
    """stem is pure Hangul → the ascii-ignore fallback filename drops every
    Hangul char but keeps the (ascii) extension, while filename* carries the
    full UTF-8 name for browsers that support it."""
    rom = make_rom(system_key="nes", name="게임.nes", stored_name="게임.nes")
    client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    resp = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/download")
    assert resp.status_code == 200
    disposition = resp.headers["content-disposition"]
    assert 'filename=".img"' in disposition
    assert "filename*=UTF-8''%EA%B2%8C%EC%9E%84.img" in disposition


# --------------------------------------------------------------------------- #
# POST cover (manual upload)
# --------------------------------------------------------------------------- #

def test_upload_cover_success(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Up1.nes")
    resp = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cover_status"] == "ok"
    assert body["cover_size"] > 0
    row = _row(rom["id"])
    assert row["cover_status"] == "ok"
    assert row["cover_source"] == "manual"
    assert covers_router._cover_abs(session_id, row).exists()
    assert covers_router._preview_path(session_id, row).exists()


def test_upload_cover_with_crop_box_persists_it(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Up2.nes")
    crop = {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.5}
    resp = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
        data={"crop": json.dumps(crop)},
    )
    assert resp.status_code == 200
    row = _row(rom["id"])
    assert json.loads(row["crop_box"]) == [0.1, 0.1, 0.5, 0.5]


def test_upload_cover_with_unparsable_crop_falls_back_to_default_fit(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Up3.nes")
    resp = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
        data={"crop": "{not valid json"},
    )
    assert resp.status_code == 200
    row = _row(rom["id"])
    assert row["crop_box"] is None


def test_upload_cover_rejects_corrupt_bytes(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Up4.nes")
    resp = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", b"totally not an image", "image/png")},
    )
    assert resp.status_code == 422


def test_upload_cover_rejects_empty_file(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Up5.nes")
    resp = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", b"", "image/png")},
    )
    assert resp.status_code == 400


def test_upload_cover_rejects_oversized_file(client, make_rom, session_id, monkeypatch):
    monkeypatch.setattr(covers_router, "_MAX_COVER_UPLOAD_BYTES", 100)
    rom = make_rom(system_key="nes", name="Up6.nes")
    resp = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 413


def test_upload_cover_unknown_rom_404(client, session_id):
    resp = client.post(
        f"/api/sessions/{session_id}/roms/does-not-exist/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 404


def test_upload_cover_unknown_session_404(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Up7.nes")
    resp = client.post(
        f"/api/sessions/nope/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# POST cover/regenerate
# --------------------------------------------------------------------------- #

def test_regenerate_cover_pico8_uses_label_render(client, make_rom, session_id, monkeypatch):
    monkeypatch.setattr(covers_pico8, "render_pico8_cover", lambda _path: _png_bytes((100, 100)))
    rom = make_rom(system_key="pico8", name="Cart.p8", content=b"__label__\n" + b"0" * 128)
    resp = client.post(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/regenerate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cover_status"] == "ok"
    row = _row(rom["id"])
    assert row["cover_source"] == "auto"


def test_regenerate_cover_pico8_failure_marks_failed(client, make_rom, session_id, monkeypatch):
    def _raise(_path):
        raise covers.CoverError("no label")

    monkeypatch.setattr(covers_pico8, "render_pico8_cover", _raise)
    rom = make_rom(system_key="pico8", name="Cart2.p8", cover_status="none")
    resp = client.post(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/regenerate")
    assert resp.status_code == 200
    assert resp.json()["cover_status"] == "failed"


def test_regenerate_cover_fetches_art_and_saves(client, make_rom, session_id, monkeypatch):
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_ok)
    rom = make_rom(system_key="nes", name="Regen1.nes", cover_status="none")
    resp = client.post(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/regenerate")
    assert resp.status_code == 200
    assert resp.json()["cover_status"] == "ok"
    row = _row(rom["id"])
    assert row["cover_source"] == "auto"


def test_regenerate_cover_no_art_marks_failed_from_none(client, make_rom, session_id, monkeypatch):
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_none)
    rom = make_rom(system_key="nes", name="Regen2.nes", cover_status="none")
    resp = client.post(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/regenerate")
    assert resp.status_code == 200
    assert resp.json()["cover_status"] == "failed"


def test_regenerate_cover_no_art_keeps_existing_status(client, make_rom, session_id, monkeypatch):
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_none)
    rom = make_rom(system_key="nes", name="Regen3.nes", cover_status="ok", cover_path="covers/nes/x.img")
    resp = client.post(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/regenerate")
    assert resp.status_code == 200
    assert resp.json()["cover_status"] == "ok"
    assert resp.json()["cover_path"] == "covers/nes/x.img"


def test_regenerate_cover_render_error_treated_as_no_art(client, make_rom, session_id, monkeypatch):
    async def _fetch_bad(_url):
        return b"garbage-not-an-image"

    monkeypatch.setattr(artfetch, "fetch_image", _fetch_bad)
    rom = make_rom(system_key="nes", name="Regen4.nes", cover_status="none")
    resp = client.post(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/regenerate")
    assert resp.status_code == 200
    assert resp.json()["cover_status"] == "failed"


def test_regenerate_cover_unknown_system_key_500(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Regen5.nes")
    with db.connect() as conn:
        conn.execute("UPDATE roms SET system_key = ? WHERE id = ?", ("bogus-system", rom["id"]))
    resp = client.post(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/regenerate")
    assert resp.status_code == 500


def test_regenerate_cover_unknown_rom_404(client, session_id):
    resp = client.post(f"/api/sessions/{session_id}/roms/nope/cover/regenerate")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# POST autocover (+ autofill_rom fallback chain: IGDB -> TGDB -> libretro ->
# IGDB-no-platform -> TGDB-no-platform)
# --------------------------------------------------------------------------- #

def test_autocover_igdb_hit_covers_rom(client, make_rom, session_id, monkeypatch):
    async def _igdb_hit(query, system=None, limit=8):
        return {"results": [{"name": query, "cover_url": "https://igdb.example/c.jpg"}]}

    monkeypatch.setattr(igdb, "search_covers", _igdb_hit)
    monkeypatch.setattr(tgdb, "cover_candidates", _tgdb_miss)
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_ok)
    make_rom(system_key="nes", name="Zelda.nes", original_name="Zelda.nes")

    resp = client.post(f"/api/sessions/{session_id}/autocover", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"checked": 1, "covered": 1, "force": False}


def test_autocover_tgdb_fallback_covers_rom(client, make_rom, session_id, monkeypatch):
    async def _tgdb_hit(name, _system_key):
        return [(name, "https://tgdb.example/c.jpg")]

    monkeypatch.setattr(igdb, "search_covers", _igdb_miss)
    monkeypatch.setattr(tgdb, "cover_candidates", _tgdb_hit)
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_ok)
    make_rom(system_key="nes", name="Contra.nes", original_name="Contra.nes")

    resp = client.post(f"/api/sessions/{session_id}/autocover", json={})
    assert resp.json()["covered"] == 1


def test_autocover_libretro_fallback_covers_rom(client, make_rom, session_id, monkeypatch):
    monkeypatch.setattr(igdb, "search_covers", _igdb_miss)
    monkeypatch.setattr(tgdb, "cover_candidates", _tgdb_miss)
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_ok)  # only libretro url is ever fetched
    make_rom(system_key="nes", name="Metroid.nes", original_name="Metroid.nes")

    resp = client.post(f"/api/sessions/{session_id}/autocover", json={})
    body = resp.json()
    assert body["covered"] == 1


def test_autocover_igdb_no_platform_fallback_covers_rom(client, make_rom, session_id, monkeypatch):
    async def _igdb_platformless_hit(query, system=None, limit=8):
        if system is None:
            return {"results": [{"name": query, "cover_url": "https://igdb.example/np.jpg"}]}
        return {"results": []}

    async def _fetch_selective(url):
        if "raw.githubusercontent" in url:
            return None  # force the libretro step to miss
        return _png_bytes()

    monkeypatch.setattr(igdb, "search_covers", _igdb_platformless_hit)
    monkeypatch.setattr(tgdb, "cover_candidates", _tgdb_miss)
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_selective)
    make_rom(system_key="nes", name="Kirby.nes", original_name="Kirby.nes")

    resp = client.post(f"/api/sessions/{session_id}/autocover", json={})
    assert resp.json()["covered"] == 1


def test_autocover_tgdb_no_platform_fallback_covers_rom(client, make_rom, session_id, monkeypatch):
    async def _tgdb_platformless_hit(name, system_key):
        if system_key == "":
            return [(name, "https://tgdb.example/np.jpg")]
        return []

    async def _fetch_selective(url):
        if "raw.githubusercontent" in url:
            return None  # force the libretro step to miss
        return _png_bytes()

    monkeypatch.setattr(igdb, "search_covers", _igdb_miss)
    monkeypatch.setattr(tgdb, "cover_candidates", _tgdb_platformless_hit)
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_selective)
    make_rom(system_key="nes", name="Pilotwings.nes", original_name="Pilotwings.nes")

    resp = client.post(f"/api/sessions/{session_id}/autocover", json={})
    assert resp.json()["covered"] == 1


def test_autocover_render_error_leaves_rom_uncovered(client, make_rom, session_id, monkeypatch):
    """A provider hit whose bytes don't actually decode as an image must not
    crash the batch — autofill_rom swallows the CoverError and reports a miss."""
    async def _igdb_hit(query, system=None, limit=8):
        return {"results": [{"name": query, "cover_url": "https://igdb.example/c.jpg"}]}

    async def _fetch_garbage(_url):
        return b"garbage-not-an-image"

    monkeypatch.setattr(igdb, "search_covers", _igdb_hit)
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_garbage)
    make_rom(system_key="nes", name="Broken.nes", original_name="Broken.nes")

    resp = client.post(f"/api/sessions/{session_id}/autocover", json={})
    assert resp.json()["covered"] == 0


def test_autocover_skips_libretro_for_system_without_repo(client, make_rom, session_id, monkeypatch):
    """`ngp` has no libretro-thumbnails repo mapping, so _libretro_probe must
    bail out immediately (rather than probing) when every other source misses."""
    monkeypatch.setattr(igdb, "search_covers", _igdb_miss)
    monkeypatch.setattr(tgdb, "cover_candidates", _tgdb_miss)
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_none)
    make_rom(system_key="ngp", name="Pocket.ngp", original_name="Pocket.ngp")

    resp = client.post(f"/api/sessions/{session_id}/autocover", json={})
    assert resp.json() == {"checked": 1, "covered": 0, "force": False}


def test_autocover_total_miss_leaves_rom_uncovered(client, make_rom, session_id, monkeypatch):
    monkeypatch.setattr(igdb, "search_covers", _igdb_miss)
    monkeypatch.setattr(tgdb, "cover_candidates", _tgdb_miss)
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_none)
    make_rom(system_key="nes", name="Obscure.nes", original_name="Obscure.nes")

    resp = client.post(f"/api/sessions/{session_id}/autocover", json={})
    assert resp.json() == {"checked": 1, "covered": 0, "force": False}


def test_autocover_pico8_roms_are_never_touched(client, make_rom, session_id, monkeypatch):
    async def _igdb_would_hit(query, system=None, limit=8):
        return {"results": [{"name": query, "cover_url": "https://igdb.example/c.jpg"}]}

    monkeypatch.setattr(igdb, "search_covers", _igdb_would_hit)
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_ok)
    make_rom(system_key="pico8", name="Cart.p8", content=b"__label__\n" + b"0" * 128)

    resp = client.post(f"/api/sessions/{session_id}/autocover", json={})
    body = resp.json()
    # pico8 is still selected by the `cover_status != 'ok'` filter, but
    # autofill_rom() itself refuses to touch it.
    assert body["checked"] == 1
    assert body["covered"] == 0


def test_autocover_system_filter_scopes_query(client, make_rom, session_id, monkeypatch):
    async def _igdb_hit(query, system=None, limit=8):
        return {"results": [{"name": query, "cover_url": "https://igdb.example/c.jpg"}]}

    monkeypatch.setattr(igdb, "search_covers", _igdb_hit)
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_ok)
    make_rom(system_key="nes", name="NesGame.nes", original_name="NesGame.nes")
    make_rom(system_key="gb", name="GbGame.gb", original_name="GbGame.gb")

    resp = client.post(f"/api/sessions/{session_id}/autocover", json={"system": "gb"})
    body = resp.json()
    assert body["checked"] == 1
    assert body["covered"] == 1


def test_autocover_force_skips_manual_and_crop_covers(client, make_rom, session_id, monkeypatch):
    async def _igdb_hit(query, system=None, limit=8):
        return {"results": [{"name": query, "cover_url": "https://igdb.example/c.jpg"}]}

    monkeypatch.setattr(igdb, "search_covers", _igdb_hit)
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_ok)
    auto_rom = make_rom(
        system_key="nes", name="AutoOne.nes", original_name="AutoOne.nes",
        cover_status="ok", cover_source="auto", cover_path="covers/nes/AutoOne.img",
    )
    manual_rom = make_rom(
        system_key="nes", name="ManualOne.nes", original_name="ManualOne.nes",
        cover_status="ok", cover_source="manual", cover_path="covers/nes/ManualOne.img",
    )

    resp = client.post(f"/api/sessions/{session_id}/autocover", json={"force": True})
    body = resp.json()
    assert body["force"] is True
    assert body["checked"] == 1  # only the auto-sourced rom is a force target
    assert body["covered"] == 1
    manual_row = _row(manual_rom["id"])
    assert manual_row["cover_source"] == "manual"
    assert manual_row["cover_path"] == "covers/nes/ManualOne.img"


# --------------------------------------------------------------------------- #
# POST autoresolve (Korean-mode gated rename + cover fill)
# --------------------------------------------------------------------------- #

def test_autoresolve_requires_korean_mode(client, make_rom, session_id, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "KOREAN_MODE", False)
    make_rom(system_key="nes", name="Whatever.nes")
    resp = client.post(f"/api/sessions/{session_id}/autoresolve", json={})
    assert resp.status_code == 403


def test_autoresolve_renames_and_covers_on_hit(client, make_rom, session_id, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "KOREAN_MODE", True)

    async def _resolve_hit(query, system=None):
        return {"name": query, "korean": "한글타이틀", "cover_url": "https://igdb.example/c.jpg"}

    monkeypatch.setattr(igdb, "resolve", _resolve_hit)
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_ok)
    rom = make_rom(system_key="nes", name="Zelda.nes", original_name="Zelda.nes", cover_status="none")

    resp = client.post(f"/api/sessions/{session_id}/autoresolve", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["checked"] == 1
    assert body["renamed"] == 1
    assert body["covered"] == 1
    assert body["missing_count"] == 0

    row = _row(rom["id"])
    assert "한글타이틀" in row["stored_name"]
    assert row["cover_status"] == "ok"


def test_autoresolve_render_error_still_renames_but_skips_cover(client, make_rom, session_id, monkeypatch):
    """A resolve hit with a cover_url whose bytes don't decode must not crash the
    rename — the CoverError is swallowed and the cover is simply left unset."""
    from app import config

    monkeypatch.setattr(config, "KOREAN_MODE", True)

    async def _resolve_hit(query, system=None):
        return {"name": query, "korean": "한글타이틀2", "cover_url": "https://igdb.example/c.jpg"}

    async def _fetch_garbage(_url):
        return b"garbage-not-an-image"

    monkeypatch.setattr(igdb, "resolve", _resolve_hit)
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_garbage)
    rom = make_rom(system_key="nes", name="Metroid2.nes", original_name="Metroid2.nes", cover_status="none")

    resp = client.post(f"/api/sessions/{session_id}/autoresolve", json={})
    body = resp.json()
    assert body["renamed"] == 1
    assert body["covered"] == 0
    row = _row(rom["id"])
    assert "한글타이틀2" in row["stored_name"]
    assert row["cover_status"] == "none"


def test_autoresolve_records_missing_when_igdb_has_nothing(client, make_rom, session_id, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "KOREAN_MODE", True)

    async def _resolve_miss(_query, _system=None):
        return None

    monkeypatch.setattr(igdb, "resolve", _resolve_miss)
    rom = make_rom(system_key="nes", name="Obscure.nes", original_name="Obscure.nes")

    resp = client.post(f"/api/sessions/{session_id}/autoresolve", json={})
    body = resp.json()
    assert body["renamed"] == 0
    assert body["covered"] == 0
    assert body["missing_count"] == 1
    assert rom["stored_name"] in body["missing"]


def test_autoresolve_skips_already_korean_names(client, make_rom, session_id, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "KOREAN_MODE", True)
    make_rom(system_key="nes", name="한글게임.nes", stored_name="한글게임.nes")

    resp = client.post(f"/api/sessions/{session_id}/autoresolve", json={})
    assert resp.json()["checked"] == 0


def test_autoresolve_skips_pico8(client, make_rom, session_id, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "KOREAN_MODE", True)
    make_rom(system_key="pico8", name="Cart.p8", content=b"__label__\n" + b"0" * 128)

    resp = client.post(f"/api/sessions/{session_id}/autoresolve", json={})
    assert resp.json()["checked"] == 0


def test_autoresolve_system_filter(client, make_rom, session_id, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "KOREAN_MODE", True)

    async def _resolve_miss(_query, _system=None):
        return None

    monkeypatch.setattr(igdb, "resolve", _resolve_miss)
    make_rom(system_key="nes", name="NesGame.nes")
    make_rom(system_key="gb", name="GbGame.gb")

    resp = client.post(f"/api/sessions/{session_id}/autoresolve", json={"system": "gb"})
    assert resp.json()["checked"] == 1


# --------------------------------------------------------------------------- #
# DELETE cover
# --------------------------------------------------------------------------- #

def test_delete_cover_removes_files_and_resets_status(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Del1.nes")
    client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    row = _row(rom["id"])
    cover_path = covers_router._cover_abs(session_id, row)
    preview_path = covers_router._preview_path(session_id, row)
    assert cover_path.exists() and preview_path.exists()

    resp = client.delete(f"/api/sessions/{session_id}/roms/{rom['id']}/cover")
    assert resp.status_code == 200
    assert resp.json() == {"rom_id": rom["id"], "cover_status": "none"}
    assert not cover_path.exists()
    assert not preview_path.exists()
    row2 = _row(rom["id"])
    assert row2["cover_path"] is None
    assert row2["cover_status"] == "none"


def test_delete_cover_is_a_noop_without_a_cover(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Del2.nes")
    resp = client.delete(f"/api/sessions/{session_id}/roms/{rom['id']}/cover")
    assert resp.status_code == 200
    assert resp.json()["cover_status"] == "none"


def test_delete_cover_unknown_rom_404(client, session_id):
    resp = client.delete(f"/api/sessions/{session_id}/roms/nope/cover")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# POST cover/recrop
# --------------------------------------------------------------------------- #

def test_recrop_requires_existing_cover(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Crop1.nes", cover_status="none")
    resp = client.post(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/recrop", json={})
    assert resp.status_code == 400


def test_recrop_404_when_source_missing_on_disk(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Crop2.nes", cover_status="ok")
    resp = client.post(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/recrop", json={})
    assert resp.status_code == 404


def test_recrop_success_marks_source_crop(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Crop3.nes")
    client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    resp = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover/recrop",
        json={"crop": {"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5}},
    )
    assert resp.status_code == 200
    row = _row(rom["id"])
    assert row["cover_source"] == "crop"
    assert json.loads(row["crop_box"]) == [0.0, 0.0, 0.5, 0.5]


def test_recrop_with_null_crop_resets_to_fit(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Crop4.nes")
    client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    resp = client.post(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/recrop", json={"crop": None})
    assert resp.status_code == 200
    row = _row(rom["id"])
    assert row["crop_box"] is None


def test_recrop_422_on_corrupt_preview(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Crop5.nes")
    client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    storage.write_bytes(covers_router._preview_path(session_id, rom), b"garbage")
    resp = client.post(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/recrop", json={})
    assert resp.status_code == 422


def test_recrop_falls_back_to_device_img_when_no_preview(client, make_rom, session_id):
    """If only the device .img survives (no web preview on disk), recrop should
    still find a source to re-crop from."""
    rom = make_rom(system_key="nes", name="Crop6.nes", cover_status="ok",
                    cover_path="covers/nes/Crop6.img")
    storage.write_bytes(covers_router._cover_abs(session_id, _row(rom["id"])), _png_bytes((186, 100)))
    resp = client.post(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/recrop", json={})
    assert resp.status_code == 200


def test_recrop_unknown_rom_404(client, session_id):
    resp = client.post(f"/api/sessions/{session_id}/roms/nope/cover/recrop", json={})
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# PATCH cover/flag
# --------------------------------------------------------------------------- #

def test_set_flag_requires_the_key(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Flag1.nes")
    resp = client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/flag", json={})
    assert resp.status_code == 400


def test_set_flag_rejects_unsupported_flag(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Flag2.nes")
    resp = client.patch(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover/flag", json={"cover_flag": "xx"}
    )
    assert resp.status_code == 400


def test_set_flag_rebakes_existing_cover(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Flag3.nes")
    client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )
    resp = client.patch(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover/flag", json={"cover_flag": "ko"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"rom_id": rom["id"], "cover_flag": "ko", "rebaked": True}
    row = _row(rom["id"])
    assert row["cover_flag"] == "ko"


def test_set_flag_without_cover_does_not_rebake(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Flag4.nes", cover_status="none")
    resp = client.patch(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover/flag", json={"cover_flag": "ja"}
    )
    assert resp.status_code == 200
    assert resp.json()["rebaked"] is False


def test_set_flag_null_clears_it(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Flag5.nes", cover_flag="ko")
    resp = client.patch(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover/flag", json={"cover_flag": None}
    )
    assert resp.status_code == 200
    assert resp.json()["cover_flag"] is None
    assert _row(rom["id"])["cover_flag"] is None


def test_set_flag_unknown_rom_404(client, session_id):
    resp = client.patch(
        f"/api/sessions/{session_id}/roms/nope/cover/flag", json={"cover_flag": "ko"}
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# POST cover/from-url
# --------------------------------------------------------------------------- #

def test_cover_from_url_requires_url(client, make_rom, session_id):
    rom = make_rom(system_key="nes", name="Url1.nes")
    resp = client.post(f"/api/sessions/{session_id}/roms/{rom['id']}/cover/from-url", json={})
    assert resp.status_code == 400


def test_cover_from_url_422_when_fetch_fails(client, make_rom, session_id, monkeypatch):
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_none)
    rom = make_rom(system_key="nes", name="Url2.nes")
    resp = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover/from-url",
        json={"url": "https://example.com/x.jpg"},
    )
    assert resp.status_code == 422


def test_cover_from_url_422_on_render_error(client, make_rom, session_id, monkeypatch):
    async def _fetch_bad(_url):
        return b"garbage"

    monkeypatch.setattr(artfetch, "fetch_image", _fetch_bad)
    rom = make_rom(system_key="nes", name="Url3.nes")
    resp = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover/from-url",
        json={"url": "https://example.com/x.jpg"},
    )
    assert resp.status_code == 422


def test_cover_from_url_success_with_crop(client, make_rom, session_id, monkeypatch):
    monkeypatch.setattr(artfetch, "fetch_image", _fetch_ok)
    rom = make_rom(system_key="nes", name="Url4.nes")
    resp = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cover/from-url",
        json={"url": "https://example.com/x.jpg", "crop": {"x": 0, "y": 0, "width": 1, "height": 1}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cover_status"] == "ok"
    row = _row(rom["id"])
    assert row["cover_source"] == "manual"
    assert json.loads(row["crop_box"]) == [0, 0, 1, 1]


def test_cover_from_url_unknown_rom_404(client, session_id):
    resp = client.post(
        f"/api/sessions/{session_id}/roms/nope/cover/from-url", json={"url": "https://x/y.jpg"}
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Pure-function unit tests: crop parsing, region-tag/search-term derivation,
# and the small path/flag helpers that back the endpoints above.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("crop, expected", [
    (None, None),
    ("", None),
    ({}, None),
    ({"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}, (0.1, 0.2, 0.3, 0.4)),
    ('{"x": 0, "y": 0, "width": 0.5, "height": 0.5}', (0.0, 0.0, 0.5, 0.5)),
    ("{not valid json", None),
    ({"x": 0, "y": 0, "width": 0, "height": 0.5}, None),  # zero width rejected
    ({"x": 0, "y": 0}, None),  # missing keys
])
def test_parse_crop(crop, expected):
    assert covers_router._parse_crop(crop) == expected


@pytest.mark.parametrize("text, expected", [
    ("Japan", True),
    ("Japan, USA", True),
    ("Japan, Foo", False),
    ("", False),
    ("Super Game", False),
])
def test_is_region_tag(text, expected):
    assert covers_router._is_region_tag(text) == expected


def test_strip_tags_removes_parens_and_brackets():
    assert covers_router._strip_tags("Game (Japan) [!]") == "Game"


def test_search_term_prefers_english_in_parens_when_stem_is_non_latin():
    assert covers_router._search_term(None, "타이틀 (Super Game).nes") == "Super Game"


def test_search_term_ignores_region_tag_parens_and_falls_back_to_stem():
    assert covers_router._search_term(None, "타이틀 (Japan).nes") == "타이틀 (Japan)"


def test_search_term_uses_latin_base_even_with_parens_present():
    assert covers_router._search_term(None, "Super Mario (Japan).nes") == "Super Mario"


def test_search_term_falls_back_to_korean_name_when_nothing_searchable():
    assert covers_router._search_term("한글이름", "타이틀.nes") == "한글이름"


def test_search_term_prefers_english_in_parens_even_when_korean_prefix_has_latin_suffix():
    # A Korean prefix carrying a trailing Latin abbreviation ("CD") used to be
    # mistaken for a latin stem, losing the real English title in the parens.
    assert covers_router._search_term(None, "파이널 파이트 CD (Final Fight CD).chd") == "Final Fight CD"


def test_term_variants_moves_leading_article():
    variants = covers_router._term_variants("Story of Thor, The")
    assert "The Story of Thor" in variants
    assert "Story of Thor" in variants


def test_term_variants_splits_tilde_localized_titles():
    variants = covers_router._term_variants("Bare Knuckle ~ Streets of Rage")
    assert "Bare Knuckle" in variants
    assert "Streets of Rage" in variants


def test_term_variants_drops_subtitle_after_dash():
    variants = covers_router._term_variants("Ys III - Wanderers from Ys")
    assert "Ys III" in variants


def test_term_variants_strips_bracketed_tags():
    variants = covers_router._term_variants("Banana (VTech Socrates)")
    assert "Banana" in variants


def test_clean_original_strips_noise_tokens():
    cleaned = covers_router._clean_original("한글_Super Game (Japan) v20160324 J-K.nes")
    assert cleaned == "Super Game"


def test_has_latin_and_has_searchable():
    assert covers_router._has_latin("Mario") is True
    assert covers_router._has_latin("마리오") is False
    assert covers_router._has_searchable("1942") is True
    assert covers_router._has_searchable("마리오") is False


def test_rom_terms_combines_stored_and_original_names():
    rom = {
        "korean_name": "타이틀",
        "stored_name": "타이틀 (Super Game).nes",
        "original_name": "Super_Game_Original (USA).nes",
    }
    assert covers_router._rom_terms(rom) == ["Super Game", "Super_Game_Original"]


def test_rom_terms_empty_when_nothing_latin_or_numeric():
    rom = {"korean_name": None, "stored_name": "타이틀.nes", "original_name": "원본이름.nes"}
    assert covers_router._rom_terms(rom) == []


def test_dirname_of_normal_path():
    assert covers_router._dirname_of({"rom_path": "roms/nes/Game.nes"}) == "nes"


def test_dirname_of_short_path_falls_back_to_unknown():
    assert covers_router._dirname_of({"rom_path": "Game.nes"}) == "unknown"










def test_rom_lang_lowercases_and_defaults_to_none():
    assert covers_router._rom_lang({"cover_flag": "KO"}) == "ko"
    assert covers_router._rom_lang({"cover_flag": ""}) is None
    assert covers_router._rom_lang({}) is None


def test_cover_abs_none_without_cover_path(session_id):
    assert covers_router._cover_abs(session_id, {"cover_path": None}) is None


def test_cover_abs_builds_path_when_present(session_id):
    result = covers_router._cover_abs(session_id, {"cover_path": "covers/nes/Game.img"})
    assert result is not None
    assert result.name == "Game.img"


# --------------------------------------------------------------------------- #
# rebake_cover_img — direct unit coverage of edge cases not easily reached
# through a single HTTP call.
# --------------------------------------------------------------------------- #

def test_rebake_false_when_cover_not_ok(make_rom, session_id):
    rom = make_rom(system_key="nes", name="Rebake1.nes", cover_status="none")
    assert covers_router.rebake_cover_img(session_id, rom) is False


def test_rebake_false_when_preview_missing(make_rom, session_id):
    rom = make_rom(system_key="nes", name="Rebake2.nes", cover_status="ok")
    assert covers_router.rebake_cover_img(session_id, rom) is False


def test_rebake_success_writes_new_device_img(make_rom, session_id):
    rom = make_rom(system_key="nes", name="Rebake3.nes", cover_status="ok")
    storage.write_bytes(covers_router._preview_path(session_id, rom), covers.render_preview(_png_bytes()))
    assert covers_router.rebake_cover_img(session_id, rom) is True
    cover_path = storage.covers_dir(session_id, "nes") / covers.cover_filename(rom["stored_name"])
    assert cover_path.exists() and cover_path.stat().st_size > 0


def test_rebake_tolerates_corrupt_crop_box(make_rom, session_id):
    rom = make_rom(system_key="nes", name="Rebake4.nes", cover_status="ok", crop_box="not-json")
    storage.write_bytes(covers_router._preview_path(session_id, rom), covers.render_preview(_png_bytes()))
    assert covers_router.rebake_cover_img(session_id, rom) is True


def test_rebake_false_on_render_error(make_rom, session_id):
    rom = make_rom(system_key="nes", name="Rebake5.nes", cover_status="ok")
    storage.write_bytes(covers_router._preview_path(session_id, rom), b"garbage-not-an-image")
    assert covers_router.rebake_cover_img(session_id, rom) is False
