# -*- coding: utf-8 -*-
"""Per-ROM metadata resolution (metadata.resolve_metadata: local Korean-name
mapping + libretro-thumbnails URL construction, no network) and header sanity
checks (romcheck.md_header_warning: catches a Genesis/MD ROM whose header size
field wasn't bumped after a Korean patch grew the file)."""
from __future__ import annotations

import json
import struct

import pytest

from app import config
from app.services import metadata, romcheck


# =====================================================================
# metadata._rom_stem / _libretro_url
# =====================================================================

def test_rom_stem_strips_extension():
    assert metadata._rom_stem("Super Mario Bros. (USA).nes") == "Super Mario Bros. (USA)"


def test_rom_stem_no_extension_returns_whole_name():
    assert metadata._rom_stem("noext") == "noext"


def test_rom_stem_uses_only_the_basename():
    assert metadata._rom_stem("some/dir/Game (USA).nes") == "Game (USA)"


def test_libretro_url_known_system():
    url = metadata._libretro_url("nes", "Named_Snaps", "Super Mario Bros. (USA)")
    assert url == (
        "https://raw.githubusercontent.com/libretro-thumbnails/"
        "Nintendo_-_Nintendo_Entertainment_System/master/Named_Snaps/"
        "Super%20Mario%20Bros.%20%28USA%29.png"
    )


def test_libretro_url_unknown_system_returns_none():
    assert metadata._libretro_url("pico8", "Named_Snaps", "Anything") is None


def test_libretro_url_sanitizes_filesystem_illegal_chars():
    # libretro replaces &*/:`<>?\|" with '_' in its stored filenames.
    url = metadata._libretro_url("gg", "Named_Boxarts", 'Game: Sub/Title?')
    assert url is not None
    assert "Game_ Sub_Title_" in url or "Game_%20Sub_Title_" in url


# =====================================================================
# metadata._resolve_korean / resolve_metadata
# =====================================================================

@pytest.fixture
def korean_names_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    d = tmp_path / "korean_names"
    d.mkdir()
    return d


def test_resolve_korean_exact_stem_match(korean_names_dir):
    (korean_names_dir / "nes.json").write_text(
        json.dumps({"Contra (Japan)": "콘트라"}), encoding="utf-8"
    )
    assert metadata._resolve_korean("nes", "Contra (Japan)") == "콘트라"


def test_resolve_korean_falls_back_to_stripped_region(korean_names_dir):
    (korean_names_dir / "nes.json").write_text(
        json.dumps({"Contra": "콘트라"}), encoding="utf-8"
    )
    assert metadata._resolve_korean("nes", "Contra (Japan)") == "콘트라"


def test_resolve_korean_no_mapping_file_returns_none(korean_names_dir):
    assert metadata._resolve_korean("nes", "Contra (Japan)") is None


def test_resolve_korean_malformed_json_returns_none(korean_names_dir):
    (korean_names_dir / "nes.json").write_text("{not valid", encoding="utf-8")
    assert metadata._resolve_korean("nes", "Contra") is None


def test_resolve_korean_non_dict_json_returns_none(korean_names_dir):
    (korean_names_dir / "nes.json").write_text(json.dumps(["a", "b"]), encoding="utf-8")
    assert metadata._resolve_korean("nes", "Contra") is None


def test_resolve_korean_no_match_returns_none(korean_names_dir):
    (korean_names_dir / "nes.json").write_text(
        json.dumps({"Something Else": "다른이름"}), encoding="utf-8"
    )
    assert metadata._resolve_korean("nes", "Contra (Japan)") is None


def test_resolve_metadata_with_korean_hit(korean_names_dir):
    (korean_names_dir / "nes.json").write_text(
        json.dumps({"Contra": "콘트라"}), encoding="utf-8"
    )
    meta = metadata.resolve_metadata("nes", "Contra (Japan).nes")
    assert meta.original_name == "Contra (Japan)"
    assert meta.korean_name == "콘트라"
    assert meta.title == "콘트라"
    assert meta.source == "libretro"
    assert meta.screenshot_url.endswith("Contra%20%28Japan%29.png")
    assert meta.art_url == meta.screenshot_url


def test_resolve_metadata_without_korean_hit_falls_back_to_stem(korean_names_dir):
    meta = metadata.resolve_metadata("nes", "Some Unmapped Game (USA).nes")
    assert meta.korean_name is None
    assert meta.title == "Some Unmapped Game (USA)"
    assert meta.source == "libretro"  # libretro repo is known for 'nes'


def test_resolve_metadata_unknown_system_has_no_art_source(korean_names_dir):
    meta = metadata.resolve_metadata("pico8", "Some Cart.p8.png")
    assert meta.screenshot_url is None
    assert meta.boxart_url is None
    assert meta.art_url is None
    assert meta.source == "none"


def test_art_url_prefers_screenshot_over_boxart(korean_names_dir):
    meta = metadata.GameMeta(
        original_name="X", title="X", korean_name=None,
        screenshot_url="http://snap", boxart_url="http://box", source="libretro",
    )
    assert meta.art_url == "http://snap"


def test_art_url_falls_back_to_boxart_when_no_screenshot(korean_names_dir):
    meta = metadata.GameMeta(
        original_name="X", title="X", korean_name=None,
        screenshot_url=None, boxart_url="http://box", source="libretro",
    )
    assert meta.art_url == "http://box"


# =====================================================================
# romcheck.md_header_warning
# =====================================================================

def _md_bytes(rom_size: int, declared_size: int) -> bytes:
    """Build a minimal fake Genesis/MD ROM of exactly `rom_size` bytes (>= the
    0x1A8 header) and stamp `declared_size - 1` (big-endian u32) at the
    header's ROM-end field 0x1A4."""
    assert rom_size >= 0x1A8
    data = bytearray(rom_size)
    struct.pack_into(">I", data, 0x1A4, declared_size - 1)
    return bytes(data)


def test_md_header_matches_declared_size_no_warning():
    data = _md_bytes(0x2000, declared_size=0x2000)
    assert romcheck.md_header_warning("md", data) is None


def test_md_header_mismatch_warns():
    data = _md_bytes(0x2100, declared_size=0x2000)  # file grew (patched) w/o header bump
    warning = romcheck.md_header_warning("md", data)
    assert warning is not None
    assert "0x2000" in warning
    assert "0x2100" in warning


def test_md_header_non_md_system_never_warns():
    data = _md_bytes(0x2100, declared_size=0x2000)
    assert romcheck.md_header_warning("nes", data) is None


def test_md_header_too_short_returns_none():
    assert romcheck.md_header_warning("md", b"\x00" * 10) is None


def test_md_header_exactly_at_boundary_length():
    # len(data) == 0x1A8 exactly is the minimum length that's checked.
    data = _md_bytes(0x1A8, declared_size=0x1A8)
    assert romcheck.md_header_warning("md", data) is None
