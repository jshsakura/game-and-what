# -*- coding: utf-8 -*-
"""PICO-8 support: compat lookup (pico8_compat), the static memory-pressure hint
computed from a .p8.png's steganographic header (pico8_memhint), and the SD
core-download/cache logic (pico8core). All network/filesystem access is faked
or redirected under tmp_path — no real GitHub calls, no real cart images."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from app.services import pico8_compat, pico8_memhint, pico8core

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


# =====================================================================
# pico8_compat.lookup()
# =====================================================================

@pytest.fixture(autouse=True)
def _reset_compat_cache(monkeypatch):
    """Each test gets a fresh module cache so _PATH swaps actually take effect."""
    monkeypatch.setattr(pico8_compat, "_COMPAT", None)
    yield
    monkeypatch.setattr(pico8_compat, "_COMPAT", None)


def test_lookup_known_good_cart_by_exact_stem():
    # 'muse' is a real bundled entry with status 'good'.
    assert pico8_compat.lookup("muse.p8.png") == "good"


def test_lookup_strips_leading_article_and_trailing_version_suffix():
    # 'A Muse-2.p8.png' should normalize down to the same 'muse' key.
    assert pico8_compat.lookup("A Muse-2.p8.png") == "good"


def test_lookup_is_case_insensitive_and_ignores_punctuation():
    assert pico8_compat.lookup("The MUSE!!.p8.png") == "good"


def test_lookup_partial_status():
    assert pico8_compat.lookup("Bomb Jack.p8.png") == "partial"


def test_lookup_broken_status():
    assert pico8_compat.lookup("Driftmania.p8.png") == "broken"


def test_lookup_unknown_cart_returns_none():
    assert pico8_compat.lookup("Some Totally Unknown Homebrew Cart Xyzzy") is None


def test_lookup_empty_name_returns_none():
    assert pico8_compat.lookup("") is None


def test_load_falls_back_to_empty_dict_on_bad_json(monkeypatch, tmp_path):
    bad = tmp_path / "compat.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(pico8_compat, "_PATH", bad)
    assert pico8_compat.lookup("muse") is None


def test_load_falls_back_to_empty_dict_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(pico8_compat, "_PATH", tmp_path / "does_not_exist.json")
    assert pico8_compat.lookup("muse") is None


def test_load_caches_result_across_calls(monkeypatch, tmp_path):
    custom = tmp_path / "compat.json"
    custom.write_text(json.dumps({"foo": {"status": "good", "note": ""}}), encoding="utf-8")
    monkeypatch.setattr(pico8_compat, "_PATH", custom)
    assert pico8_compat.lookup("foo") == "good"
    # Mutate the file after the first load; cached dict must not change.
    custom.write_text(json.dumps({"foo": {"status": "broken", "note": ""}}), encoding="utf-8")
    assert pico8_compat.lookup("foo") == "good"


# =====================================================================
# pico8_memhint.estimate()
# =====================================================================

_CART_W, _CART_H = 160, 205
_CODE_OFFSET = 0x4300


def _encode_bytes(px, data: bytes, start: int) -> None:
    """Write `data` into the steganographic low-2-bits-per-channel layout that
    _read_cart_bytes decodes, starting at cart-byte offset `start`."""
    for i, byte in enumerate(data):
        idx = start + i
        x, y = idx % _CART_W, idx // _CART_W
        assert y < _CART_H, "test fixture wrote past the cart image bounds"
        r = (byte >> 4) & 3
        g = (byte >> 2) & 3
        b = byte & 3
        a = (byte >> 6) & 3
        px[x, y] = (r, g, b, a)


def _make_cart(tmp_path: Path, name: str, code: bytes, size=(_CART_W, _CART_H)) -> Path:
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    px = im.load()
    if size == (_CART_W, _CART_H):
        _encode_bytes(px, code, _CODE_OFFSET)
    path = tmp_path / name
    im.save(path, format="PNG")
    return path


def test_estimate_none_when_image_wrong_size(tmp_path):
    cart = _make_cart(tmp_path, "wrongsize.p8.png", b"", size=(100, 100))
    assert pico8_memhint.estimate(cart) is None


def test_estimate_none_when_not_a_real_image(tmp_path):
    cart = tmp_path / "notanimage.p8.png"
    cart.write_bytes(b"this is not a png file at all")
    assert pico8_memhint.estimate(cart) is None


def test_estimate_pxa_format_uses_compressed_ratio(tmp_path):
    # PXA header: b'\x00pxa' + chars(2 bytes BE) + compressed(2 bytes BE).
    chars = 1000
    compressed = 7808  # exactly half of _COMPRESSED_LIMIT (0x3d00 = 15616)
    header = b"\x00pxa" + chars.to_bytes(2, "big") + compressed.to_bytes(2, "big")
    cart = _make_cart(tmp_path, "pxa.p8.png", header)
    pct = pico8_memhint.estimate(cart)
    # compressed ratio (50%) dominates over chars ratio (1000/65535 ~= 1.5%)
    assert pct == 50


def test_estimate_old_format_uses_char_ratio_only(tmp_path):
    chars = 6554  # 10% of 65535 (rounded)
    header = b":c:\x00" + chars.to_bytes(2, "big") + b"\x00\x00"
    cart = _make_cart(tmp_path, "old.p8.png", header)
    pct = pico8_memhint.estimate(cart)
    assert pct == round(chars / 0xFFFF * 100)


def test_estimate_uncompressed_ascii_scans_for_null_terminator(tmp_path):
    code = b"print('hello world')" + b"\x00"
    cart = _make_cart(tmp_path, "ascii.p8.png", code)
    pct = pico8_memhint.estimate(cart)
    expected_chars = len(code) - 1  # up to (not including) the null byte
    assert pct == round(expected_chars / 0xFFFF * 100)


def test_estimate_ascii_without_terminator_uses_full_scanned_length(tmp_path):
    # No null byte anywhere in the (bounded) scan window -> uses len(blob).
    code = b"x" * 50
    cart = _make_cart(tmp_path, "noterm.p8.png", code)
    pct = pico8_memhint.estimate(cart)
    assert pct is not None and pct >= 0


# =====================================================================
# pico8core.ensure_cores_dir()
# =====================================================================

class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture
def cache_dirs(tmp_path, monkeypatch):
    cache = tmp_path / "pico8_cores"
    cores = cache / "cores"
    monkeypatch.setattr(pico8core, "_CACHE", cache)
    monkeypatch.setattr(pico8core, "_CORES", cores)
    return cache, cores


def test_returns_cached_dir_without_hitting_network_when_present(cache_dirs, monkeypatch):
    cache, cores = cache_dirs
    cores.mkdir(parents=True)
    (cores / "pico8.elf").write_bytes(b"existing")

    def boom(*a, **k):
        raise AssertionError("should not hit the network when already cached")

    monkeypatch.setattr(pico8core, "_http", boom)
    result = pico8core.ensure_cores_dir()
    assert result == cores


def test_no_cache_and_network_error_returns_none(cache_dirs, monkeypatch):
    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(pico8core, "_http", boom)
    assert pico8core.ensure_cores_dir() is None


def test_downloads_and_extracts_cores_on_first_use(cache_dirs, monkeypatch):
    cache, cores = cache_dirs
    release = {
        "tag_name": "v1.2.3",
        "assets": [{"name": "dist.zip", "browser_download_url": "http://x/dist.zip"}],
    }
    zip_data = _zip_bytes({
        "pico8_gnw_distro-1.2.3/cores/pico8.elf": b"COREBIN",
        "pico8_gnw_distro-1.2.3/cores/sub/extra.bin": b"EXTRA",
        "pico8_gnw_distro-1.2.3/README.md": b"not under cores, skipped",
        "pico8_gnw_distro-1.2.3/cores/": b"",  # directory entry, must be skipped
    })
    calls = []

    def fake_http(url, timeout=30):
        calls.append(url)
        if url == pico8core._LATEST_API:
            return _FakeResponse(json.dumps(release).encode())
        return _FakeResponse(zip_data)

    monkeypatch.setattr(pico8core, "_http", fake_http)
    result = pico8core.ensure_cores_dir()

    assert result == cores
    assert (cores / "pico8.elf").read_bytes() == b"COREBIN"
    assert (cores / "sub" / "extra.bin").read_bytes() == b"EXTRA"
    assert not (cores / "README.md").exists()
    assert len(calls) == 2


def test_no_zip_asset_in_release_falls_back_to_cache(cache_dirs, monkeypatch):
    release = {"tag_name": "v1.0", "assets": [{"name": "readme.txt", "browser_download_url": "http://x"}]}

    def fake_http(url, timeout=30):
        return _FakeResponse(json.dumps(release).encode())

    monkeypatch.setattr(pico8core, "_http", fake_http)
    assert pico8core.ensure_cores_dir() is None


def test_corrupt_zip_falls_back_to_cache(cache_dirs, monkeypatch):
    release = {
        "tag_name": "v1.0",
        "assets": [{"name": "dist.zip", "browser_download_url": "http://x/dist.zip"}],
    }

    def fake_http(url, timeout=30):
        if url == pico8core._LATEST_API:
            return _FakeResponse(json.dumps(release).encode())
        return _FakeResponse(b"not actually a zip file")

    monkeypatch.setattr(pico8core, "_http", fake_http)
    assert pico8core.ensure_cores_dir() is None


def test_force_redownloads_even_when_the_release_is_unchanged(cache_dirs, monkeypatch):
    """force=True always re-downloads and re-extracts, which is what makes it usable
    as a repair for a half-written cache. (There used to be a "same release tag ->
    skip" short-circuit here, but it was unreachable — the guard above it already
    returned for every non-forced call — so the tag file it read was dead weight.)"""
    cache, cores = cache_dirs
    cores.mkdir(parents=True)
    (cores / "old.elf").write_bytes(b"old")

    release = {
        "tag_name": "v1.2.3",
        "assets": [{"name": "dist.zip", "browser_download_url": "http://x/dist.zip"}],
    }
    zip_data = _zip_bytes({"pico8_gnw_distro-1.2.3/cores/new.elf": b"NEW"})
    asset_calls = []

    def fake_http(url, timeout=30):
        if url == pico8core._LATEST_API:
            return _FakeResponse(json.dumps(release).encode())
        asset_calls.append(url)
        return _FakeResponse(zip_data)

    monkeypatch.setattr(pico8core, "_http", fake_http)
    result = pico8core.ensure_cores_dir(force=True)

    assert result == cores
    assert asset_calls == ["http://x/dist.zip"]       # re-fetched despite the same tag
    assert (cores / "new.elf").exists()
    assert not (cores / "old.elf").exists()           # stale cache replaced, not merged
