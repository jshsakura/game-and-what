"""Cover rendering pipeline: services/covers.py and services/covers_pico8.py.

Pins the device-cover contract ported from the firmware's tools/gencovers.py:
max 186x100 (or an exact per-system target when given), aspect preserved,
LANCZOS resampling, JPEG output capped at COVER_MAX_BYTES, EXIF orientation
applied before cropping, and the optional language-flag overlay. Also pins
covers_pico8.py's square PICO-8 cart-label extraction (from both .p8 text and
.p8.png cart forms). All images are small, generated in-memory/on tmp_path —
no network, no fixtures from other test files.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.services import covers, covers_pico8
from app.services.covers import (
    MAX_HEIGHT,
    MAX_WIDTH,
    CoverError,
    calculate_new_size,
    cover_filename,
    overlay_lang_flag,
    render_cover,
    render_display,
    render_preview,
)
from app.services.covers_pico8 import (
    _LABEL_SIZE,
    _PALETTE,
    extract_label,
    render_pico8_cover,
    render_pico8_preview,
)


def _png_bytes(size=(400, 300), color=(200, 50, 50)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_with_orientation(size=(300, 200), color=(10, 20, 30), orientation=6) -> bytes:
    """A JPEG whose EXIF says it needs rotating (mirrors a phone-camera photo)."""
    img = Image.new("RGB", size, color)
    exif = img.getexif()
    exif[0x0112] = orientation
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data))


# ---------------------------------------------------------------------------
# calculate_new_size
# ---------------------------------------------------------------------------

def test_calculate_new_size_downscales_preserving_aspect_ratio():
    # Arrange: 2x wider than the envelope allows at that height.
    # Act
    size = calculate_new_size((372, 200))
    # Assert
    assert size == (186, 100)


def test_calculate_new_size_never_upscales_past_target_caps():
    size = calculate_new_size((100, 50), target_width=500, target_height=500)
    assert size[0] <= MAX_WIDTH and size[1] <= MAX_HEIGHT


def test_calculate_new_size_portrait_image_is_bound_by_height():
    size = calculate_new_size((100, 400))
    assert size[1] == MAX_HEIGHT
    assert size[0] < MAX_WIDTH


def test_calculate_new_size_rejects_zero_dimension():
    with pytest.raises(CoverError):
        calculate_new_size((0, 100))


# ---------------------------------------------------------------------------
# overlay_lang_flag
# ---------------------------------------------------------------------------

def test_overlay_lang_flag_noop_without_lang():
    img = Image.new("RGB", (186, 100), (0, 0, 0))
    out = overlay_lang_flag(img, None)
    assert out is img


def test_overlay_lang_flag_noop_for_unknown_language_code():
    img = Image.new("RGB", (186, 100), (0, 0, 0))
    out = overlay_lang_flag(img, "xx-unknown")
    assert out is img


def test_overlay_lang_flag_bakes_flag_into_top_right_corner():
    img = Image.new("RGB", (186, 100), (0, 0, 0))
    out = overlay_lang_flag(img, "ko")
    assert out.size == img.size
    # Somewhere in the top-right quadrant the flag replaced the black background.
    top_right = out.crop((out.width - 60, 0, out.width, 30))
    assert any(px != (0, 0, 0) for px in top_right.getdata())
    # Far corner (bottom-left) is untouched by the small overlay.
    assert out.getpixel((1, out.height - 2)) == (0, 0, 0)


def test_overlay_lang_flag_noop_when_asset_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(covers, "_FLAGS_DIR", tmp_path)  # empty dir, no flags/*.png
    img = Image.new("RGB", (186, 100), (5, 5, 5))
    out = overlay_lang_flag(img, "ko")
    assert out is img


def test_overlay_lang_flag_noop_when_asset_is_corrupt(monkeypatch, tmp_path):
    (tmp_path / "kr.png").write_bytes(b"not a real png")
    monkeypatch.setattr(covers, "_FLAGS_DIR", tmp_path)
    img = Image.new("RGB", (186, 100), (5, 5, 5))
    out = overlay_lang_flag(img, "ko")
    assert out is img


# ---------------------------------------------------------------------------
# render_cover
# ---------------------------------------------------------------------------

def test_render_cover_fit_within_envelope_default():
    data = render_cover(_png_bytes(size=(372, 200)))
    img = _open(data)
    assert img.format == "JPEG"
    assert img.size == (186, 100)


def test_render_cover_exact_target_crops_to_fill():
    data = render_cover(_png_bytes(size=(400, 100)), target_width=120, target_height=100)
    img = _open(data)
    assert img.size == (120, 100)


def test_render_cover_target_is_capped_by_hardware_envelope():
    data = render_cover(_png_bytes(size=(400, 400)), target_width=500, target_height=500)
    img = _open(data)
    assert img.size == (MAX_WIDTH, MAX_HEIGHT)


def test_render_cover_legacy_crop_flag_fills_186x100():
    data = render_cover(_png_bytes(size=(300, 300)), crop=True)
    img = _open(data)
    assert img.size == (MAX_WIDTH, MAX_HEIGHT)


def test_render_cover_applies_user_crop_box_before_sizing():
    # Arrange: right half is a distinct color from the left half.
    img = Image.new("RGB", (200, 100), (0, 0, 0))
    for x in range(100, 200):
        for y in range(100):
            img.putpixel((x, y), (255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")

    # Act: crop just the white right half.
    data = render_cover(buf.getvalue(), target_width=50, target_height=50,
                         crop_box=(0.5, 0.0, 0.5, 1.0))

    # Assert
    out = _open(data).convert("RGB")
    assert out.size == (50, 50)
    r, g, b = out.getpixel((25, 25))
    assert r > 200 and g > 200 and b > 200


def test_crop_to_fill_rejects_zero_dimension_image():
    """Defensive guard in the private crop-to-fill helper (never hit through the
    public API since Pillow can't decode a real zero-size image)."""
    class _ZeroSize:
        size = (0, 5)

    with pytest.raises(CoverError):
        covers._crop_to_fill(_ZeroSize(), 10, 10)


def test_render_cover_rejects_invalid_crop_box():
    with pytest.raises(CoverError):
        render_cover(_png_bytes(), crop_box=(0.5, 0.5, 0.0, 0.5))


def test_render_cover_rejects_unreadable_source():
    with pytest.raises(CoverError):
        render_cover(b"this is not an image")


def test_render_cover_applies_exif_orientation_before_sizing():
    # A 300x200 photo tagged "needs 90-degree rotation" -> logically 200x300.
    data = render_cover(_jpeg_with_orientation(size=(300, 200)), target_width=50, target_height=80)
    img = _open(data)
    assert img.size == (50, 80)


def test_render_cover_bakes_language_flag_when_lang_given():
    plain = render_cover(_png_bytes(size=(186, 100), color=(0, 0, 0)))
    flagged = render_cover(_png_bytes(size=(186, 100), color=(0, 0, 0)), lang="ko")
    assert plain != flagged


def test_render_cover_accepts_path_source(tmp_path):
    path = tmp_path / "art.png"
    path.write_bytes(_png_bytes())
    data = render_cover(path)
    assert _open(data).format == "JPEG"


# ---------------------------------------------------------------------------
# render_preview
# ---------------------------------------------------------------------------

def test_render_preview_downscales_only_when_larger_than_max_side():
    data = render_preview(_png_bytes(size=(1000, 500)), max_side=200)
    img = _open(data)
    assert img.format == "WEBP"
    assert max(img.size) == 200
    assert img.size[0] / img.size[1] == pytest.approx(1000 / 500, rel=0.02)


def test_render_preview_never_upscales_small_source():
    data = render_preview(_png_bytes(size=(50, 40)), max_side=512)
    img = _open(data)
    assert img.size == (50, 40)


def test_render_preview_applies_crop_box():
    img = Image.new("RGB", (200, 100), (0, 0, 0))
    for x in range(100, 200):
        for y in range(100):
            img.putpixel((x, y), (255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")

    data = render_preview(buf.getvalue(), crop_box=(0.5, 0.0, 0.5, 1.0))
    out = _open(data).convert("RGB")
    assert out.size == (100, 100)
    assert out.getpixel((50, 50))[0] > 200


def test_render_preview_never_bakes_a_flag():
    """The web 'original' preview stays clean regardless of `lang`."""
    src = _png_bytes(size=(186, 100), color=(1, 2, 3))
    assert render_preview(src, lang="ko") == render_preview(src, lang=None)


# ---------------------------------------------------------------------------
# render_display
# ---------------------------------------------------------------------------

def test_render_display_crops_to_system_ratio():
    data = render_display(_png_bytes(size=(400, 400)), target_width=186, target_height=100)
    img = _open(data)
    assert img.format == "WEBP"
    assert img.size[0] / img.size[1] == pytest.approx(186 / 100, rel=0.02)


def test_render_display_never_upscales_past_source():
    # Source shorter than max_height -> output height follows the source, not max_height.
    data = render_display(_png_bytes(size=(93, 50)), target_width=186, target_height=100,
                           max_height=400)
    img = _open(data)
    assert img.size[1] <= 50


def test_render_display_applies_crop_box_before_ratio_crop():
    img = Image.new("RGB", (200, 100), (0, 0, 0))
    for x in range(100, 200):
        for y in range(100):
            img.putpixel((x, y), (255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")

    data = render_display(buf.getvalue(), target_width=1, target_height=1,
                           crop_box=(0.5, 0.0, 0.5, 1.0), max_height=50)
    out = _open(data).convert("RGB")
    assert out.getpixel((out.width // 2, out.height // 2))[0] > 200


def test_render_display_bakes_language_flag():
    plain = render_display(_png_bytes(size=(200, 100), color=(0, 0, 0)), 186, 100)
    flagged = render_display(_png_bytes(size=(200, 100), color=(0, 0, 0)), 186, 100, lang="ko")
    assert plain != flagged


# ---------------------------------------------------------------------------
# cover_filename
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rom_path,expected", [
    ("/roms/msx/Aleste.rom", "Aleste.img"),
    ("Super Mario Bros. (USA).nes", "Super Mario Bros. (USA).img"),
    ("no_extension", "no_extension.img"),
    ("/deep/nested/path/Game.gbc", "Game.img"),
])
def test_cover_filename_swaps_extension_and_drops_directories(rom_path, expected):
    assert cover_filename(rom_path) == expected


# ---------------------------------------------------------------------------
# _encode_jpeg quality-reduction loop
# ---------------------------------------------------------------------------

def test_encode_jpeg_shrinks_quality_until_it_fits_max_bytes():
    img = Image.new("RGB", (186, 100), (128, 64, 200))
    data = covers._encode_jpeg(img, quality=85, max_bytes=covers.COVER_MAX_BYTES)
    assert len(data) <= covers.COVER_MAX_BYTES
    assert _open(data).format == "JPEG"


def test_encode_jpeg_returns_smallest_when_nothing_fits():
    # A photographic (noisy) image compresses poorly; an impossible byte cap
    # forces the loop through every quality step down to _JPEG_MIN_QUALITY.
    import random
    random.seed(0)
    img = Image.new("RGB", (186, 100))
    img.putdata([(random.randrange(256), random.randrange(256), random.randrange(256))
                 for _ in range(186 * 100)])
    data = covers._encode_jpeg(img, quality=85, max_bytes=1)
    assert len(data) > 0


def test_encode_jpeg_with_no_byte_cap_does_a_single_pass():
    img = Image.new("RGB", (186, 100), (1, 2, 3))
    data = covers._encode_jpeg(img, quality=95, max_bytes=None)
    assert _open(data).format == "JPEG"


# ---------------------------------------------------------------------------
# covers_pico8.py
# ---------------------------------------------------------------------------

_LABEL_CHARSET = "0123456789abcdefghijklmnopqrstuv"  # 32 chars -> full palette


def _p8_cart_text(rows: list[str]) -> str:
    body = "\n".join(rows)
    return f"pico-8 cartridge\nversion 1\n__lua__\n-- noop\n__label__\n{body}\n__gff__\nrest\n"


def test_extract_label_from_p8_text_maps_every_palette_index(tmp_path):
    rows = [_LABEL_CHARSET[i % len(_LABEL_CHARSET)] * _LABEL_SIZE for i in range(_LABEL_SIZE)]
    cart = tmp_path / "game.p8"
    cart.write_text(_p8_cart_text(rows), encoding="utf-8")

    label = extract_label(cart)

    assert label is not None
    assert label.size == (_LABEL_SIZE, _LABEL_SIZE)
    for i in (0, 1, 9, 10, 31, 127):
        assert label.getpixel((0, i)) == _PALETTE[i % len(_LABEL_CHARSET)]


def test_extract_label_from_p8_text_short_row_leaves_remainder_black(tmp_path):
    rows = ["f" * _LABEL_SIZE for _ in range(_LABEL_SIZE)]
    rows[5] = "f" * 50  # shorter than 128 -> tail stays default black
    cart = tmp_path / "game.p8"
    cart.write_text(_p8_cart_text(rows), encoding="utf-8")

    label = extract_label(cart)

    assert label.getpixel((49, 5)) == _PALETTE[15]  # 'f' -> index 15
    assert label.getpixel((60, 5)) == (0, 0, 0)      # beyond the short row


def test_extract_label_from_p8_text_unknown_char_maps_to_index_zero(tmp_path):
    rows = ["z" * _LABEL_SIZE for _ in range(_LABEL_SIZE)]  # 'z' is not 0-9/a-v
    cart = tmp_path / "game.p8"
    cart.write_text(_p8_cart_text(rows), encoding="utf-8")

    label = extract_label(cart)

    assert label.getpixel((0, 0)) == _PALETTE[0]


def test_extract_label_from_p8_text_too_few_rows_returns_none(tmp_path):
    rows = ["0" * _LABEL_SIZE for _ in range(_LABEL_SIZE - 1)]  # one row short
    cart = tmp_path / "game.p8"
    cart.write_text(_p8_cart_text(rows), encoding="utf-8")

    assert extract_label(cart) is None


def test_extract_label_from_p8_text_stops_at_next_section_marker(tmp_path):
    rows = ["0" * _LABEL_SIZE for _ in range(60)]
    text = (
        "__lua__\n-- noop\n__label__\n" + "\n".join(rows) + "\n__gff__\nmore rows here\n"
    )
    cart = tmp_path / "game.p8"
    cart.write_text(text, encoding="utf-8")

    # Only 60 label rows were captured before __gff__ cut it short -> < 128.
    assert extract_label(cart) is None


def test_extract_label_from_p8_png_snaps_to_nearest_palette_color(tmp_path):
    cart_img = Image.new("RGB", (160, 205), (17, 17, 17))
    label_color = _PALETTE[8]  # exact palette hit -> distance 0
    for x in range(16, 16 + _LABEL_SIZE):
        for y in range(24, 24 + _LABEL_SIZE):
            cart_img.putpixel((x, y), label_color)
    path = tmp_path / "game.p8.png"
    cart_img.save(path, format="PNG")

    label = extract_label(path)

    assert label.size == (_LABEL_SIZE, _LABEL_SIZE)
    assert label.getpixel((0, 0)) == label_color
    assert label.getpixel((_LABEL_SIZE - 1, _LABEL_SIZE - 1)) == label_color


def test_extract_label_from_p8_png_too_small_returns_none(tmp_path):
    path = tmp_path / "game.p8.png"
    Image.new("RGB", (100, 100), (0, 0, 0)).save(path, format="PNG")
    assert extract_label(path) is None


def test_extract_label_unknown_extension_returns_none(tmp_path):
    path = tmp_path / "game.txt"
    path.write_text("not a cart")
    assert extract_label(path) is None


def _valid_p8_cart(tmp_path: Path) -> Path:
    rows = ["8" * _LABEL_SIZE for _ in range(_LABEL_SIZE)]
    cart = tmp_path / "game.p8"
    cart.write_text(_p8_cart_text(rows), encoding="utf-8")
    return cart


def test_render_pico8_cover_produces_100x100_square_jpeg(tmp_path):
    cart = _valid_p8_cart(tmp_path)
    data = render_pico8_cover(cart)
    img = _open(data)
    assert img.format == "JPEG"
    assert img.size == (100, 100)  # 128x128 fit-within 186x100 -> 100x100


def test_render_pico8_cover_raises_without_a_label(tmp_path):
    path = tmp_path / "empty.p8"
    path.write_text("no label section here", encoding="utf-8")
    with pytest.raises(CoverError):
        render_pico8_cover(path)


def test_render_pico8_preview_produces_square_webp(tmp_path):
    cart = _valid_p8_cart(tmp_path)
    data = render_pico8_preview(cart)
    img = _open(data)
    assert img.format == "WEBP"
    assert img.size == (covers_pico8.PICO8_PREVIEW_SIDE, covers_pico8.PICO8_PREVIEW_SIDE)


def test_render_pico8_preview_custom_side(tmp_path):
    cart = _valid_p8_cart(tmp_path)
    data = render_pico8_preview(cart, side=64)
    assert _open(data).size == (64, 64)


def test_render_pico8_preview_raises_without_a_label(tmp_path):
    path = tmp_path / "empty.p8"
    path.write_text("no label section here", encoding="utf-8")
    with pytest.raises(CoverError):
        render_pico8_preview(path)


def test_rom_terms_falls_back_to_the_snes_cart_title():
    """A Korean-only filename gives the cover search nothing latin — both the stored and
    original names are Hangul and get rejected as unsearchable. The cart's own header
    name is the only thing left, and without it these roms can never get art."""
    from app.routers.covers import _rom_terms
    rom = {"stored_name": "혼두라 스피릿츠.smc", "original_name": "혼두라 스피릿츠",
           "korean_name": None, "snes_title": "CONTRA SPIRITS"}
    assert "CONTRA SPIRITS" in _rom_terms(rom)


def test_rom_terms_prefers_the_curated_filename_over_the_cart_title():
    """The filename is what the user curated. The header name is a fallback, not a
    replacement — a cart whose internal name is a stub must not outrank a good title."""
    from app.routers.covers import _rom_terms
    rom = {"stored_name": "혼두라 스피릿츠 (Contra Spirits).smc",
           "original_name": "혼두라 스피릿츠 (Contra Spirits)",
           "korean_name": None, "snes_title": "CONTRA SPIRITS"}
    terms = _rom_terms(rom)
    assert terms[0] == "Contra Spirits", terms
