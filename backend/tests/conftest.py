# -*- coding: utf-8 -*-
"""Shared test foundation for the whole backend/tests suite.

Fixture contract (names are load-bearing — other test files depend on these
EXACT signatures, do not rename):

    data_dir(tmp_path, monkeypatch) -> Path
        Isolated data directory for the test. `app.config.DATA_DIR`,
        `LIBRARY_DIR`, `DB_PATH`, `TMP_DIR` (and every module-level constant
        elsewhere derived from them at IMPORT time, e.g.
        `services.name_map.MAP_PATH` and `services.pico8core._CACHE`/`_CORES`/
        `_CORES`) are monkeypatched to live under it, and the directories are
        created. Nothing is written outside `tmp_path`.

    session_id(data_dir) -> str
        Initializes the sqlite schema (`db.init_db()`) under the isolated
        `data_dir` and returns `config.SHARED_SESSION_ID` ("public"), which
        `init_db()` guarantees exists as a row in `sessions`.

    client(data_dir) -> fastapi.testclient.TestClient
        The REAL app (`app.main:app`) wrapped in a TestClient, with `data_dir`
        active. Entering the TestClient context runs the app's startup event
        (schema init/migration, shared-session creation, temp-file sweep,
        etc.) against the isolated data dir. No network access is possible
        (see `no_network` below), so anything that would reach out to
        IGDB/TGDB/SteamGridDB/libretro/tistory/a pico8-core download must be
        monkeypatched by the test itself.

    make_rom(system_key="nes", name="Game.nes", **cols) -> dict
        Factory fixture. Writes a real (fake-content) ROM file under the
        shared session's roms dir for `system_key` and inserts the matching
        `roms` row (any extra `**cols` are passed straight through as column
        overrides — e.g. `korean_name=...`, `is_korean_patched=1`). Returns
        the inserted row as a plain dict (at least "id", "stored_name",
        "system_key", "rom_path"). Depends on `session_id`, so the schema is
        always ready.

    no_network (autouse)
        Any real outbound HTTP (httpx's default network transport, requests,
        urllib) raises immediately instead of hanging or hitting the internet.
        `TestClient` is unaffected — it talks to the app over httpx's
        in-process ASGI transport, not the real network transport this
        fixture blocks.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Callable

import httpx
import pytest
import requests
from fastapi.testclient import TestClient

from app import config, db
from app.services import name_map, pico8core, storage
from app.systems import get_system


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _blocked(*_args, **_kwargs):
        raise RuntimeError(
            "Network access is blocked in tests (no_network fixture) — "
            "mock the HTTP call instead of hitting the real network."
        )

    # Only the REAL network transports are blocked. TestClient talks to the
    # app through its own in-process ASGI transport (a plain httpx.BaseTransport
    # subclass), which never touches HTTPTransport/AsyncHTTPTransport.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _blocked)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", _blocked)
    monkeypatch.setattr(urllib.request, "urlopen", _blocked)


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch) -> Path:
    d = tmp_path / "gnw_data"
    d.mkdir()

    monkeypatch.setattr(config, "DATA_DIR", d)
    monkeypatch.setattr(config, "LIBRARY_DIR", d / "library")
    monkeypatch.setattr(config, "DB_PATH", d / "gnw.db")
    monkeypatch.setattr(config, "TMP_DIR", d / "tmp")

    # These modules compute their path constants ONCE at import time from
    # config.DATA_DIR/TMP_DIR rather than reading config at call time, so a
    # plain monkeypatch of config above wouldn't redirect them — patch the
    # already-imported module attributes directly instead.
    monkeypatch.setattr(name_map, "MAP_PATH", d / "name_map.json")
    pico8_cache = d / "tmp" / "pico8_cores"
    monkeypatch.setattr(pico8core, "_CACHE", pico8_cache)
    monkeypatch.setattr(pico8core, "_CORES", pico8_cache / "cores")

    config.ensure_dirs()
    return d


@pytest.fixture
def session_id(data_dir: Path) -> str:
    db.init_db()
    return config.SHARED_SESSION_ID


@pytest.fixture
def client(data_dir: Path):
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_rom(session_id: str) -> Callable[..., dict]:
    def _make_rom(system_key: str = "nes", name: str = "Game.nes", **cols) -> dict:
        system = get_system(system_key)
        rom_id = cols.pop("id", None) or storage.new_id()
        stored_name = cols.pop("stored_name", name)
        original_name = cols.pop("original_name", name)
        content = cols.pop("content", b"fake-rom-bytes")

        dest_dir = storage.roms_dir(session_id, system.dirname)
        dest_dir.mkdir(parents=True, exist_ok=True)
        rom_file = dest_dir / stored_name
        rom_file.write_bytes(content)

        row = {
            "id": rom_id,
            "session_id": session_id,
            "system_key": system_key,
            "original_name": original_name,
            "stored_name": stored_name,
            "rom_path": storage.relative_to_session(session_id, rom_file),
            **cols,
        }
        columns = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        with db.connect() as conn:
            conn.execute(
                f"INSERT INTO roms ({columns}) VALUES ({placeholders})",
                tuple(row.values()),
            )
            saved = conn.execute("SELECT * FROM roms WHERE id = ?", (rom_id,)).fetchone()
        return dict(saved)

    return _make_rom
