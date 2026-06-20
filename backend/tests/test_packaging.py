# -*- coding: utf-8 -*-
"""SD-zip membership rules in packaging._excluded — especially the per-ROM
opt-out (sd_exclude → excluded_roms) that keeps a file in the library but drops
it (and its cover) from the SD download."""
from pathlib import Path

from app import config
from app.services.packaging import _excluded


def _p(root: Path, rel: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


def test_normal_rom_is_included(tmp_path):
    rom = _p(tmp_path, f"{config.ROMS_DIR_NAME}/a2600/Pitfall.bin")
    assert _excluded(tmp_path, rom, include_video=False) is False


def test_excluded_rom_file_is_dropped(tmp_path):
    rel = f"{config.ROMS_DIR_NAME}/a2600/Custer.bin"
    rom = _p(tmp_path, rel)
    assert _excluded(tmp_path, rom, include_video=False, excluded_roms={rel}) is True


def test_excluded_set_also_drops_its_cover(tmp_path):
    cover_rel = "covers/a2600/Custer.img"
    cover = _p(tmp_path, cover_rel)
    assert _excluded(tmp_path, cover, include_video=False, excluded_roms={cover_rel}) is True


def test_excluded_roms_does_not_affect_other_files(tmp_path):
    keep = _p(tmp_path, f"{config.ROMS_DIR_NAME}/a2600/Pitfall.bin")
    other_rel = f"{config.ROMS_DIR_NAME}/a2600/Custer.bin"
    _p(tmp_path, other_rel)
    assert _excluded(tmp_path, keep, include_video=False, excluded_roms={other_rel}) is False
