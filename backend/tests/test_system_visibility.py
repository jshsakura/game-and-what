import pytest
from app import db
from app.routers.package import _excluded_roms
from app.services import packaging, storage

@pytest.mark.parametrize("system", ["segacd", "pcecd", "nes", "homebrew"])
def test_hide_removes_whole_set_and_show_preserves_rom_exclusions(client, session_id, make_rom, system, monkeypatch):
    monkeypatch.setattr(packaging.pico8core, "ensure_cores_dir", lambda: None)
    rom = make_rom(system, "Game.bin")
    excluded_rom = make_rom(system, "Excluded.bin", sd_exclude=1)
    root = storage.session_root(session_id)
    folder = root / f"roms/{system}/set"
    folder.mkdir()
    (folder / "game.cue").write_text('FILE "track.bin" BINARY')
    (folder / "track.bin").write_bytes(b"track")
    cover = root / f"covers/{system}/Game.img"
    cover.parent.mkdir(parents=True, exist_ok=True)
    cover.write_bytes(b"cover")
    def entries():
        with db.connect() as conn:
            excluded = _excluded_roms(conn, session_id)
        return {name for _, name in packaging._sd_entries(session_id, False, {system}, None, excluded)}
    before = entries()
    url = f"/api/sessions/{session_id}/systems/{system}/visibility"
    response = client.patch(url, json={"hidden": True})
    assert response.status_code == 200
    assert system in client.get(f"/api/sessions/{session_id}/library").json()["hidden_systems"]
    assert not any(n.startswith((f"roms/{system}/", f"covers/{system}/")) for n in entries())
    assert client.patch(url, json={"hidden": False}).status_code == 200
    assert entries() == before
    with db.connect() as conn:
        assert conn.execute("SELECT sd_exclude FROM roms WHERE id = ?", (excluded_rom["id"],)).fetchone()[0] == 1


def test_visibility_validation(client, session_id):
    prefix = f"/api/sessions/{session_id}/systems"
    assert client.patch(f"{prefix}/nes/visibility", json={"hidden": "false"}).status_code == 422
    assert client.patch(f"{prefix}/unknown/visibility", json={"hidden": True}).status_code == 404
    assert client.patch("/api/sessions/missing/systems/nes/visibility", json={"hidden": True}).status_code == 404


def test_hiding_pico8_omits_bundled_core(client, session_id, data_dir, monkeypatch):
    core_dir = data_dir / "core-fixture"
    core_dir.mkdir()
    (core_dir / "pico8.bin").write_bytes(b"core")
    monkeypatch.setattr(packaging.pico8core, "ensure_cores_dir", lambda: core_dir)
    client.patch(f"/api/sessions/{session_id}/systems/pico8/visibility", json={"hidden": True})
    with db.connect() as conn:
        excluded = _excluded_roms(conn, session_id)
    names = {name for _, name in packaging._sd_entries(session_id, False, None, None, excluded)}
    assert "cores/pico8.bin" not in names


def test_size_condition_measures_cd_tracks(session_id, make_rom):
    from app.routers.package import SdFilter
    import json
    rom = make_rom("segacd", "Game.cue", extra_files=json.dumps([{"name": "track.bin"}]))
    root = storage.session_root(session_id)
    track = (root / rom["rom_path"]).parent / "track.bin"
    track.write_bytes(b"x" * 2000)
    with db.connect() as conn:
        assert rom["rom_path"] in _excluded_roms(conn, session_id, SdFilter(max_bytes=1000))
