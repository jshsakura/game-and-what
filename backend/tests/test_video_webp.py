# -*- coding: utf-8 -*-
"""Animated WebP → clock bg.gif: ffmpeg's built-in webp decoder can't read the
ANIM/ANMF chunks of an animated WebP (it errors out with "Decode error rate 1
exceeds maximum"), so encode_to_clock_gif() must detect that case and hand
ffmpeg a real GIF instead. These tests exercise the Pillow-based detection and
conversion directly (no ffmpeg needed — pure image logic)."""
from PIL import Image

from app.services import video


def _make_animated_webp(path, frames=3):
    imgs = [Image.new("RGB", (40, 30), c) for c in [(255, 0, 0), (0, 255, 0), (0, 0, 255)][:frames]]
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=100, loop=0)


def _make_static_webp(path):
    Image.new("RGB", (40, 30), (10, 20, 30)).save(path)


def test_detects_animated_webp(tmp_path):
    p = tmp_path / "src.webp"
    _make_animated_webp(p)
    assert video._is_animated_webp(p) is True


def test_static_webp_is_not_animated(tmp_path):
    p = tmp_path / "src.webp"
    _make_static_webp(p)
    assert video._is_animated_webp(p) is False


def test_non_webp_suffix_is_never_animated(tmp_path):
    p = tmp_path / "src.png"
    Image.new("RGB", (40, 30), (0, 0, 0)).save(p)
    assert video._is_animated_webp(p) is False


def test_animated_webp_converts_to_playable_gif(tmp_path):
    src = tmp_path / "src.webp"
    _make_animated_webp(src, frames=3)
    out = video._animated_webp_to_gif(src)
    assert out.suffix == ".gif"
    assert out.exists()
    with Image.open(out) as im:
        assert im.format == "GIF"
        assert getattr(im, "n_frames", 1) == 3
