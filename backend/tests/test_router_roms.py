# -*- coding: utf-8 -*-
"""routers/roms.py, routers/scores.py, routers/lang.py.

Pins:
  - upload_roms: per-file ok/error results (bad extension, too large, exact-
    content duplicate), Korean-patch/region/cover-flag derivation from the
    filename, the Genesis header-size sanity warning, and the PICO-8-only
    inline cover (everything else defers to the background autofill).
  - upload_cd_folder / add_cd_tracks: folder-per-game CD uploads (.cue/.chd
    primary + track sidecars keep their EXACT names), size caps, and the
    numbered-folder clash rule.
  - replace_rom_file / add_rom_file / delete_rom_file: swapping the rom
    binary and managing homebrew "extra" sidecar files (assets .dat etc.),
    trash-based removal.
  - scores.backfill_scores: IGDB rating backfill (mocked at the igdb service
    boundary), only-missing vs refresh, system/limit scoping.
  - lang.set_lang: manual user-patch override, 'manual' lang_source pinning,
    and that a no-op toggle does not spam the activity feed.

All network is mocked at the service boundary (covers_pico8 rendering,
igdb.fetch_rating) — the autouse `no_network` fixture would otherwise raise on
any real outbound call. No sleeps: `scores._RATE_PAUSE` and the roms-router
`asyncio.sleep` pacing are patched away.
"""
from __future__ import annotations

import json
import struct

import pytest

from app import config, db
from app.routers import lang as lang_router
from app.routers import roms as roms_router
from app.routers import scores as scores_router
from app.services import covers, covers_pico8


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _upload(client, session_id, system, files):
    """files: list of (filename, bytes) tuples, all under the 'files' field."""
    return client.post(
        f"/api/sessions/{session_id}/roms",
        data={"system": system},
        files=[("files", (name, data, "application/octet-stream")) for name, data in files],
    )


def _fetch_rom(rom_id):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM roms WHERE id = ?", (rom_id,)).fetchone()
        return dict(row) if row else None


def _events_for(session_id, rom_id, event_type):
    with db.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM events WHERE session_id = ? AND rom_id = ? AND event_type = ?",
                (session_id, rom_id, event_type),
            ).fetchall()
        ]


def _md_header(total_len: int, declared_len: int) -> bytes:
    """Genesis header with the ROM-end-address field set so declared_size ==
    declared_len (see romcheck.md_header_warning: declared = value + 1)."""
    data = bytearray(total_len)
    struct.pack_into(">I", data, 0x1A4, declared_len - 1)
    return bytes(data)


async def _instant(*_a, **_kw) -> None:
    return None


# ===========================================================================
# upload_roms — POST /sessions/{session_id}/roms
# ===========================================================================

def test_upload_unknown_system_returns_400(client, session_id):
    r = _upload(client, session_id, "not-a-system", [("Game.nes", b"x")])
    assert r.status_code == 400


def test_upload_experimental_system_blocked_when_flag_off(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    r = _upload(client, session_id, "ngp", [("Game.ngp", b"x")])
    assert r.status_code == 403


def test_upload_unknown_session_returns_404(client):
    r = _upload(client, "no-such-session", "nes", [("Game.nes", b"x")])
    assert r.status_code == 404


def test_upload_rejects_extension_not_accepted(client, session_id):
    r = _upload(client, session_id, "nes", [("Game.zzz", b"content")])
    assert r.status_code == 200
    body = r.json()
    assert body["stored"] == 0
    assert body["results"][0] == {"name": "Game.zzz", "ok": False, "error": "extension not accepted"}


def test_upload_rejects_oversized_file(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "MAX_ROM_BYTES", 10)
    r = _upload(client, session_id, "nes", [("Game.nes", b"x" * 20)])
    body = r.json()
    assert body["results"][0]["ok"] is False
    assert body["results"][0]["error"] == "too large"


def test_upload_exact_duplicate_content_is_skipped(client, session_id):
    data = b"identical-bytes"
    r1 = _upload(client, session_id, "nes", [("First.nes", data)])
    assert r1.json()["results"][0]["ok"] is True
    stored_name = r1.json()["results"][0]["stored_name"]

    r2 = _upload(client, session_id, "nes", [("Second.nes", data)])
    result = r2.json()["results"][0]
    assert result["ok"] is False
    assert result["error"] == "duplicate"
    assert result["duplicate_of"] == stored_name

    # only ONE row was ever inserted for this content.
    with db.connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) c FROM roms WHERE session_id = ?", (session_id,)
        ).fetchone()["c"]
    assert n == 1


def test_upload_strips_region_tag_from_stored_name_but_keeps_it_in_its_own_column(client, session_id):
    r = _upload(client, session_id, "nes", [("Game (USA).nes", b"payload")])
    result = r.json()["results"][0]
    assert result["ok"] is True
    assert result["stored_name"] == "Game.nes"          # region tag removed from the filename
    rom = _fetch_rom(result["id"])
    assert rom["region"] == "USA"                       # ...but preserved in its own column
    assert rom["original_name"] == "Game (USA)"


def test_upload_non_pico8_rom_defers_cover_to_background_autofill(client, session_id):
    # The response itself must say 'pending' synchronously — whatever the
    # background autofill (asyncio.create_task, exercised directly further
    # down) eventually settles it to is that task's own concern, not this
    # request's.
    r = _upload(client, session_id, "nes", [("Game.nes", b"payload")])
    result = r.json()["results"][0]
    assert result["cover_status"] == "pending"


def test_upload_korean_patch_filename_sets_flags_in_korean_mode(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "KOREAN_MODE", True)
    name = "Game (Korea-patch J-K v20200101 v1.0).nes"
    r = _upload(client, session_id, "nes", [(name, b"payload")])
    result = r.json()["results"][0]
    rom = _fetch_rom(result["id"])
    assert rom["is_korean_patched"] == 1
    assert rom["orig_lang"] == "ja"
    assert rom["play_lang"] == "ko"
    assert rom["cover_flag"] == "ko"
    assert "ko" in covers.FLAG_CODES  # sanity: the flag we asserted is a real one


def test_upload_korean_patch_flag_cleared_when_korean_mode_off(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "KOREAN_MODE", False)
    name = "Game (Korea-patch J-K v20200101 v1.0).nes"
    r = _upload(client, session_id, "nes", [(name, b"payload")])
    rom = _fetch_rom(r.json()["results"][0]["id"])
    assert rom["is_korean_patched"] == 0          # gated off outside Korean mode
    assert rom["cover_flag"] is None              # 'ko' explicitly scrubbed, not just unset


def test_upload_md_header_size_mismatch_produces_warning(client, session_id):
    bad = _md_header(total_len=500, declared_len=100)  # header says 100, file is 500
    r = _upload(client, session_id, "md", [("Sonic.bin", bad)])
    result = r.json()["results"][0]
    assert result["ok"] is True
    assert result["warning"] is not None


def test_upload_md_header_matching_size_has_no_warning(client, session_id):
    good = _md_header(total_len=500, declared_len=500)
    r = _upload(client, session_id, "md", [("Sonic.bin", good)])
    assert r.json()["results"][0]["warning"] is None


def test_upload_pico8_renders_cover_and_preview_inline(client, session_id, monkeypatch):
    monkeypatch.setattr(covers_pico8, "render_pico8_cover", lambda path: b"\xff\xd8fake-jpeg")
    monkeypatch.setattr(covers_pico8, "render_pico8_preview", lambda path: b"fake-webp")

    r = _upload(client, session_id, "pico8", [("Cart.p8", b"pico8 source")])
    result = r.json()["results"][0]
    assert result["ok"] is True
    assert result["cover_status"] == "ok"

    rom = _fetch_rom(result["id"])
    assert rom["cover_status"] == "ok"
    assert rom["cover_path"] is not None
    from app.services import storage
    cover_abs = storage.session_root(session_id) / rom["cover_path"]
    assert cover_abs.read_bytes() == b"\xff\xd8fake-jpeg"
    preview_abs = storage.previews_dir(session_id, "pico8") / "Cart.webp"
    assert preview_abs.read_bytes() == b"fake-webp"


def test_upload_pico8_preview_render_error_still_keeps_the_cover(client, session_id, monkeypatch):
    # The cover and the preview are rendered/saved independently — a broken
    # preview render must not roll back an already-successful cover.
    monkeypatch.setattr(covers_pico8, "render_pico8_cover", lambda path: b"\xff\xd8fake-jpeg")
    def _boom_preview(path):
        raise covers.CoverError("bad preview")
    monkeypatch.setattr(covers_pico8, "render_pico8_preview", _boom_preview)

    r = _upload(client, session_id, "pico8", [("Cart.p8", b"pico8 source")])
    result = r.json()["results"][0]
    assert result["cover_status"] == "ok"
    rom = _fetch_rom(result["id"])
    assert rom["cover_path"] is not None
    from app.services import storage
    assert not (storage.previews_dir(session_id, "pico8") / "Cart.webp").exists()


def test_upload_pico8_cover_error_leaves_status_none_not_pending(client, session_id, monkeypatch):
    def _boom(path):
        raise covers.CoverError("no label")
    monkeypatch.setattr(covers_pico8, "render_pico8_cover", _boom)

    r = _upload(client, session_id, "pico8", [("Cart.p8", b"pico8 source")])
    result = r.json()["results"][0]
    # Pico-8 never goes through the 'pending' background-autofill path.
    assert result["cover_status"] == "none"


def test_upload_multiple_files_mixed_ok_and_rejected(client, session_id):
    r = _upload(client, session_id, "nes", [
        ("Good.nes", b"good-bytes"),
        ("Bad.zzz", b"bad-ext"),
    ])
    body = r.json()
    assert body["stored"] == 1
    oks = {res["name"]: res["ok"] for res in body["results"]}
    assert oks == {"Good.nes": True, "Bad.zzz": False}


# ---------------------------------------------------------------------------
# _autofill_covers / _settle_cover — background helpers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_autofill_covers_settles_to_none_when_every_attempt_misses(
    session_id, make_rom, monkeypatch
):
    rom = make_rom(system_key="nes", name="Game.nes", cover_status="pending")
    monkeypatch.setattr(roms_router.asyncio, "sleep", _instant)

    async def _never_finds(_session_id, _rom):
        return False
    monkeypatch.setattr("app.routers.covers.autofill_rom", _never_finds)

    await roms_router._autofill_covers(session_id, [{
        "id": rom["id"], "system_key": "nes", "stored_name": "Game.nes",
        "original_name": "Game.nes", "korean_name": None,
        "rom_path": rom["rom_path"], "cover_flag": None,
    }])

    assert _fetch_rom(rom["id"])["cover_status"] == "none"


@pytest.mark.asyncio
async def test_autofill_covers_stops_retrying_once_a_cover_is_found(
    session_id, make_rom, monkeypatch
):
    rom = make_rom(system_key="nes", name="Game.nes", cover_status="pending")
    monkeypatch.setattr(roms_router.asyncio, "sleep", _instant)

    calls = []
    async def _finds_on_first_try(_session_id, _rom):
        calls.append(1)
        return True
    monkeypatch.setattr("app.routers.covers.autofill_rom", _finds_on_first_try)

    await roms_router._autofill_covers(session_id, [{
        "id": rom["id"], "system_key": "nes", "stored_name": "Game.nes",
        "original_name": "Game.nes", "korean_name": None,
        "rom_path": rom["rom_path"], "cover_flag": None,
    }])

    assert len(calls) == 1  # no retry pass needed
    # cover_status is left untouched here (autofill_rom itself would have set 'ok';
    # our fake didn't, so it stays whatever make_rom seeded — 'pending').
    assert _fetch_rom(rom["id"])["cover_status"] == "pending"


@pytest.mark.asyncio
async def test_autofill_covers_swallows_exceptions_and_still_settles(
    session_id, make_rom, monkeypatch
):
    rom = make_rom(system_key="nes", name="Game.nes", cover_status="pending")
    monkeypatch.setattr(roms_router.asyncio, "sleep", _instant)

    async def _raises(_session_id, _rom):
        raise RuntimeError("provider exploded")
    monkeypatch.setattr("app.routers.covers.autofill_rom", _raises)

    await roms_router._autofill_covers(session_id, [{
        "id": rom["id"], "system_key": "nes", "stored_name": "Game.nes",
        "original_name": "Game.nes", "korean_name": None,
        "rom_path": rom["rom_path"], "cover_flag": None,
    }])

    assert _fetch_rom(rom["id"])["cover_status"] == "none"


def test_settle_cover_only_clears_a_still_pending_rom(session_id, make_rom):
    pending = make_rom(system_key="nes", name="Pending.nes", cover_status="pending")
    already_ok = make_rom(system_key="nes", name="Ok.nes", cover_status="ok")

    roms_router._settle_cover(pending["id"])
    roms_router._settle_cover(already_ok["id"])

    assert _fetch_rom(pending["id"])["cover_status"] == "none"
    assert _fetch_rom(already_ok["id"])["cover_status"] == "ok"  # untouched






# ===========================================================================
# upload_cd_folder — POST /sessions/{session_id}/roms/cdfolder
# ===========================================================================

def _upload_cdfolder(client, session_id, system, rel_paths, files):
    return client.post(
        f"/api/sessions/{session_id}/roms/cdfolder",
        data={"system": system, "paths": json.dumps(rel_paths)},
        files=[("files", (name, data, "application/octet-stream")) for name, data in files],
    )


def test_cdfolder_unknown_system_returns_400(client, session_id):
    r = _upload_cdfolder(client, session_id, "not-a-system", ["G/G.cue"], [("G.cue", b"x")])
    assert r.status_code == 400


def test_cdfolder_invalid_paths_json_returns_400(client, session_id):
    r = client.post(
        f"/api/sessions/{session_id}/roms/cdfolder",
        data={"system": "pcecd", "paths": "not-json"},
        files=[("files", ("G.cue", b"x", "application/octet-stream"))],
    )
    assert r.status_code == 400


def test_cdfolder_paths_files_length_mismatch_returns_400(client, session_id):
    r = _upload_cdfolder(
        client, session_id, "pcecd", ["G/G.cue", "G/track01.bin"], [("G.cue", b"x")]
    )
    assert r.status_code == 400


def test_cdfolder_missing_cue_and_chd_returns_400(client, session_id):
    r = _upload_cdfolder(client, session_id, "pcecd", ["G/data.bin"], [("data.bin", b"x")])
    assert r.status_code == 400


def test_cdfolder_no_files_returns_400(client, session_id):
    r = client.post(
        f"/api/sessions/{session_id}/roms/cdfolder",
        data={"system": "pcecd", "paths": "[]"},
    )
    # FastAPI's own validation (files is required) also lands on a 4xx here;
    # either way the folder-with-nothing-in-it case must not succeed.
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_cdfolder_empty_file_list_hits_the_no_files_guard_directly(session_id):
    # An empty `files` list can't be produced through a real multipart HTTP
    # request (FastAPI's own File(...) validation rejects it first), so this
    # branch is exercised by calling the handler directly.
    with pytest.raises(Exception) as exc:
        await roms_router.upload_cd_folder(session_id, system="pcecd", paths="[]", files=[])
    assert getattr(exc.value, "status_code", None) == 400


def test_cdfolder_stores_cue_plus_track_as_one_rom_with_extra_files(client, session_id):
    r = _upload_cdfolder(
        client, session_id, "pcecd",
        ["MyGame/MyGame.cue", "MyGame/track01.bin"],
        [("MyGame.cue", b"cue-bytes"), ("track01.bin", b"track-bytes")],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["stored"] == 1
    result = body["results"][0]
    assert result["ok"] is True
    assert result["tracks"] == 1

    rom = _fetch_rom(result["id"])
    assert rom["rom_path"] == "roms/pcecd/MyGame/MyGame.cue"
    extra = json.loads(rom["extra_files"])
    assert extra == [{"name": "track01.bin", "size": len(b"track-bytes")}]

    from app.services import storage
    root = storage.session_root(session_id)
    assert (root / "roms/pcecd/MyGame/MyGame.cue").read_bytes() == b"cue-bytes"
    assert (root / "roms/pcecd/MyGame/track01.bin").read_bytes() == b"track-bytes"


def test_cdfolder_selects_chd_as_primary_when_no_cue_present(client, session_id):
    r = _upload_cdfolder(
        client, session_id, "pcecd", ["GameB/GameB.chd"], [("GameB.chd", b"chd-bytes")]
    )
    assert r.status_code == 200
    result = r.json()["results"][0]
    assert result["ok"] is True
    rom = _fetch_rom(result["id"])
    assert rom["rom_path"].endswith("GameB.chd")


def test_cdfolder_exact_duplicate_of_primary_content_is_rejected(client, session_id):
    r1 = _upload_cdfolder(
        client, session_id, "pcecd", ["GameC/GameC.cue"], [("GameC.cue", b"same-primary-bytes")]
    )
    assert r1.json()["results"][0]["ok"] is True

    r2 = _upload_cdfolder(
        client, session_id, "pcecd", ["GameC2/GameC2.cue"], [("GameC2.cue", b"same-primary-bytes")]
    )
    body2 = r2.json()
    assert body2["stored"] == 0
    assert body2["results"][0]["error"] == "duplicate"


def test_cdfolder_reuploading_same_game_name_gets_a_numbered_folder(client, session_id):
    r1 = _upload_cdfolder(
        client, session_id, "pcecd", ["GameD/GameD.cue"], [("GameD.cue", b"content-one")]
    )
    assert r1.json()["results"][0]["ok"] is True

    r2 = _upload_cdfolder(
        client, session_id, "pcecd", ["GameD/GameD.cue"], [("GameD.cue", b"content-two-different")]
    )
    body2 = r2.json()
    assert body2["results"][0]["ok"] is True
    rom2 = _fetch_rom(body2["results"][0]["id"])
    assert rom2["rom_path"] == "roms/pcecd/GameD (2)/GameD.cue"


def test_cdfolder_rejects_a_track_with_an_unsafe_filename(client, session_id):
    # rel_paths[1] is empty, so the code falls back to the raw upload filename,
    # which still carries a path separator -> rejected mid-write (and the
    # staging directory is cleaned up, never left as a partial folder).
    r = _upload_cdfolder(
        client, session_id, "pcecd",
        ["GameE/GameE.cue", ""],
        [("GameE.cue", b"cue-bytes"), ("evil/name.bin", b"x")],
    )
    assert r.status_code == 400
    from app.services import storage
    incoming = list(storage.roms_dir(session_id, "pcecd").glob(".incoming-*"))
    assert incoming == []  # staging dir was cleaned up, not left behind


def test_cdfolder_rejects_file_over_the_per_file_cap(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "MAX_CD_FILE_BYTES", 5)
    r = _upload_cdfolder(
        client, session_id, "pcecd", ["GameF/GameF.cue"], [("GameF.cue", b"this-is-too-long")]
    )
    assert r.status_code == 413


def test_cdfolder_rejects_folder_over_the_total_cap(client, session_id, monkeypatch):
    monkeypatch.setattr(config, "MAX_CD_FILE_BYTES", 100)   # generous per-file
    monkeypatch.setattr(config, "MAX_CD_TOTAL_BYTES", 10)   # tight total
    r = _upload_cdfolder(
        client, session_id, "pcecd",
        ["GameG/GameG.cue", "GameG/track01.bin"],
        [("GameG.cue", b"123456"), ("track01.bin", b"123456")],
    )
    assert r.status_code == 413


# ===========================================================================
# add_cd_tracks — POST /sessions/{session_id}/roms/{rom_id}/cdtracks
# ===========================================================================

def test_add_cd_tracks_unknown_session_returns_404(client):
    r = client.post(
        "/api/sessions/no-such-session/roms/x/cdtracks",
        files=[("files", ("t.bin", b"x", "application/octet-stream"))],
    )
    assert r.status_code == 404


def test_add_cd_tracks_unknown_rom_returns_404(client, session_id):
    r = client.post(
        f"/api/sessions/{session_id}/roms/no-such-rom/cdtracks",
        files=[("files", ("t.bin", b"x", "application/octet-stream"))],
    )
    assert r.status_code == 404


def test_add_cd_tracks_appends_a_new_track_next_to_the_primary_file(client, session_id, make_rom):
    rom = make_rom(system_key="pcecd", name="Game.cue")
    r = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cdtracks",
        files=[("files", ("track01.bin", b"track-bytes", "application/octet-stream"))],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == ["track01.bin"]
    assert body["tracks"] == 1

    updated = _fetch_rom(rom["id"])
    assert json.loads(updated["extra_files"]) == [{"name": "track01.bin", "size": 11}]
    from app.services import storage
    added_file = storage.session_root(session_id) / "roms/pcecd/track01.bin"
    assert added_file.read_bytes() == b"track-bytes"


def test_add_cd_tracks_never_clobbers_the_primary_file(client, session_id, make_rom):
    rom = make_rom(system_key="pcecd", name="Game.cue", content=b"original-cue")
    r = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cdtracks",
        files=[("files", ("Game.cue", b"malicious-overwrite", "application/octet-stream"))],
    )
    assert r.status_code == 200
    assert r.json()["added"] == []  # silently skipped, not added as a track
    from app.services import storage
    primary = storage.session_root(session_id) / rom["rom_path"]
    assert primary.read_bytes() == b"original-cue"


def test_add_cd_tracks_rejects_unsafe_track_name(client, session_id, make_rom):
    rom = make_rom(system_key="pcecd", name="Game.cue")
    r = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cdtracks",
        files=[("files", (".", b"x", "application/octet-stream"))],
    )
    assert r.status_code == 400


def test_add_cd_tracks_rejects_oversized_track_and_cleans_up_partial_file(
    client, session_id, make_rom, monkeypatch
):
    monkeypatch.setattr(config, "MAX_CD_FILE_BYTES", 5)
    rom = make_rom(system_key="pcecd", name="Game.cue")
    r = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cdtracks",
        files=[("files", ("track01.bin", b"way-too-big", "application/octet-stream"))],
    )
    assert r.status_code == 413
    from app.services import storage
    assert not (storage.session_root(session_id) / "roms/pcecd/track01.bin").exists()


def test_add_cd_tracks_replaces_rather_than_duplicates_same_name(client, session_id, make_rom):
    rom = make_rom(system_key="pcecd", name="Game.cue")
    client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cdtracks",
        files=[("files", ("track01.bin", b"first", "application/octet-stream"))],
    )
    r2 = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/cdtracks",
        files=[("files", ("track01.bin", b"second-longer", "application/octet-stream"))],
    )
    extra = json.loads(_fetch_rom(rom["id"])["extra_files"])
    assert extra == [{"name": "track01.bin", "size": len(b"second-longer")}]  # replaced, not duplicated


# ===========================================================================
# replace_rom_file — POST /sessions/{session_id}/roms/{rom_id}/replace
# ===========================================================================

def test_replace_rom_unknown_rom_returns_404(client, session_id):
    r = client.post(
        f"/api/sessions/{session_id}/roms/no-such-rom/replace",
        files={"file": ("Game.nes", b"new-bytes", "application/octet-stream")},
    )
    assert r.status_code == 404


def test_replace_rom_rejects_extension_invalid_for_the_system(client, session_id, make_rom):
    rom = make_rom(system_key="nes", name="Game.nes")
    r = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/replace",
        files={"file": ("Game.zzz", b"new-bytes", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_replace_rom_rejects_empty_file(client, session_id, make_rom):
    rom = make_rom(system_key="nes", name="Game.nes")
    r = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/replace",
        files={"file": ("Game.nes", b"", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_replace_rom_rejects_oversized_file(client, session_id, make_rom, monkeypatch):
    monkeypatch.setattr(config, "MAX_ROM_BYTES", 5)
    rom = make_rom(system_key="nes", name="Game.nes")
    r = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/replace",
        files={"file": ("Game.nes", b"way-too-big", "application/octet-stream")},
    )
    assert r.status_code == 413


def test_replace_rom_swaps_bytes_keeps_name_and_trashes_the_old_file(client, session_id, make_rom):
    rom = make_rom(system_key="nes", name="Game.nes", content=b"old-bytes")
    r = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/replace",
        files={"file": ("Whatever.nes", b"new-bytes", "application/octet-stream")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["stored_name"] == "Game.nes"       # slot/name unchanged
    assert body["size_bytes"] == len(b"new-bytes")

    from app.services import storage
    abs_path = storage.session_root(session_id) / rom["rom_path"]
    assert abs_path.read_bytes() == b"new-bytes"

    # the OLD content is recoverable, not destroyed.
    trashed = list(storage.trash_dir(session_id).iterdir())
    assert any(p.read_bytes() == b"old-bytes" for p in trashed)

    # the new content's hash was remembered for future auto-name resolution.
    from app.services import name_index
    with db.connect() as conn:
        assert name_index.lookup(conn, name_index.hash_bytes(b"new-bytes")) == "Game"


# ===========================================================================
# add_rom_file / delete_rom_file — homebrew "extra" sidecar files
# ===========================================================================

def test_add_rom_file_unknown_rom_returns_404(client, session_id):
    r = client.post(
        f"/api/sessions/{session_id}/roms/no-such-rom/files",
        files={"file": ("assets.dat", b"data", "application/octet-stream")},
    )
    assert r.status_code == 404


def test_add_rom_file_rejects_empty_file(client, session_id, make_rom):
    rom = make_rom(system_key="homebrew", name="MyApp.bin")
    r = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/files",
        files={"file": ("assets.dat", b"", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_add_rom_file_rejects_oversized_file(client, session_id, make_rom, monkeypatch):
    monkeypatch.setattr(config, "MAX_ROM_BYTES", 5)
    rom = make_rom(system_key="homebrew", name="MyApp.bin")
    r = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/files",
        files={"file": ("assets.dat", b"way-too-big", "application/octet-stream")},
    )
    assert r.status_code == 413


def test_add_rom_file_rejects_name_matching_the_template_file(client, session_id, make_rom):
    rom = make_rom(system_key="homebrew", name="MyApp.bin")
    r = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/files",
        files={"file": ("MyApp.bin", b"data", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_add_rom_file_stores_extra_file_alongside_the_template(client, session_id, make_rom):
    rom = make_rom(system_key="homebrew", name="MyApp.bin")
    r = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/files",
        files={"file": ("myapp_assets.dat", b"asset-bytes", "application/octet-stream")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["extra_files"] == [{"name": "myapp_assets.dat", "size": len(b"asset-bytes")}]

    from app.services import storage
    stored = storage.session_root(session_id) / "roms/homebrew/myapp_assets.dat"
    assert stored.read_bytes() == b"asset-bytes"
    assert json.loads(_fetch_rom(rom["id"])["extra_files"]) == body["extra_files"]


def test_add_rom_file_replaces_rather_than_duplicates_same_name(client, session_id, make_rom):
    rom = make_rom(system_key="homebrew", name="MyApp.bin")
    client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/files",
        files={"file": ("assets.dat", b"v1", "application/octet-stream")},
    )
    r2 = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/files",
        files={"file": ("assets.dat", b"v2-longer", "application/octet-stream")},
    )
    assert r2.json()["extra_files"] == [{"name": "assets.dat", "size": len(b"v2-longer")}]


def test_add_rom_file_tolerates_a_corrupted_extra_files_column(client, session_id, make_rom):
    # _extra_list falls back to [] on malformed JSON rather than 500ing.
    rom = make_rom(system_key="homebrew", name="MyApp.bin", extra_files="not-valid-json")
    r = client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/files",
        files={"file": ("assets.dat", b"data", "application/octet-stream")},
    )
    assert r.status_code == 200
    assert r.json()["extra_files"] == [{"name": "assets.dat", "size": 4}]


def test_delete_rom_file_unknown_rom_returns_404(client, session_id):
    r = client.delete(f"/api/sessions/{session_id}/roms/no-such-rom/files/assets.dat")
    assert r.status_code == 404


def test_delete_rom_file_removes_entry_and_trashes_the_file(client, session_id, make_rom):
    rom = make_rom(system_key="homebrew", name="MyApp.bin")
    client.post(
        f"/api/sessions/{session_id}/roms/{rom['id']}/files",
        files={"file": ("assets.dat", b"asset-bytes", "application/octet-stream")},
    )

    r = client.delete(f"/api/sessions/{session_id}/roms/{rom['id']}/files/assets.dat")
    assert r.status_code == 200
    assert r.json()["extra_files"] == []

    from app.services import storage
    assert not (storage.session_root(session_id) / "roms/homebrew/assets.dat").exists()
    trashed = list(storage.trash_dir(session_id).iterdir())
    assert any(p.read_bytes() == b"asset-bytes" for p in trashed)
    assert json.loads(_fetch_rom(rom["id"])["extra_files"]) == []


def test_delete_rom_file_never_raises_for_a_name_not_in_extra_files(client, session_id, make_rom):
    rom = make_rom(system_key="homebrew", name="MyApp.bin")
    r = client.delete(f"/api/sessions/{session_id}/roms/{rom['id']}/files/never-added.dat")
    assert r.status_code == 200
    assert r.json()["extra_files"] == []


# ===========================================================================
# scores.py — POST /sessions/{session_id}/scores/backfill
# ===========================================================================

@pytest.fixture(autouse=True)
def _no_rate_pause(monkeypatch):
    """Deterministic, instant backfill loop — no real ~0.26s pacing per rom."""
    monkeypatch.setattr(scores_router, "_RATE_PAUSE", 0)
    monkeypatch.setattr(scores_router.asyncio, "sleep", _instant)


def test_backfill_unknown_session_returns_404(client):
    r = client.post("/api/sessions/no-such-session/scores/backfill")
    assert r.status_code == 404


def test_backfill_with_no_roms_is_a_noop(client, session_id):
    r = client.post(f"/api/sessions/{session_id}/scores/backfill")
    assert r.status_code == 200
    assert r.json() == {"processed": 0, "rated": 0, "remaining": 0}


def test_backfill_stores_score_and_votes_on_a_hit(client, session_id, make_rom, monkeypatch):
    rom = make_rom(system_key="nes", name="Sonic (Star Fox).nes")

    async def _fake_rating(title, system_key):
        assert title == "Star Fox"           # parenthetical English title extracted
        return {"score": 91, "votes": 500, "name": "Star Fox", "confidence": 1.0}
    monkeypatch.setattr(scores_router.igdb, "fetch_rating", _fake_rating)

    r = client.post(f"/api/sessions/{session_id}/scores/backfill")
    assert r.json() == {"processed": 1, "rated": 1, "remaining": 0}
    updated = _fetch_rom(rom["id"])
    assert updated["igdb_score"] == 91
    assert updated["igdb_votes"] == 500


def test_backfill_marks_unscoreable_rom_with_sentinel_minus_one(client, session_id, make_rom, monkeypatch):
    rom = make_rom(system_key="nes", name="Obscure Homebrew.nes")
    monkeypatch.setattr(scores_router.igdb, "fetch_rating", lambda *a, **kw: _none())
    r = client.post(f"/api/sessions/{session_id}/scores/backfill")
    assert r.json() == {"processed": 1, "rated": 0, "remaining": 0}
    updated = _fetch_rom(rom["id"])
    assert updated["igdb_score"] == -1
    assert updated["igdb_votes"] == 0


async def _none():
    return None


def test_backfill_exception_from_provider_is_treated_as_no_match(client, session_id, make_rom, monkeypatch):
    make_rom(system_key="nes", name="Game.nes")

    async def _boom(*_a, **_kw):
        raise RuntimeError("igdb is down")
    monkeypatch.setattr(scores_router.igdb, "fetch_rating", _boom)

    r = client.post(f"/api/sessions/{session_id}/scores/backfill")
    assert r.json()["processed"] == 1
    assert r.json()["rated"] == 0


def test_backfill_only_missing_by_default_skips_already_scored_roms(client, session_id, make_rom, monkeypatch):
    already = make_rom(system_key="nes", name="Already.nes", igdb_score=50, igdb_votes=10)
    missing = make_rom(system_key="nes", name="Missing.nes")

    calls = []
    async def _fake_rating(title, system_key):
        calls.append(title)
        return {"score": 77, "votes": 1, "name": title, "confidence": 1.0}
    monkeypatch.setattr(scores_router.igdb, "fetch_rating", _fake_rating)

    r = client.post(f"/api/sessions/{session_id}/scores/backfill")
    assert r.json()["processed"] == 1
    assert calls == ["Missing"]
    assert _fetch_rom(already["id"])["igdb_score"] == 50  # untouched


def test_backfill_refresh_true_rescopes_everything_including_already_scored(client, session_id, make_rom, monkeypatch):
    already = make_rom(system_key="nes", name="Already.nes", igdb_score=50, igdb_votes=10)

    async def _fake_rating(title, system_key):
        return {"score": 99, "votes": 2, "name": title, "confidence": 1.0}
    monkeypatch.setattr(scores_router.igdb, "fetch_rating", _fake_rating)

    r = client.post(f"/api/sessions/{session_id}/scores/backfill", params={"refresh": True})
    assert r.json()["processed"] == 1
    assert _fetch_rom(already["id"])["igdb_score"] == 99


def test_backfill_scopes_to_a_single_system(client, session_id, make_rom, monkeypatch):
    make_rom(system_key="nes", name="A.nes")
    make_rom(system_key="gb", name="B.gb")

    async def _fake_rating(title, system_key):
        return {"score": 60, "votes": 1, "name": title, "confidence": 1.0}
    monkeypatch.setattr(scores_router.igdb, "fetch_rating", _fake_rating)

    r = client.post(f"/api/sessions/{session_id}/scores/backfill", params={"system": "nes"})
    assert r.json()["processed"] == 1


def test_backfill_limit_caps_processed_count_and_reports_remaining(client, session_id, make_rom, monkeypatch):
    for i in range(3):
        make_rom(system_key="nes", name=f"Game{i}.nes")

    async def _fake_rating(title, system_key):
        return {"score": 60, "votes": 1, "name": title, "confidence": 1.0}
    monkeypatch.setattr(scores_router.igdb, "fetch_rating", _fake_rating)

    r = client.post(f"/api/sessions/{session_id}/scores/backfill", params={"limit": 2})
    body = r.json()
    assert body["processed"] == 2
    assert body["remaining"] == 1


def test_english_title_falls_back_to_bare_stem_without_parens():
    assert scores_router._english_title("Game.nes") == "Game"


def test_english_title_extracts_the_parenthetical_english_name():
    assert scores_router._english_title("한글 이름 (English Title).nes") == "English Title"


# ===========================================================================
# lang.py — PATCH /sessions/{session_id}/roms/{rom_id}/lang
# ===========================================================================

def _set_lang(client, session_id, rom_id, patched):
    return client.patch(
        f"/api/sessions/{session_id}/roms/{rom_id}/lang",
        json={"is_korean_patched": patched},
    )


def test_set_lang_missing_field_returns_400(client, session_id, make_rom):
    rom = make_rom(system_key="nes", name="Game.nes")
    r = client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/lang", json={})
    assert r.status_code == 400


def test_set_lang_unknown_session_returns_404(client):
    r = _set_lang(client, "no-such-session", "rom-1", True)
    assert r.status_code == 404


def test_set_lang_unknown_rom_returns_404(client, session_id):
    r = _set_lang(client, session_id, "no-such-rom", True)
    assert r.status_code == 404


def test_set_lang_marks_patched_true_sets_play_lang_ko_and_manual_source(client, session_id, make_rom):
    rom = make_rom(system_key="nes", name="Game.nes", orig_lang="ja", play_lang="ja",
                    is_korean_patched=0)
    r = _set_lang(client, session_id, rom["id"], True)
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "rom_id": rom["id"], "orig_lang": "ja", "play_lang": "ko",
        "is_korean_patched": True, "lang_source": "manual",
    }
    updated = _fetch_rom(rom["id"])
    assert updated["is_korean_patched"] == 1
    assert updated["play_lang"] == "ko"
    assert updated["lang_source"] == "manual"


def test_set_lang_unmarking_patched_reverts_play_lang_to_original(client, session_id, make_rom):
    rom = make_rom(system_key="nes", name="Game.nes", orig_lang="ja", play_lang="ko",
                    is_korean_patched=1)
    r = _set_lang(client, session_id, rom["id"], False)
    body = r.json()
    assert body["is_korean_patched"] is False
    assert body["play_lang"] == "ja"                 # falls back to orig_lang


def test_set_lang_logs_an_activity_event_only_when_the_flag_actually_changes(client, session_id, make_rom):
    rom = make_rom(system_key="nes", name="Game.nes", is_korean_patched=0,
                    orig_lang="ja", play_lang="ja")

    # Setting to the SAME value (false -> false) must not log anything.
    _set_lang(client, session_id, rom["id"], False)
    assert _events_for(session_id, rom["id"], "lang_patch") == []

    # Actually flipping it DOES log.
    _set_lang(client, session_id, rom["id"], True)
    events = _events_for(session_id, rom["id"], "lang_patch")
    assert len(events) == 1
