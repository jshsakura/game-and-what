import json
from app.services import packaging, storage


def test_compact_library_preserves_list_facts_and_lazy_metadata(client, make_rom, session_id):
    meta = {"summary": "cached facts " * 500, "source": "miyoo-gamelist"}
    rom = make_rom("nes", igdb_meta=json.dumps(meta), sd_exclude=1, favorite=1)
    url = f"/api/sessions/{session_id}/library"
    full = client.get(url).json()["roms"][0]
    compact = client.get(url + "?compact=true").json()["roms"][0]
    assert compact == {k: v for k, v in full.items() if k != "igdb_meta" and v is not None}
    assert compact["sd_exclude"] == 1 and compact["favorite"] == 1
    assert client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/igdb-meta").json() == meta
    client.patch(f"/api/sessions/{session_id}/roms/{rom['id']}/sd-exclude", json={"exclude": False})
    assert client.get(url + "?compact=true").json()["roms"][0]["sd_exclude"] == 0


def test_library_uses_transport_compression(client, make_rom, session_id):
    make_rom(korean_name="long display title " * 200)
    response = client.get(f"/api/sessions/{session_id}/library?compact=true", headers={"Accept-Encoding": "gzip"})
    assert response.headers["Content-Encoding"] == "gzip"
    assert "Accept-Encoding" in response.headers["Vary"]
    assert response.json()["roms"]


def test_package_size_scans_sd_manifest_once(client, make_rom, session_id, monkeypatch):
    monkeypatch.setattr(packaging.pico8core, "ensure_cores_dir", lambda: None)
    rom = make_rom(content=b"12345")
    scan = packaging._sd_entries
    calls = []
    def traced(*args, **kwargs):
        calls.append(True)
        yield from scan(*args, **kwargs)
    monkeypatch.setattr(packaging, "_sd_entries", traced)
    response = client.get(f"/api/sessions/{session_id}/package/size?system=nes")
    assert response.status_code == 200
    assert response.json()["bytes"] == 5
    assert len(calls) == 1


def test_manifest_prunes_excluded_and_private_folders(session_id, monkeypatch):
    monkeypatch.setattr(packaging.pico8core, "ensure_cores_dir", lambda: None)
    root = storage.session_root(session_id)
    for relative in ["roms/segacd/hidden/track.bin", "roms/nes/game.nes", "_previews/nes/game.png"]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"data")
    walk = packaging.os.walk
    visited = []
    def traced(*args, **kwargs):
        for item in walk(*args, **kwargs):
            visited.append(str(item[0]))
            yield item
    monkeypatch.setattr(packaging.os, "walk", traced)
    names = {name for _, name in packaging._sd_entries(session_id, False, None, None, {"roms/segacd/hidden"})}
    assert names == {"roms/nes/game.nes"}
    assert not any(name.endswith("/hidden") or "/_previews" in name for name in visited)


def test_rom_download_retains_original_zip_transport(client, make_rom, session_id):
    import io
    import zipfile
    rom = make_rom(content=b"original ROM bytes" * 1000)
    response = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/download", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert "Content-Encoding" not in response.headers
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert any(archive.read(name) == b"original ROM bytes" * 1000 for name in archive.namelist())


def test_library_start_has_all_counts_but_only_first_platform(client, make_rom, session_id):
    make_rom("nes", "First.nes")
    make_rom("nes", "Excluded.nes", sd_exclude=1)
    make_rom("32x", "Other.32x")
    make_rom("pico8", "Broken.p8", pico8_compat="broken")
    start = client.get(f"/api/sessions/{session_id}/library/start").json()
    assert start["partial"] is True
    assert start["overview"]["total_roms"] == 4
    assert start["overview"]["systems"]["nes"] == {"total":2,"sd":1,"missing":1}
    assert start["overview"]["systems"]["pico8"]["sd"] == 0
    assert {r["system_key"] for r in start["roms"]} == {start["system_key"]}
    assert len(start["roms"]) < start["overview"]["total_roms"]
    all_roms = client.get(f"/api/sessions/{session_id}/library?compact=true").json()["roms"]
    assert len(all_roms) == 4
    nes = client.get(f"/api/sessions/{session_id}/library?compact=true&system=nes").json()["roms"]
    assert len(nes) == 2 and all(r["system_key"] == "nes" for r in nes)


def test_library_start_skips_hidden_default_platform(client, make_rom, session_id):
    make_rom("nes"); make_rom("32x", "Other.32x")
    client.patch(f"/api/sessions/{session_id}/systems/nes/visibility", json={"hidden":True})
    start = client.get(f"/api/sessions/{session_id}/library/start").json()
    assert start["system_key"] == "32x"
    assert start["overview"]["systems"]["nes"]["sd"] == 0
    assert start["overview"]["systems"]["nes"]["total"] == 1


def test_library_start_empty_and_invalid_platform(client, session_id):
    start = client.get(f"/api/sessions/{session_id}/library/start").json()
    assert start["roms"] == [] and start["overview"]["total_roms"] == 0
    assert client.get(f"/api/sessions/{session_id}/library?system=unknown").status_code == 404
    assert client.get("/api/sessions/missing/library/start").status_code == 404
