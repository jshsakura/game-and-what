# -*- coding: utf-8 -*-
"""app/main.py (app wiring, /api/health, /api/config, /api/systems, the
experimental-only router gate) and app/routers/sessions.py (session lifecycle
+ library listing, the require_* dependency helpers).

IMPORTANT: the project's real .env sets GNW_KOREAN_MODE=true and
GNW_EXPERIMENTAL_MODE=true (this is a personal deploy), so config.KOREAN_MODE
/ config.EXPERIMENTAL_MODE default to True in THIS dev environment — every
test below explicitly monkeypatches both flags rather than relying on their
default, exactly like the existing test_experimental_mode.py does.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import config
from app.routers import sessions
from app.systems import get_system


# ── app-level endpoints ──────────────────────────────────────────────────────

def test_health_reports_ok_and_an_ffmpeg_flag(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["ffmpeg"], bool)


def test_config_reflects_korean_mode_flag(client, monkeypatch):
    monkeypatch.setattr(config, "KOREAN_MODE", True)
    assert client.get("/api/config").json()["korean_mode"] is True

    monkeypatch.setattr(config, "KOREAN_MODE", False)
    assert client.get("/api/config").json()["korean_mode"] is False


def test_config_reflects_experimental_mode_flag(client, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    assert client.get("/api/config").json()["experimental_mode"] is True

    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    assert client.get("/api/config").json()["experimental_mode"] is False


def test_config_cover_sources_libretro_always_on_others_follow_keys(client, monkeypatch):
    monkeypatch.setattr(config, "IGDB_CLIENT_ID", "")
    monkeypatch.setattr(config, "IGDB_CLIENT_SECRET", "")
    monkeypatch.setattr(config, "TGDB_API_KEY", "")
    monkeypatch.setattr(config, "STEAMGRIDDB_API_KEY", "")

    sources = client.get("/api/config").json()["cover_sources"]
    assert sources == {"libretro": True, "igdb": False, "tgdb": False, "sgdb": False}

    monkeypatch.setattr(config, "IGDB_CLIENT_ID", "id")
    monkeypatch.setattr(config, "IGDB_CLIENT_SECRET", "secret")
    monkeypatch.setattr(config, "TGDB_API_KEY", "key")
    monkeypatch.setattr(config, "STEAMGRIDDB_API_KEY", "key")

    sources = client.get("/api/config").json()["cover_sources"]
    assert sources == {"libretro": True, "igdb": True, "tgdb": True, "sgdb": True}


def test_config_igdb_requires_both_id_and_secret(client, monkeypatch):
    # Half a credential pair must not read as "configured".
    monkeypatch.setattr(config, "IGDB_CLIENT_ID", "id-only")
    monkeypatch.setattr(config, "IGDB_CLIENT_SECRET", "")
    assert client.get("/api/config").json()["cover_sources"]["igdb"] is False


def test_list_systems_official_mode_excludes_experimental_systems(client, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    body = client.get("/api/systems").json()
    keys = {s["key"] for s in body["systems"]}
    assert "ngp" not in keys
    assert "nes" in keys
    assert all(s["experimental"] is False for s in body["systems"])


def test_list_systems_experimental_mode_includes_fork_only_systems(client, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    body = client.get("/api/systems").json()
    by_key = {s["key"]: s for s in body["systems"]}
    assert "ngp" in by_key
    assert by_key["ngp"]["experimental"] is True
    assert by_key["ngp"]["dirname"] == "ngp"
    assert "ngp" in by_key["ngp"]["exts"] or "ngc" in by_key["ngp"]["exts"]


def test_list_systems_entry_shape(client, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    body = client.get("/api/systems").json()
    nes = next(s for s in body["systems"] if s["key"] == "nes")
    assert nes["name"] == "NES"
    assert nes["dirname"] == "nes"
    assert "nes" in nes["exts"]
    assert nes["pico8"] is False


# ── security headers middleware ──────────────────────────────────────────────

def test_cross_origin_isolation_headers_present_on_every_response(client):
    r = client.get("/api/health")
    assert r.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert r.headers["Cross-Origin-Embedder-Policy"] == "credentialless"


def test_no_cache_header_is_not_forced_onto_json_responses(client):
    # The no-cache middleware only targets text/html (the SPA shell) so hashed
    # JSON API responses stay normally cacheable.
    r = client.get("/api/health")
    assert "no-cache" not in r.headers.get("Cache-Control", "")


# ── router mounting ──────────────────────────────────────────────────────────

def test_expected_routers_are_mounted(client):
    openapi_paths = set(client.get("/openapi.json").json()["paths"])
    for expected in (
        "/api/health",
        "/api/config",
        "/api/systems",
        "/api/sessions",
        "/api/sessions/{session_id}/library",
        "/api/sessions/{session_id}/roms",
        "/api/sessions/{session_id}/videos",
        "/api/sessions/{session_id}/music",
        "/api/clock/background",
        "/api/sessions/{session_id}/package",
    ):
        assert expected in openapi_paths, f"missing route: {expected}"


# ── experimental-only routers (videos/clock/music) gate ─────────────────────

def test_experimental_only_router_blocks_when_flag_off(client, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    r = client.post(
        "/api/clock/background",
        files={"file": ("pic.png", b"\x89PNGfake", "image/png")},
    )
    assert r.status_code == 403


def test_experimental_only_router_allows_through_when_flag_on(client, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    r = client.post(
        "/api/clock/background",
        files={"file": ("pic.png", b"\x89PNGfake", "image/png")},
    )
    # Dependency passed; whatever happens next (missing ffmpeg -> 503, bad
    # image -> 422, etc.) is video-encoding territory, not this gate.
    assert r.status_code != 403


def test_non_experimental_router_is_unaffected_by_the_flag(client, monkeypatch):
    # /api/sessions (sessions.router) carries no experimental dependency.
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    r = client.post("/api/sessions", params={"label": "x"})
    assert r.status_code == 200


# ── sessions.py: dependency helpers ─────────────────────────────────────────

def test_require_korean_mode_blocks_when_flag_off(monkeypatch):
    monkeypatch.setattr(config, "KOREAN_MODE", False)
    with pytest.raises(HTTPException) as exc:
        sessions.require_korean_mode()
    assert exc.value.status_code == 403


def test_require_korean_mode_allows_when_flag_on(monkeypatch):
    monkeypatch.setattr(config, "KOREAN_MODE", True)
    sessions.require_korean_mode()  # must not raise


def test_require_experimental_mode_blocks_when_flag_off(monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    with pytest.raises(HTTPException) as exc:
        sessions.require_experimental_mode()
    assert exc.value.status_code == 403


def test_require_experimental_mode_allows_when_flag_on(monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    sessions.require_experimental_mode()  # must not raise


def test_require_system_enabled_blocks_experimental_system_when_flag_off(monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    with pytest.raises(HTTPException) as exc:
        sessions.require_system_enabled(get_system("ngp"))
    assert exc.value.status_code == 403


def test_require_system_enabled_allows_official_system_regardless_of_flag(monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    sessions.require_system_enabled(get_system("nes"))  # must not raise


def test_require_session_raises_404_for_unknown_session(session_id):
    from app import db

    with db.connect() as conn:
        with pytest.raises(HTTPException) as exc:
            sessions.require_session(conn, "does-not-exist")
    assert exc.value.status_code == 404


def test_require_session_passes_for_known_session(session_id):
    from app import db

    with db.connect() as conn:
        sessions.require_session(conn, session_id)  # must not raise


# ── sessions.py: endpoints ───────────────────────────────────────────────────

def test_create_session_returns_new_id_and_persists_it(client):
    r = client.post("/api/sessions", params={"label": "my workspace"})
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "my workspace"
    assert body["session_id"]

    # A second call mints a DIFFERENT id.
    r2 = client.post("/api/sessions", params={"label": "another"})
    assert r2.json()["session_id"] != body["session_id"]


def test_get_library_404s_for_unknown_session(client):
    r = client.get("/api/sessions/no-such-session/library")
    assert r.status_code == 404


def test_get_library_on_shared_session_starts_empty(client, session_id):
    r = client.get(f"/api/sessions/{session_id}/library")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == session_id
    assert body["roms"] == []
    assert body["videos"] == []
    assert body["music"] == []


def test_get_library_returns_a_seeded_rom_enriched_with_display_fields(client, make_rom):
    # make_rom is a raw DB factory (no romtag/langfill parsing), so the region
    # tag is passed explicitly rather than expected to be derived from the name.
    rom = make_rom(system_key="nes", name="Super Game.nes", region="USA")

    r = client.get(f"/api/sessions/{rom['session_id']}/library")
    assert r.status_code == 200
    roms = r.json()["roms"]
    assert len(roms) == 1
    fetched = roms[0]
    assert fetched["id"] == rom["id"]
    # No korean_name set -> display_name falls back to the cleaned stored name.
    assert fetched["display_name"] == "Super Game"
    assert fetched["display_region"] == "USA"
    assert "cover_ver" in fetched and fetched["cover_ver"]


def test_get_library_prefers_korean_name_for_display_name(client, make_rom):
    rom = make_rom(system_key="nes", name="Game.nes", korean_name="게임")
    r = client.get(f"/api/sessions/{rom['session_id']}/library")
    fetched = r.json()["roms"][0]
    assert fetched["display_name"] == "게임"


def test_get_library_korean_patched_rom_displays_region_korea(client, make_rom):
    rom = make_rom(system_key="nes", name="Game.nes", is_korean_patched=1, region="Japan")
    r = client.get(f"/api/sessions/{rom['session_id']}/library")
    fetched = r.json()["roms"][0]
    assert fetched["display_region"] == "Korea"
