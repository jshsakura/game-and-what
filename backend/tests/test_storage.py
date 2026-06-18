# -*- coding: utf-8 -*-
"""safe_name() filename sanitization for the SD card's FAT/exFAT filesystem."""
import unicodedata

from app import config
from app.services import storage
from app.services.storage import safe_name


def test_subtitle_colon_becomes_hyphen():
    # FAT forbids ':' — a subtitle colon should read as ' - ', not '_'.
    assert safe_name("스타워즈: 제국의 역습 (Star Wars)") == "스타워즈 - 제국의 역습 (Star Wars)"


def test_colon_without_space_still_spaced_hyphen():
    assert safe_name("판타지 존 2:오파 오파의 눈물") == "판타지 존 2 - 오파 오파의 눈물"


def test_other_illegal_chars_fall_back_to_underscore():
    assert safe_name('bad/slash*?') == "bad_slash__"


def test_genuine_underscore_is_preserved():
    # 'C_So!' is a real game name — its underscore is not a sanitized colon.
    assert safe_name("C_So!") == "C_So!"


def test_plain_name_unchanged():
    assert safe_name("Plain Name") == "Plain Name"


def test_empty_falls_back_to_untitled():
    assert safe_name("") == "untitled"
    assert safe_name("   ") == "untitled"


def test_result_is_nfc_normalized():
    decomposed = unicodedata.normalize("NFD", "한글")
    assert safe_name(decomposed) == unicodedata.normalize("NFC", "한글")


def test_sweep_temp_uploads_removes_orphans_keeps_real(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LIBRARY_DIR", tmp_path)
    media = tmp_path / "public" / config.MEDIA_DIR_NAME
    media.mkdir(parents=True)
    (media / ".src_abc").write_bytes(b"x")
    (media / ".src_def").write_bytes(b"y")
    (media / "keep.avi").write_bytes(b"z")

    removed = storage.sweep_temp_uploads()

    assert removed == 2
    assert not list(media.glob(".src_*"))
    assert (media / "keep.avi").exists()


def test_sweep_temp_uploads_no_library_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LIBRARY_DIR", tmp_path / "missing")
    assert storage.sweep_temp_uploads() == 0
