"""CD uploads must extract raw tracks without changing any disc bytes."""
import json
from pathlib import Path
import shutil
import subprocess
import time
import zipfile

import pytest

from app import config, db
from app.services import cdrom, packaging, storage


@pytest.fixture
def disc(tmp_path):
    tool = shutil.which("chdman")
    if not tool:
        pytest.skip("chdman required for actual CD round trip")
    # Includes a distinct sector zero and security area: compare ALL extracted bytes.
    tracks = [bytes(range(256)) * 147, b"AUDIO" * 7526 + b"ab"]
    assert all(len(t) == 2352 * 16 for t in tracks)
    for i, content in enumerate(tracks, 1):
        (tmp_path / f"input{i}.bin").write_bytes(content)
    cue = tmp_path / "input.cue"
    cue.write_text('FILE "input1.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n'
                   'FILE "input2.bin" BINARY\n  TRACK 02 AUDIO\n    INDEX 01 00:00:00\n')
    chd = tmp_path / "Disc.chd"
    subprocess.run([tool, "createcd", "-i", str(cue), "-o", str(chd)],
                   check=True, capture_output=True)
    return chd.read_bytes(), tracks


def row(rom_id):
    with db.connect() as conn:
        return dict(conn.execute("SELECT * FROM roms WHERE id=?", (rom_id,)).fetchone())


@pytest.mark.parametrize("system", ["pcecd", "segacd"])
@pytest.mark.parametrize("route", ["direct", "folder", "chunked"])
def test_cd_upload_roundtrip(client, session_id, monkeypatch, disc, system, route):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    payload, tracks = disc
    if route == "folder":
        response = client.post(f"/api/sessions/{session_id}/roms/cdfolder",
            data={"system": system, "paths": json.dumps(["Disc/Disc.chd"])},
            files={"files": ("Disc.chd", payload)})
    elif route == "direct":
        response = client.post(f"/api/sessions/{session_id}/roms",
            data={"system": system}, files={"files": ("Disc.chd", payload)})
    else:
        # CDs must not be subject to the cartridge limit.
        monkeypatch.setattr(config, "MAX_ROM_BYTES", 1)
        response = client.post(f"/api/sessions/{session_id}/uploads", json={
            "filename": "Disc.chd", "total_size": len(payload), "kind": "rom", "system": system})
        assert response.status_code == 200
        uid = response.json()["upload_id"]
        response = client.put(f"/api/sessions/{session_id}/uploads/{uid}/chunk?index=0",
            files={"file": ("Disc.chd", payload)})
        assert response.status_code == 200
        response = client.post(f"/api/sessions/{session_id}/uploads/{uid}/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "processing"
        job_id = response.json()["job_id"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in {"done", "failed"}:
                break
            time.sleep(0.01)
        assert job["status"] == "done", job
        rom = row(job["result"]["rom_id"])
        assert client.get(f"/api/sessions/{session_id}/uploads/{uid}").json()["status"] == "complete"
        response = client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200, response.text
    result = (response.json()["result"] if route == "chunked" else response.json())["results"][0]
    assert result["ok"], result
    rom = row(result["id"])
    assert rom["rom_path"] == f"roms/{system}/Disc/Disc.cue"
    extra = json.loads(rom["extra_files"])
    assert [e["name"] for e in extra] == ["Disc (Track 01).bin", "Disc (Track 02).bin"]
    root = storage.session_root(session_id)
    folder = root / Path(rom["rom_path"]).parent
    assert not list(folder.glob("*.chd"))
    for item, content in zip(extra, tracks):
        assert (folder / item["name"]).read_bytes() == content
    # SD archive has one CUE and all tracks; no original CHD or temporary files.
    archive, _ = packaging.build_sd_zip_cached(session_id, systems={system})
    with zipfile.ZipFile(archive) as zf:
        assert set(zf.namelist()) == {rom["rom_path"], *[str(Path(rom["rom_path"]).parent / e["name"]) for e in extra]}


@pytest.mark.parametrize("missing_tool", [False, True])
def test_conversion_failure_leaves_no_game(client, session_id, monkeypatch, missing_tool):
    if missing_tool:
        monkeypatch.setattr(cdrom.shutil, "which", lambda _: None)
    elif not shutil.which("chdman"):
        pytest.skip("chdman required")
    response = client.post(f"/api/sessions/{session_id}/roms/cdfolder",
        data={"system": "pcecd", "paths": '["Broken.chd"]'},
        files={"files": ("Broken.chd", b"invalid CHD")})
    assert response.status_code == (503 if missing_tool else 422)
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM roms").fetchone()[0] == 0
    assert list(storage.roms_dir(session_id, "pcecd").iterdir()) == []


def test_cd_cue_filename_matches_folder(client, session_id):
    response = client.post(f"/api/sessions/{session_id}/roms/cdfolder",
        data={"system": "pcecd", "paths": '["Title/index.cue", "Title/original.bin"]'},
        files=[("files", ("index.cue", b'FILE "original.bin" BINARY\n')),
               ("files", ("original.bin", b"original data"))])
    rom = row(response.json()["results"][0]["id"])
    assert rom["rom_path"] == "roms/pcecd/Title/Title.cue"
    root = storage.session_root(session_id)
    assert (root / rom["rom_path"]).read_bytes() == b'FILE "original.bin" BINARY\n'
    assert (root / "roms/pcecd/Title/original.bin").read_bytes() == b"original data"


def test_chd_clash_and_duplicate_preserve_existing_game(client, session_id, disc):
    payload, tracks = disc
    url = f"/api/sessions/{session_id}/roms/cdfolder"
    first = client.post(url, data={"system": "pcecd", "paths": '["Disc/Disc.cue"]'},
        files={"files": ("Disc.cue", b"original cue")}).json()["results"][0]
    form = {"system": "pcecd", "paths": '["Disc/Disc.chd"]'}
    response = client.post(url, data=form, files={"files": ("Disc.chd", payload)})
    rom = row(response.json()["results"][0]["id"])
    assert rom["rom_path"] == "roms/pcecd/Disc (2)/Disc (2).cue"
    root = storage.session_root(session_id)
    assert (root / row(first["id"])["rom_path"]).read_bytes() == b"original cue"
    extra = json.loads(rom["extra_files"])
    assert extra[0]["name"] == "Disc (2) (Track 01).bin"
    assert (root / Path(rom["rom_path"]).parent / extra[0]["name"]).read_bytes() == tracks[0]
    duplicate = client.post(url, data=form, files={"files": ("Disc.chd", payload)})
    assert duplicate.json()["results"][0]["error"] == "duplicate"
    assert not (root / "roms/pcecd/Disc (3)").exists()
    assert not list((root / "roms/pcecd").glob(".incoming-*"))


def test_background_chd_failure_updates_status_and_cleans_temp(client, session_id, monkeypatch):
    monkeypatch.setattr(cdrom.shutil, "which", lambda _: None)
    init = client.post(f"/api/sessions/{session_id}/uploads", json={
        "filename": "Broken.chd", "total_size": 3, "kind": "rom", "system": "pcecd"})
    uid = init.json()["upload_id"]
    client.put(f"/api/sessions/{session_id}/uploads/{uid}/chunk?index=0", files={"file": ("Broken.chd", b"bad")})
    result = client.post(f"/api/sessions/{session_id}/uploads/{uid}/complete").json()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{result['job_id']}").json()
        if job["status"] == "failed":
            break
        time.sleep(0.01)
    assert job["status"] == "failed"
    assert "chdman not installed" in job["message"]
    assert client.get(f"/api/sessions/{session_id}/uploads/{uid}").json()["status"] == "failed"
    assert not (config.TMP_DIR / f"{uid}.part").exists()
    assert list(storage.roms_dir(session_id, "pcecd").iterdir()) == []


def test_sidecar_management_uses_cd_folder(client, session_id):
    result = client.post(f"/api/sessions/{session_id}/roms/cdfolder",
        data={"system": "pcecd", "paths": '["Game/Game.cue"]'},
        files={"files": ("Game.cue", b"cue")}).json()["results"][0]
    rom_id = result["id"]
    url = f"/api/sessions/{session_id}/roms/{rom_id}/files"
    assert client.post(url, files={"file": ("track.bin", b"raw data")}).status_code == 200
    root = storage.session_root(session_id)
    assert (root / "roms/pcecd/Game/track.bin").read_bytes() == b"raw data"
    assert not (root / "roms/pcecd/track.bin").exists()
    assert client.delete(url + "/track.bin").status_code == 200
    assert not (root / "roms/pcecd/Game/track.bin").exists()


def test_staging_files_never_ship_to_sd(session_id):
    root = storage.session_root(session_id)
    stage = storage.roms_dir(session_id, "pcecd") / ".incoming-test" / "Disc.chd"
    stage.parent.mkdir(parents=True, exist_ok=True)
    stage.write_bytes(b"CHD still converting")
    assert packaging._excluded(root, stage, False)


@pytest.mark.parametrize("system", ["segacd", "pcecd"])
@pytest.mark.parametrize("folder_game", [False, True])
def test_convert_existing_chd_preserves_id_and_metadata(client, session_id, make_rom, monkeypatch, disc, system, folder_game):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    payload, tracks = disc
    if folder_game:
        (storage.roms_dir(session_id, system) / "Disc").mkdir(parents=True, exist_ok=True)
    rom = make_rom(system_key=system, name="Disc/Disc.chd" if folder_game else "Disc.chd",
                   content=payload, favorite=1, korean_name="My disc", sd_exclude=1)
    url = f"/api/sessions/{session_id}/roms/{rom['id']}/convert-chd"
    response = client.post(url)
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed"}:
            break
        time.sleep(0.01)
    assert job["status"] == "done", job
    updated = row(rom["id"])
    assert updated["id"] == rom["id"]
    assert updated["favorite"] == 1 and updated["sd_exclude"] == 1
    assert updated["korean_name"] == "My disc"
    assert updated["rom_path"] == f"roms/{system}/Disc/Disc.cue"
    root = storage.session_root(session_id)
    assert not (root / rom["rom_path"]).exists()
    extra = json.loads(updated["extra_files"])
    for entry, data in zip(extra, tracks):
        assert (root / Path(updated["rom_path"]).parent / entry["name"]).read_bytes() == data
    # Web player retrieves the CUE and every sidecar by the generated name.
    response = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/rom")
    assert response.status_code == 200
    for entry, data in zip(extra, tracks):
        assert entry["name"].encode() in response.content
        track = client.get(f"/api/sessions/{session_id}/roms/{rom['id']}/cdfile", params={"name": entry["name"]})
        assert track.status_code == 200 and track.content == data
    assert client.post(url).status_code == 400


def test_existing_chd_failure_retains_source_and_row(client, session_id, make_rom, monkeypatch):
    (storage.roms_dir(session_id, "pcecd") / "Disc").mkdir(parents=True, exist_ok=True)
    rom = make_rom(system_key="pcecd", name="Disc/Disc.chd", content=b"original CHD")
    monkeypatch.setattr(cdrom.shutil, "which", lambda _: None)
    import asyncio
    with pytest.raises(Exception):
        asyncio.run(cdrom.convert_library_chd(session_id, rom["id"]))
    assert (storage.session_root(session_id) / rom["rom_path"]).read_bytes() == b"original CHD"
    assert row(rom["id"])["rom_path"] == rom["rom_path"]
    assert not list(storage.roms_dir(session_id, "pcecd").glob(".incoming-*"))
