# -*- coding: utf-8 -*-
"""GNW_EXPERIMENTAL_MODE ("personal lab") gating.

Official mode (flag off) must expose ONLY what the upstream sylverb firmware
registers (which now includes PC Engine CD and Atari Lynx) and keep fork-only
content — experimental system folders, /media, /music — out of the SD zip.
Experimental mode restores the full fork feature set. The flag is read at call
time from config, so tests flip `config.EXPERIMENTAL_MODE` via monkeypatch.
"""
from pathlib import Path

import pytest

from app import config
from app.services.packaging import _excluded
from app.systems import EXPERIMENTAL_DIRNAMES, SYSTEMS, available_systems, get_system


# The upstream rg_emulators.c registration, verbatim. PC Engine CD and Atari Lynx
# joined it upstream on 2026-07-05.
UPSTREAM_OFFICIAL = {
    "nes", "gb", "gbc", "gg", "sms", "md", "sg", "pce", "pcecd", "col", "msx",
    "a2600", "a7800", "amstrad", "wsv", "lynx", "tama", "mini", "gw",
    "homebrew", "pico8",
}


def _p(root: Path, rel: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


def test_experimental_flags_match_upstream_registration():
    assert {s.key for s in SYSTEMS if not s.experimental} == UPSTREAM_OFFICIAL
    assert EXPERIMENTAL_DIRNAMES == {
        "ngp", "ws", "vb", "videopac", "zxs", "c64", "gamecom",
    }


def test_available_systems_official_mode(monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    assert {s.key for s in available_systems()} == UPSTREAM_OFFICIAL


def test_available_systems_experimental_mode(monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    assert available_systems() == SYSTEMS


@pytest.mark.parametrize("dirname", sorted(EXPERIMENTAL_DIRNAMES))
def test_official_zip_drops_experimental_system_folders(tmp_path, monkeypatch, dirname):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    rom = _p(tmp_path, f"{config.ROMS_DIR_NAME}/{dirname}/Game.bin")
    cover = _p(tmp_path, f"{config.COVERS_DIR_NAME}/{dirname}/Game.img")
    assert _excluded(tmp_path, rom, include_video=False) is True
    assert _excluded(tmp_path, cover, include_video=False) is True


def test_official_zip_keeps_official_system_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    rom = _p(tmp_path, f"{config.ROMS_DIR_NAME}/lynx/Game.lnx")
    assert _excluded(tmp_path, rom, include_video=False) is False


def test_experimental_zip_keeps_experimental_system_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    rom = _p(tmp_path, f"{config.ROMS_DIR_NAME}/ngp/Game.ngp")
    assert _excluded(tmp_path, rom, include_video=False) is False


def test_official_zip_never_ships_media_even_with_video_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    avi = _p(tmp_path, f"{config.MEDIA_DIR_NAME}/clip.avi")
    assert _excluded(tmp_path, avi, include_video=True) is True


def test_official_zip_drops_music(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    mp3 = _p(tmp_path, f"{config.MUSIC_DIR_NAME}/song.mp3")
    assert _excluded(tmp_path, mp3, include_video=False) is True


def test_experimental_zip_keeps_music_and_opted_in_media(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    mp3 = _p(tmp_path, f"{config.MUSIC_DIR_NAME}/song.mp3")
    avi = _p(tmp_path, f"{config.MEDIA_DIR_NAME}/clip.avi")
    assert _excluded(tmp_path, mp3, include_video=False) is False
    assert _excluded(tmp_path, avi, include_video=True) is False
    assert _excluded(tmp_path, avi, include_video=False) is True  # still opt-in


def test_require_system_enabled_blocks_experimental_uploads(monkeypatch):
    from fastapi import HTTPException

    from app.routers.sessions import require_experimental_mode, require_system_enabled

    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    with pytest.raises(HTTPException) as exc:
        require_system_enabled(get_system("ngp"))
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        require_experimental_mode()
    require_system_enabled(get_system("lynx"))  # official → no raise

    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    require_system_enabled(get_system("ngp"))  # lab mode → no raise
    require_experimental_mode()
