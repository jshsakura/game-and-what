# -*- coding: utf-8 -*-
"""patchver.parse() — sortable "YYYY-MM-DD vX.Y" descriptor from a Korean-patch
filename tag. Pins the date-wins-over-version priority, the strict 8-digit date
validation (month/day range), the dotted-version requirement (to avoid dates
being mistaken for versions), and the 'proto' pre-release fallback."""
from app.services import patchver


# --- None / empty input -------------------------------------------------

def test_none_returns_none():
    assert patchver.parse(None) is None


def test_empty_string_returns_none():
    assert patchver.parse("") is None


def test_plain_name_with_no_tag_returns_none():
    assert patchver.parse("Super Mario Bros.nes") is None


# --- date + version combined --------------------------------------------

def test_date_and_version_combined():
    name = "Some Game (Korea-patch J-K v20231026 v1.0).nes"
    assert patchver.parse(name) == "2023-10-26 v1.0"


def test_date_and_version_combined_e_to_k():
    name = "Some Game (Korea-patch E-K v20181226 v4.0).nes"
    assert patchver.parse(name) == "2018-12-26 v4.0"


# --- date only ------------------------------------------------------------

def test_date_only_no_v_prefix_no_version():
    name = "Some Game (Korea-patch J-K 20120124).nes"
    assert patchver.parse(name) == "2012-01-24"


def test_date_only_v_prefixed():
    name = "Some Game (Korea-patch J-K v20120124).nes"
    assert patchver.parse(name) == "2012-01-24"


# --- version only -----------------------------------------------------------

def test_version_only_no_date():
    assert patchver.parse("Some Game (K-v1.2).nes") == "v1.2"


def test_version_with_letter_suffix():
    assert patchver.parse("Some Game (K-v1.1a).nes") == "v1.1a"


def test_bare_version_without_dot_is_not_a_version():
    # _VER requires a dotted number, so 'v10' alone must not be picked up.
    assert patchver.parse("Some Game (K-v10).nes") is None


# --- proto / pre-release ----------------------------------------------------

def test_proto_tag_alone():
    assert patchver.parse("Some Game (Korea-patch J-K ver.proto).nes") == "proto"


def test_bare_proto_word():
    assert patchver.parse("Some Game (proto build).nes") == "proto"


def test_proto_ignored_when_version_present():
    # ver is found via _VER first, so the proto fallback never runs.
    assert patchver.parse("Some Game (K-v1.0 proto).nes") == "v1.0"


# --- date validity range -----------------------------------------------------

def test_invalid_month_is_rejected():
    # month '13' is out of range -> not a valid date -> no date component
    assert patchver.parse("Some Game (Korea-patch J-K 20231399).nes") is None


def test_invalid_day_is_rejected():
    assert patchver.parse("Some Game (Korea-patch J-K 20230132).nes") is None


def test_year_before_1980_is_rejected():
    assert patchver.parse("Some Game (Korea-patch J-K 19791026).nes") is None


def test_year_after_2099_is_rejected():
    assert patchver.parse("Some Game (Korea-patch J-K 21000101).nes") is None


def test_skips_invalid_date_and_picks_next_valid_one():
    # First 8-digit run is an invalid date (month 13); the loop must not stop
    # there and should keep scanning for a valid one.
    name = "Some Game (20231399) (Korea-patch J-K v20200101 v1.0).nes"
    assert patchver.parse(name) == "2020-01-01 v1.0"


def test_boundary_dates_are_valid():
    assert patchver.parse("Game (19800101).nes") == "1980-01-01"
    assert patchver.parse("Game (20991231).nes") == "2099-12-31"


# --- unicode / garbage safety ------------------------------------------------

def test_korean_filename_without_tag_returns_none():
    assert patchver.parse("한글 게임 이름.nes") is None


def test_garbage_digits_shorter_than_8_ignored():
    assert patchver.parse("Some Game (v2023).nes") is None
