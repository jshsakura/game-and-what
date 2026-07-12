# -*- coding: utf-8 -*-
"""Korean-name resolution machinery:

  - titlematch : fuzzy title scoring used to reject wrong auto-cover hits.
  - langfill   : one-time backfill of orig_lang/play_lang/is_korean_patched
                 and region onto EXISTING library rows.
  - name_index : persistent hash -> resolved-name cache (rom_names table).
  - name_map   : hash-keyed Korean-name map built from bundled + scratch
                 gamelist.xml sources, one JSON artifact per session.

All DB access here uses a throwaway sqlite3 connection built inline (NOT the
real app.db schema/migrations) since we only need the handful of columns each
pure function actually touches. Filesystem-facing name_map tests monkeypatch
config.KOREAN_NAMES_DIR / config.LIBRARY_DIR / name_map.MAP_PATH so nothing
touches the real data/ or app source tree.
"""
from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path

import pytest

from app import config
from app.services import langfill, name_index, name_map, storage, titlematch


# =====================================================================
# titlematch
# =====================================================================

def test_normalize_drops_bracketed_region_tags():
    assert titlematch.normalize("Sonic the Hedgehog (USA)") == "sonic the hedgehog"


def test_normalize_collapses_non_latin_scripts():
    assert titlematch.normalize("골든액스 Golden Axe") == "golden axe"


def test_normalize_empty_and_none():
    assert titlematch.normalize("") == ""
    assert titlematch.normalize(None) == ""


def test_score_empty_string_is_zero():
    assert titlematch.score("", "Anything") == 0.0
    assert titlematch.score("Anything", "") == 0.0


def test_score_region_only_query_is_rejected():
    # A bare region/dump word must not score against a title that contains it.
    assert titlematch.score("Japan", "All Japan Pro Wrestling") == 0.0
    assert titlematch.score("proto", "Proto Man Adventures") == 0.0


def test_score_sequel_number_mismatch_is_capped():
    # Different series numbers -> capped at 0.4, always below the threshold.
    s = titlematch.score("Rockman", "Rockman 2")
    assert s == 0.4
    assert not titlematch.matches("Rockman", "Rockman 2")


def test_score_lone_one_is_tolerated():
    # "Final Fight" == "Final Fight 1" (a lone '1' isn't a real sequel marker).
    assert titlematch.matches("Final Fight", "Final Fight 1")


def test_score_roman_numeral_matches_arabic():
    assert titlematch.score("Final Fight II", "Final Fight 2") == pytest.approx(1.0)


def test_score_stopwords_ignored_for_token_overlap():
    assert titlematch.score("The Legend of Zelda", "Legend of Zelda") == pytest.approx(1.0)


def test_score_containment_bonus():
    s = titlematch.score("Shinobi", "GG Shinobi")
    assert s >= 0.9
    assert titlematch.matches("Shinobi", "GG Shinobi")


def test_matches_respects_custom_threshold():
    score = titlematch.score("Fire Pro Wrestling", "R-Type")
    assert score < titlematch.DEFAULT_THRESHOLD
    assert not titlematch.matches("Fire Pro Wrestling", "R-Type")
    assert titlematch.matches("Fire Pro Wrestling", "R-Type", threshold=0.0)


def test_best_picks_highest_scoring_candidate_above_threshold():
    candidates = [
        ("Fire Pro Wrestling", "payload-a"),
        ("R-Type", "payload-b"),
        ("R-Type II", "payload-c"),
    ]
    result = titlematch.best("R-Type", candidates)
    assert result == ("R-Type", "payload-b")


def test_best_returns_none_when_nothing_clears_threshold():
    candidates = [("Fire Pro Wrestling", "x"), ("Puzzle Bobble", "y")]
    assert titlematch.best("R-Type", candidates) is None


def test_best_empty_candidate_list():
    assert titlematch.best("Anything", []) is None


# =====================================================================
# langfill
# =====================================================================

def _lang_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE roms (
            id TEXT PRIMARY KEY, original_name TEXT, stored_name TEXT,
            orig_lang TEXT, play_lang TEXT,
            is_korean_patched INTEGER NOT NULL DEFAULT 0,
            lang_source TEXT, region TEXT
        )"""
    )
    return conn


def test_backfill_classifies_only_unclassified_rows():
    conn = _lang_conn()
    conn.execute(
        "INSERT INTO roms (id, original_name, stored_name) VALUES (?, ?, ?)",
        ("r1", "Contra (Korea-patch J-K v20200912 v1.0).nes", "콘트라.nes"),
    )
    conn.execute(
        """INSERT INTO roms (id, original_name, stored_name, lang_source,
               orig_lang, play_lang, is_korean_patched)
           VALUES (?, ?, ?, 'manual', 'en', 'en', 0)""",
        ("r2", "Some Game (USA).nes", "Some Game (USA).nes"),
    )
    conn.commit()

    updated = langfill.backfill(conn)

    assert updated == 1
    row1 = conn.execute("SELECT * FROM roms WHERE id = 'r1'").fetchone()
    assert row1["orig_lang"] == "ja"
    assert row1["play_lang"] == "ko"
    assert row1["is_korean_patched"] == 1
    assert row1["lang_source"] == "auto"
    # Already-classified (manual) row is left untouched.
    row2 = conn.execute("SELECT * FROM roms WHERE id = 'r2'").fetchone()
    assert row2["lang_source"] == "manual"
    assert row2["orig_lang"] == "en"


def test_backfill_marks_unrecognized_names_as_classified_auto():
    conn = _lang_conn()
    conn.execute(
        "INSERT INTO roms (id, original_name, stored_name) VALUES (?, ?, ?)",
        ("r1", "볼.gw", "볼 (Ball).gw"),
    )
    conn.commit()

    updated = langfill.backfill(conn)

    assert updated == 1
    row = conn.execute("SELECT * FROM roms WHERE id = 'r1'").fetchone()
    assert row["orig_lang"] is None
    assert row["is_korean_patched"] == 0
    assert row["lang_source"] == "auto"  # marked so it's never rescanned


def test_backfill_no_rows_returns_zero():
    conn = _lang_conn()
    assert langfill.backfill(conn) == 0


def test_backfill_region_fills_from_original_name():
    conn = _lang_conn()
    conn.execute(
        "INSERT INTO roms (id, original_name, stored_name) VALUES (?, ?, ?)",
        ("r1", "Antarctic Adventure (Japan).nes", "남극탐험.nes"),
    )
    conn.commit()

    updated = langfill.backfill_region(conn)

    assert updated == 1
    row = conn.execute("SELECT region FROM roms WHERE id = 'r1'").fetchone()
    assert row["region"] == "Japan"


def test_backfill_region_leaves_untaggable_rows_null_and_uncounted():
    conn = _lang_conn()
    conn.execute(
        "INSERT INTO roms (id, original_name, stored_name) VALUES (?, ?, ?)",
        ("r1", "Alpha Roid.rom", "알파 로이드.rom"),
    )
    conn.commit()

    updated = langfill.backfill_region(conn)

    assert updated == 0
    row = conn.execute("SELECT region FROM roms WHERE id = 'r1'").fetchone()
    assert row["region"] is None


def test_backfill_region_does_not_touch_already_tagged_rows():
    conn = _lang_conn()
    conn.execute(
        """INSERT INTO roms (id, original_name, stored_name, region)
           VALUES (?, ?, ?, ?)""",
        ("r1", "Sonic (USA).md", "소닉.md", "PreExisting"),
    )
    conn.commit()

    # WHERE region IS NULL excludes this row entirely.
    updated = langfill.backfill_region(conn)

    assert updated == 0
    row = conn.execute("SELECT region FROM roms WHERE id = 'r1'").fetchone()
    assert row["region"] == "PreExisting"


# =====================================================================
# name_index
# =====================================================================

def _names_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE rom_names (
            hash TEXT PRIMARY KEY, system_key TEXT NOT NULL,
            korean_name TEXT, source TEXT, original_name TEXT,
            lang TEXT NOT NULL DEFAULT 'ko'
        )"""
    )
    return conn


def test_hash_bytes_matches_hashlib():
    import hashlib
    data = b"some rom bytes"
    assert name_index.hash_bytes(data) == hashlib.sha256(data).hexdigest()


def test_hash_file_matches_hash_bytes(tmp_path):
    p = tmp_path / "game.nes"
    p.write_bytes(b"cartridge data" * 100)
    assert name_index.hash_file(p) == name_index.hash_bytes(p.read_bytes())


def test_store_then_lookup_roundtrip():
    conn = _names_conn()
    name_index.store(conn, "abc123", "nes", "콘트라")
    assert name_index.lookup(conn, "abc123") == "콘트라"


def test_lookup_missing_hash_returns_none():
    conn = _names_conn()
    assert name_index.lookup(conn, "doesnotexist") is None


def test_store_nfc_normalizes_korean_name():
    conn = _names_conn()
    decomposed = unicodedata.normalize("NFD", "콘트라")
    name_index.store(conn, "h1", "nes", decomposed)
    stored = name_index.lookup(conn, "h1")
    assert stored == unicodedata.normalize("NFC", "콘트라")


def test_lookup_by_name_matches_system_and_original_name():
    conn = _names_conn()
    name_index.store(conn, "h1", "nes", "콘트라", source="gamelist",
                      original_name="Contra (Japan).nes")
    found = name_index.lookup_by_name(conn, "nes", "Contra (Japan).nes")
    assert found == "콘트라"


def test_lookup_by_name_nfc_normalizes_the_query():
    conn = _names_conn()
    name_index.store(conn, "h1", "nes", "콘트라", original_name="Contra (Japan).nes")
    decomposed_query = unicodedata.normalize("NFD", "Contra (Japan).nes")
    assert name_index.lookup_by_name(conn, "nes", decomposed_query) == "콘트라"


def test_lookup_by_name_empty_returns_none_without_querying():
    conn = _names_conn()
    assert name_index.lookup_by_name(conn, "nes", "") is None
    assert name_index.lookup_by_name(conn, "nes", None) is None


def test_lookup_by_name_wrong_system_key_misses():
    conn = _names_conn()
    name_index.store(conn, "h1", "nes", "콘트라", original_name="Contra.nes")
    assert name_index.lookup_by_name(conn, "gb", "Contra.nes") is None


def test_lookup_by_name_respects_lang():
    conn = _names_conn()
    name_index.store(conn, "h1", "nes", "콘트라", original_name="Contra.nes")
    assert name_index.lookup_by_name(conn, "nes", "Contra.nes", lang="ja") is None
    assert name_index.lookup_by_name(conn, "nes", "Contra.nes", lang="ko") == "콘트라"


def test_lookup_by_name_excludes_null_korean_name():
    conn = _names_conn()
    conn.execute(
        "INSERT INTO rom_names (hash, system_key, korean_name, original_name, lang) "
        "VALUES ('h1', 'nes', NULL, 'Contra.nes', 'ko')"
    )
    assert name_index.lookup_by_name(conn, "nes", "Contra.nes") is None


def test_store_allows_none_source_and_original_name():
    conn = _names_conn()
    name_index.store(conn, "h1", "nes", "콘트라")
    row = conn.execute("SELECT source, original_name FROM rom_names WHERE hash='h1'").fetchone()
    assert row["source"] is None
    assert row["original_name"] is None


def test_store_replaces_existing_hash():
    conn = _names_conn()
    name_index.store(conn, "h1", "nes", "이름1")
    name_index.store(conn, "h1", "nes", "이름2")
    assert name_index.lookup(conn, "h1") == "이름2"


# =====================================================================
# name_map
# =====================================================================

_GAMELIST_XML = """<?xml version="1.0" encoding="utf-8"?>
<gameList>
    <game>
        <path>./Ball (Nintendo).zip</path>
        <name>볼 (Ball)</name>
    </game>
    <game>
        <path>./Contra (Japan).zip</path>
        <name>(K) 콘트라</name>
    </game>
</gameList>
"""

_GAMELIST_XML_SCRATCH_DUP = """<?xml version="1.0" encoding="utf-8"?>
<gameList>
    <game>
        <path>./Ball (Nintendo).zip</path>
        <name>공 (Ball) FROM SCRATCH</name>
    </game>
</gameList>
"""


@pytest.fixture
def name_map_env(tmp_path, monkeypatch):
    """Isolate name_map/gamelist's filesystem reach: a fake bundled seed dir and
    a fake library dir (whose _data/ subfolder is gamelist's scratch source)."""
    seed_gamelists = tmp_path / "seed" / "gamelists"
    seed_gamelists.mkdir(parents=True)
    (seed_gamelists / "gamelist-nes.xml").write_text(_GAMELIST_XML, encoding="utf-8")

    library_dir = tmp_path / "library"
    library_dir.mkdir()

    monkeypatch.setattr(config, "KOREAN_NAMES_DIR", tmp_path / "seed")
    monkeypatch.setattr(config, "LIBRARY_DIR", library_dir)
    monkeypatch.setattr(name_map, "MAP_PATH", tmp_path / "name_map.json")
    return tmp_path, library_dir


def test_build_index_maps_english_keys_to_korean_names(name_map_env):
    index = name_map.build_index("s1")
    assert index["nes"]["ball"] == "볼 (Ball)"
    assert index["nes"]["contra"] == "(K) 콘트라"


def test_build_index_seed_wins_over_scratch_duplicate(name_map_env, tmp_path):
    scratch = storage.scratch_dir("s1")
    scratch.mkdir(parents=True)
    (scratch / "gamelist-nes.xml").write_text(_GAMELIST_XML_SCRATCH_DUP, encoding="utf-8")

    index = name_map.build_index("s1")

    # setdefault() means the FIRST source (bundled seed) wins on a key clash.
    assert index["nes"]["ball"] == "볼 (Ball)"


def test_build_index_empty_when_no_sources(tmp_path, monkeypatch):
    empty_seed = tmp_path / "empty_seed"
    empty_seed.mkdir()
    monkeypatch.setattr(config, "KOREAN_NAMES_DIR", empty_seed)
    monkeypatch.setattr(config, "LIBRARY_DIR", tmp_path / "lib_unused")
    assert name_map.build_index("nosession") == {}


def _rom_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE roms (
            id TEXT PRIMARY KEY, session_id TEXT, system_key TEXT,
            stored_name TEXT, rom_path TEXT
        )"""
    )
    return conn


def test_build_hashes_matches_and_writes_json(name_map_env):
    _, library_dir = name_map_env
    session_id = "s1"
    root = storage.session_root(session_id)

    matched_path = root / "roms" / "nes" / "Ball (Nintendo).zip"
    matched_path.parent.mkdir(parents=True, exist_ok=True)
    matched_path.write_bytes(b"ball rom bytes")

    unmatched_path = root / "roms" / "nes" / "Totally Unknown Game.zip"
    unmatched_path.write_bytes(b"unknown rom bytes")

    conn = _rom_conn()
    conn.execute(
        "INSERT INTO roms VALUES ('id1', ?, 'nes', 'Ball (Nintendo).zip', 'roms/nes/Ball (Nintendo).zip')",
        (session_id,),
    )
    conn.execute(
        "INSERT INTO roms VALUES ('id2', ?, 'nes', 'Totally Unknown Game.zip', 'roms/nes/Totally Unknown Game.zip')",
        (session_id,),
    )
    # Row pointing at a file that was never actually written -> must be skipped.
    conn.execute(
        "INSERT INTO roms VALUES ('id3', ?, 'nes', 'Ghost.zip', 'roms/nes/Ghost.zip')",
        (session_id,),
    )
    conn.commit()

    stats = name_map.build(conn, session_id)

    assert stats["total"] == 2
    assert stats["matched"] == 1
    assert stats["systems"] == {"nes": {"total": 2, "matched": 1}}
    assert stats["path"] == str(name_map.MAP_PATH)

    on_disk = name_map.load()
    assert len(on_disk) == 2
    matched_hash = name_index.hash_file(matched_path)
    entry = on_disk[matched_hash]
    assert entry["system"] == "nes"
    assert entry["filename"] == "Ball (Nintendo).zip"
    assert entry["korean_name"] == "볼 (Ball)"
    assert entry["cover_ref"] is None


def test_load_returns_empty_dict_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(name_map, "MAP_PATH", tmp_path / "missing.json")
    assert name_map.load() == {}


def test_load_returns_empty_dict_on_malformed_json(tmp_path, monkeypatch):
    bad = tmp_path / "name_map.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(name_map, "MAP_PATH", bad)
    assert name_map.load() == {}
