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
