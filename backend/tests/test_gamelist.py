# -*- coding: utf-8 -*-
"""services/gamelist.py — Korean-name resolution from EmulationStation-style
gamelist.xml (and 꿀렁 .ps1 bundles). Pinned behaviour:
  - English-title matching bridges the MAME-shortname gamelist <path> and the
    descriptive uploaded filename via a normalized 'English key'.
  - Korean-key matching lets an already-Korean-named file re-match a curated
    list (idempotent re-runs).
  - A malformed gamelist.xml raises rather than silently matching nothing.
  - get_sources() only re-parses when the source files actually changed.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile

import pytest

from app import config, db
from app.services import gamelist, storage


# ---------------------------------------------------------------------------
# Pure string helpers
# ---------------------------------------------------------------------------

def test_norm_lowercases_and_collapses_punctuation_and_whitespace():
    assert gamelist._norm("Contra!!  Force") == "contra force"


def test_is_matchable_requires_three_latin_letters():
    assert gamelist._is_matchable("ball") is True
    assert gamelist._is_matchable("gb") is False   # too short
    assert gamelist._is_matchable("ab1") is False  # only 2 letters


def test_is_matchable_rejects_stop_keys():
    assert gamelist._is_matchable("nes") is False
    assert gamelist._is_matchable("usa") is False


def test_english_key_extracts_paren_english_from_korean_label():
    assert gamelist._english_key("볼 (Ball)") == "ball"


def test_english_key_extracts_leading_english_before_parens():
    assert gamelist._english_key("Ball (Nintendo)") == "ball"


def test_english_key_strips_leading_k_marker():
    assert gamelist._english_key("(K) Contra") == "contra"


def test_english_key_returns_empty_when_no_latin_and_no_parens():
    """Pure-Hangul label with nothing bracketed at all -- no English key to
    extract."""
    assert gamelist._english_key("볼링") == ""


def test_has_hangul():
    assert gamelist._has_hangul("볼") is True
    assert gamelist._has_hangul("Ball") is False


def test_clean_korean_drops_leading_k_marker_keeps_english_paren():
    assert gamelist._clean_korean("(K) 볼 (Ball)") == "볼 (Ball)"


def test_clean_english_prefers_paren_when_before_part_has_no_latin():
    assert gamelist._clean_english("볼 (Ball)") == "Ball"


def test_kor_key_strips_markers_parens_and_spacing():
    assert gamelist._kor_key("(K) 슈퍼 로봇 대전 (Super Robot Wars)") == "슈퍼로봇대전"


def test_compose_name_already_korean_paren_english_passthrough():
    assert gamelist.compose_name("(K) 볼 (Ball)", "Ball") == "볼 (Ball)"


def test_compose_name_builds_korean_english_pair():
    assert gamelist.compose_name("슈퍼 마리오", "Super Mario Bros.") == "슈퍼 마리오 (Super Mario Bros.)"


def test_compose_name_falls_back_to_english_when_korean_missing():
    assert gamelist.compose_name("", "Contra") == "Contra"


def test_compose_name_skips_english_suffix_when_names_match():
    assert gamelist.compose_name("contra", "Contra") == "contra"


# ---------------------------------------------------------------------------
# parse_ps1
# ---------------------------------------------------------------------------

_PS1_SAMPLE = """
$games = @(
    @{Name='슈퍼 마리오'; TargetPattern='Super Mario Bros'; BasePattern=@('Super ?Mario', 'SMB')}
    @{Name='컨트라'; BasePattern=@('Contra')}
)
"""


def test_parse_ps1_extracts_name_target_and_patterns():
    games = gamelist.parse_ps1(_PS1_SAMPLE)

    assert len(games) == 2
    assert games[0] == {"korean": "슈퍼 마리오", "english": "Super Mario Bros",
                         "patterns": ["Super ?Mario", "SMB"]}


def test_parse_ps1_falls_back_english_to_name_when_no_target_pattern():
    games = gamelist.parse_ps1(_PS1_SAMPLE)

    assert games[1]["english"] == "컨트라"


def test_parse_ps1_ignores_blocks_missing_name_or_base_pattern():
    text = "@{TargetPattern='X'; BasePattern=@('Y')}"
    assert gamelist.parse_ps1(text) == []


# ---------------------------------------------------------------------------
# gamelist.xml parsing
# ---------------------------------------------------------------------------

_GAMELIST_XML = """<?xml version="1.0"?>
<gameList>
  <game>
    <path>./gnw_ball.zip</path>
    <name>볼 (Ball)</name>
  </game>
  <game>
    <path>./Contra.nes</path>
    <name>(K) Contra</name>
  </game>
  <game>
    <path></path>
    <name></name>
  </game>
</gameList>
"""


def test_parse_games_skips_entries_without_a_name(tmp_path):
    p = tmp_path / "gamelist.xml"
    p.write_text(_GAMELIST_XML, encoding="utf-8")

    games = gamelist.parse_games(p)

    assert len(games) == 2
    assert games[0]["name"] == "볼 (Ball)"
    assert games[0]["folder"] == ""  # single path segment -> no folder


def test_parse_games_extracts_folder_from_nested_path():
    root = ET.fromstring(
        "<gameList><game><path>./gnw/gnw_ball.zip</path><name>Ball</name></game></gameList>"
    )
    games = gamelist._games_from_root(root)
    assert games[0]["folder"] == "gnw"


def test_parse_games_raises_on_malformed_xml(tmp_path):
    p = tmp_path / "bad.xml"
    p.write_text("<gameList><game>", encoding="utf-8")

    with pytest.raises(ET.ParseError):
        gamelist.parse_games(p)


def test_gamelist_keys_from_name_and_path_leaf():
    keys = gamelist._gamelist_keys("볼 (Ball)", "./gnw/gnw_ball.zip")
    assert keys == {"ball"}  # 'gnw_ball' leaf is skipped (MAME-code prefix)


def test_gamelist_keys_uses_path_leaf_when_not_a_mame_code():
    keys = gamelist._gamelist_keys("(K) Contra", "./roms/Contra.nes")
    assert keys == {"contra"}


# ---------------------------------------------------------------------------
# system_from_filename / infer_system
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename,expected", [
    ("gamelist-gb.xml", "gb"),
    ("gamelist-megadrive.xml", "md"),
    ("gamelist-ngpc.xml", "ngp"),
    ("gamelist-unknown-system.xml", None),
])
def test_system_from_filename(filename, expected):
    assert gamelist.system_from_filename(filename) == expected


def test_infer_system_picks_most_common_folder():
    games = [{"folder": "nes"}, {"folder": "nes"}, {"folder": "gb"}]
    assert gamelist.infer_system(games) == "nes"


def test_infer_system_returns_none_when_no_folder_maps():
    assert gamelist.infer_system([{"folder": "totally-unknown"}]) is None


# ---------------------------------------------------------------------------
# load_games: bare .xml vs .zip archive
# ---------------------------------------------------------------------------

def test_load_games_bare_xml_has_empty_regex(tmp_path):
    p = tmp_path / "gamelist.xml"
    p.write_text(_GAMELIST_XML, encoding="utf-8")

    loaded = gamelist.load_games(p)

    assert loaded["regex"] == []
    assert len(loaded["key"]) == 2


def test_load_games_zip_archive_merges_ps1_and_gamelist(tmp_path):
    zpath = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("patched_list.ps1", _PS1_SAMPLE)
        zf.writestr("gamelist.xml", _GAMELIST_XML)

    loaded = gamelist.load_games(zpath)

    assert len(loaded["regex"]) == 2
    assert len(loaded["key"]) == 2


def test_load_games_zip_with_malformed_gamelist_keeps_regex_only(tmp_path):
    zpath = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("list.ps1", _PS1_SAMPLE)
        zf.writestr("gamelist.xml", "<gameList><game>")  # malformed

    loaded = gamelist.load_games(zpath)

    assert len(loaded["regex"]) == 2
    assert loaded["key"] == []


def test_load_games_zip_prefers_patched_ps1_ordering(tmp_path):
    """Sorted so a '*patched*' ps1 is parsed first (its entries win in dict
    setdefault-based indexing)."""
    zpath = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("z_other.ps1", "$games = @(@{Name='second'; BasePattern=@('X')})")
        zf.writestr("a_patched.ps1", "$games = @(@{Name='first'; BasePattern=@('X')})")

    loaded = gamelist.load_games(zpath)

    assert loaded["regex"][0]["korean"] == "first"


def test_load_games_unrecognized_suffix_is_still_parsed_as_xml(tmp_path):
    """Only .zip/.7z get archive handling; any other suffix (including no
    suffix at all) falls through to the plain gamelist.xml parser."""
    p = tmp_path / "list.dat"
    p.write_text(_GAMELIST_XML, encoding="utf-8")

    loaded = gamelist.load_games(p)

    assert loaded["regex"] == []
    assert len(loaded["key"]) == 2


def test_load_games_zip_skips_ps1_that_fails_to_parse(tmp_path, monkeypatch):
    """One malformed .ps1 in a bundle must not sink the others."""
    zpath = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a_bad.ps1", _PS1_SAMPLE)
        zf.writestr("z_good.ps1", _PS1_SAMPLE)

    real_parse_ps1 = gamelist.parse_ps1
    calls = {"n": 0}

    def flaky_parse_ps1(text):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("corrupt ps1")
        return real_parse_ps1(text)

    monkeypatch.setattr(gamelist, "parse_ps1", flaky_parse_ps1)

    loaded = gamelist.load_games(zpath)

    assert len(loaded["regex"]) == 2  # only the second (good) file's entries


# ---------------------------------------------------------------------------
# resolve_with_sources / _resolve
# ---------------------------------------------------------------------------

def test_resolve_with_sources_matches_by_english_key():
    by_eng = {}
    by_kor = {}
    gamelist._index_keygames([{"name": "볼 (Ball)", "path": "./gnw_ball.zip"}], by_eng, by_kor)

    result = gamelist.resolve_with_sources([], by_eng, by_kor, "Ball (Nintendo).gw")

    assert result == "볼 (Ball)"


def test_resolve_with_sources_matches_by_korean_key_idempotent():
    """A file already renamed to 'Korean (English)' must still re-match the
    same source (idempotent re-run of the importer)."""
    by_eng, by_kor = {}, {}
    gamelist._index_keygames([{"name": "볼 (Ball)", "path": "./gnw_ball.zip"}], by_eng, by_kor)

    result = gamelist.resolve_with_sources([], by_eng, by_kor, "볼 (Ball).gw")

    assert result == "볼 (Ball)"


def test_resolve_with_sources_regex_pattern_beats_nothing():
    regex_games = [{"korean": "컨트라", "english": "Contra", "patterns": ["Contra"]}]
    result = gamelist.resolve_with_sources(regex_games, {}, {}, "Contra (USA).nes")
    assert result == "컨트라 (Contra)"


def test_resolve_with_sources_prefers_hangul_candidate_over_english_only():
    """Even if an earlier candidate source matched without Hangul, a Hangul
    candidate from another source must win."""
    regex_games = [{"korean": "EnglishOnlyName", "english": "EnglishOnlyName",
                    "patterns": ["Contra"]}]
    by_eng = {}
    gamelist._index_keygames([{"name": "컨트라 (Contra)", "path": "./Contra.nes"}], by_eng, {})

    result = gamelist.resolve_with_sources(regex_games, by_eng, {}, "Contra (USA).nes")

    assert result == "컨트라 (Contra)"


def test_resolve_with_sources_no_match_returns_none():
    assert gamelist.resolve_with_sources([], {}, {}, "TotallyUnknownGame.nes") is None


def test_resolve_with_sources_strips_extension_before_matching():
    by_eng, by_kor = {}, {}
    gamelist._index_keygames([{"name": "볼 (Ball)", "path": "./gnw_ball.zip"}], by_eng, by_kor)
    assert gamelist.resolve_with_sources([], by_eng, by_kor, "Ball") == "볼 (Ball)"


# ---------------------------------------------------------------------------
# source_files / gamelist_xmls / _data_signature / get_sources caching
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_and_scratch(tmp_path, monkeypatch):
    """Isolated Korean-names seed dir (bundled source-of-truth) + a session
    scratch dir (user-uploaded lists), matching source_files()'s two roots."""
    seed_gamelists = tmp_path / "seed" / "gamelists"
    seed_gamelists.mkdir(parents=True)
    monkeypatch.setattr(config, "KOREAN_NAMES_DIR", tmp_path / "seed")
    monkeypatch.setattr(config, "LIBRARY_DIR", tmp_path / "library")
    gamelist._SOURCE_CACHE.clear()
    yield seed_gamelists, config.SHARED_SESSION_ID
    gamelist._SOURCE_CACHE.clear()


def test_source_files_combines_seed_and_scratch_xml_only(seed_and_scratch):
    seed_dir, sid = seed_and_scratch
    (seed_dir / "gamelist-nes.xml").write_text(_GAMELIST_XML, encoding="utf-8")
    (seed_dir / "notes.txt").write_text("ignored", encoding="utf-8")
    scratch = storage.scratch_dir(sid)
    scratch.mkdir(parents=True)
    (scratch / "gamelist-gb.xml").write_text(_GAMELIST_XML, encoding="utf-8")

    files = gamelist.source_files(sid)

    names = sorted(f.name for f in files)
    assert names == ["gamelist-gb.xml", "gamelist-nes.xml"]


def test_gamelist_xmls_filters_to_gamelist_prefixed_xml(seed_and_scratch):
    seed_dir, sid = seed_and_scratch
    (seed_dir / "gamelist-nes.xml").write_text(_GAMELIST_XML, encoding="utf-8")
    (seed_dir / "other.xml").write_text(_GAMELIST_XML, encoding="utf-8")

    files = gamelist.gamelist_xmls(sid)

    assert [f.name for f in files] == ["gamelist-nes.xml"]


def test_get_sources_caches_until_source_signature_changes(seed_and_scratch, monkeypatch):
    seed_dir, sid = seed_and_scratch
    p = seed_dir / "gamelist-nes.xml"
    p.write_text(_GAMELIST_XML, encoding="utf-8")

    calls = {"n": 0}
    real_build = gamelist.build_sources_for_system

    def counting_build(session_id, system):
        calls["n"] += 1
        return real_build(session_id, system)

    monkeypatch.setattr(gamelist, "build_sources_for_system", counting_build)

    gamelist.get_sources(sid, "nes")
    gamelist.get_sources(sid, "nes")  # unchanged signature -> cache hit

    assert calls["n"] == 1

    import os
    # _data_signature truncates st_mtime to whole seconds; bump it forward
    # without a real sleep so the fingerprint is guaranteed to change.
    bumped = p.stat().st_mtime + 2
    os.utime(p, (bumped, bumped))

    gamelist.get_sources(sid, "nes")  # signature changed -> re-parsed

    assert calls["n"] == 2


def test_build_sources_for_system_scopes_to_requested_system(seed_and_scratch):
    seed_dir, sid = seed_and_scratch
    (seed_dir / "gamelist-nes.xml").write_text(_GAMELIST_XML, encoding="utf-8")

    regex, by_eng, by_kor = gamelist.build_sources_for_system(sid, "gb")

    assert regex == [] and by_eng == {} and by_kor == {}  # nes list, gb requested


def test_build_sources_for_system_infers_system_from_content_when_filename_unknown(seed_and_scratch):
    """A gamelist file whose name gives no system hint still resolves via the
    folder majority inside its own <path> entries."""
    seed_dir, sid = seed_and_scratch
    (seed_dir / "custom_list.xml").write_text(
        "<gameList>"
        "<game><path>./nes/Foo.zip</path><name>Foo</name></game>"
        "<game><path>./nes/Bar.zip</path><name>Bar</name></game>"
        "</gameList>",
        encoding="utf-8",
    )

    regex, by_eng, by_kor = gamelist.build_sources_for_system(sid, "nes")

    assert by_eng  # content-inferred as 'nes' and indexed


def test_build_sources_for_system_skips_unparseable_file(seed_and_scratch):
    seed_dir, sid = seed_and_scratch
    (seed_dir / "gamelist-nes.xml").write_text("<gameList><game>", encoding="utf-8")

    regex, by_eng, by_kor = gamelist.build_sources_for_system(sid, "nes")

    assert regex == [] and by_eng == {} and by_kor == {}


# ---------------------------------------------------------------------------
# build_plan (needs a DB with roms rows)
# ---------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gnw.db")
    monkeypatch.setattr(config, "TMP_DIR", tmp_path / "tmp")
    db.init_db()
    with db.connect() as c:
        yield c


def _insert_rom(conn, rom_id, system_key, stored_name):
    conn.execute(
        "INSERT INTO roms (id, session_id, system_key, original_name, stored_name, rom_path) "
        "VALUES (?,?,?,?,?,?)",
        (rom_id, config.SHARED_SESSION_ID, system_key, stored_name, stored_name,
         f"roms/{system_key}/{stored_name}"),
    )


def test_build_plan_matches_and_renames_within_target_system(conn, tmp_path):
    sid = config.SHARED_SESSION_ID
    _insert_rom(conn, "r1", "gw", "Ball (Nintendo).gw")
    _insert_rom(conn, "r2", "nes", "SomeGame.nes")  # different system, ignored
    source = tmp_path / "gamelist.xml"
    source.write_text(_GAMELIST_XML, encoding="utf-8")

    result = gamelist.build_plan(conn, sid, source, "gw")

    assert result["system"] == "gw"
    assert len(result["plan"]) == 1
    item = result["plan"][0]
    assert item["rom_id"] == "r1"
    assert item["old"] == "Ball (Nintendo).gw"
    assert item["new"] == "볼 (Ball).gw"


def test_build_plan_infers_system_when_not_given(conn, tmp_path):
    sid = config.SHARED_SESSION_ID
    _insert_rom(conn, "r1", "gw", "Ball (Nintendo).gw")
    source = tmp_path / "gamelist.xml"
    # both games map to the 'gnw' folder -> infer_system picks 'gw'
    source.write_text(
        "<gameList>"
        "<game><path>./gnw/gnw_ball.zip</path><name>볼 (Ball)</name></game>"
        "<game><path>./gnw/gnw_other.zip</path><name>다른 (Other)</name></game>"
        "</gameList>",
        encoding="utf-8",
    )

    result = gamelist.build_plan(conn, sid, source, system=None)

    assert result["system"] == "gw"
    assert result["plan"][0]["new"] == "볼 (Ball).gw"


def test_build_plan_skips_roms_already_at_the_resolved_name(conn, tmp_path):
    sid = config.SHARED_SESSION_ID
    _insert_rom(conn, "r1", "gw", "볼 (Ball).gw")  # already renamed
    source = tmp_path / "gamelist.xml"
    source.write_text(_GAMELIST_XML, encoding="utf-8")

    result = gamelist.build_plan(conn, sid, source, "gw")

    assert result["plan"] == []


def test_build_plan_no_extension_stored_name(conn, tmp_path):
    """stored_name with no '.' must not crash the ext-split logic."""
    sid = config.SHARED_SESSION_ID
    _insert_rom(conn, "r1", "gw", "Ball (Nintendo)")  # no extension at all
    source = tmp_path / "gamelist.xml"
    source.write_text(_GAMELIST_XML, encoding="utf-8")

    result = gamelist.build_plan(conn, sid, source, "gw")

    assert result["plan"][0]["new"] == "볼 (Ball)"


def test_build_plan_scans_all_systems_when_none_can_be_inferred(conn, tmp_path):
    """No system passed AND the source's <path> folders don't map to any known
    system -> falls back to scanning every rom in the session."""
    sid = config.SHARED_SESSION_ID
    _insert_rom(conn, "r1", "gw", "Ball (Nintendo).gw")
    _insert_rom(conn, "r2", "nes", "TotallyUnrelated.nes")  # never matches, exercises the skip path
    source = tmp_path / "gamelist.xml"
    source.write_text(
        "<gameList><game><path>./unknownfolder/gnw_ball.zip</path>"
        "<name>볼 (Ball)</name></game></gameList>",
        encoding="utf-8",
    )

    result = gamelist.build_plan(conn, sid, source, system=None)

    assert result["system"] is None
    assert len(result["plan"]) == 1
    assert result["plan"][0]["rom_id"] == "r1"  # r2 was scanned too but unmatched -> skipped


def test_build_plan_raises_on_malformed_source(conn, tmp_path):
    sid = config.SHARED_SESSION_ID
    source = tmp_path / "gamelist.xml"
    source.write_text("<gameList><game>", encoding="utf-8")

    with pytest.raises(ET.ParseError):
        gamelist.build_plan(conn, sid, source, "gw")


def test_load_games_reads_a_real_7z_bundle(tmp_path):
    # py7zr dropped readall() in 1.x, so _read_archive extracts instead. Build a
    # genuine .7z (not a mock) — the old code raised AttributeError here, and the
    # callers' broad `except Exception` turned that into a silent "0 matched".
    py7zr = pytest.importorskip("py7zr")
    xml = tmp_path / "gamelist.xml"
    xml.write_text(
        "<gameList><game><name>테스트 게임</name><path>./a.gb</path></game></gameList>",
        encoding="utf-8",
    )
    archive = tmp_path / "bundle.7z"
    with py7zr.SevenZipFile(archive, "w") as z:
        z.write(xml, "gamelist.xml")

    games = gamelist.load_games(archive)["key"]

    assert [g["name"] for g in games] == ["테스트 게임"]
