# -*- coding: utf-8 -*-
"""config._env / _env_int — the "set but empty" case.

docker-compose forwards every optional knob as `${VAR:-}`, so a user who has not set
one hands the container an EMPTY STRING rather than nothing at all. That is the whole
reason these helpers exist: before them, `int("")` would have taken the app down at
import the moment the compose file started passing the byte caps through.

Pins that empty means "not configured", that a malformed value falls back instead of
crashing, and that a real value still wins.
"""
import importlib

import pytest

from app import config


@pytest.fixture
def env(monkeypatch):
    """Set a var to an exact value (including empty) and return config's readers."""
    def _set(name, value):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    return _set


# --- _env (strings) -----------------------------------------------------

def test_unset_falls_back(env):
    env("GNW_TEST_KNOB", None)
    assert config._env("GNW_TEST_KNOB", "fallback") == "fallback"


def test_empty_string_is_not_configured(env):
    """The compose case: `${VAR:-}` with nothing set."""
    env("GNW_TEST_KNOB", "")
    assert config._env("GNW_TEST_KNOB", "fallback") == "fallback"


def test_whitespace_only_is_not_configured(env):
    env("GNW_TEST_KNOB", "   ")
    assert config._env("GNW_TEST_KNOB", "fallback") == "fallback"


def test_a_real_value_wins_and_is_stripped(env):
    env("GNW_TEST_KNOB", "  https://example.com  ")
    assert config._env("GNW_TEST_KNOB", "fallback") == "https://example.com"


# --- _env_int (byte caps) -----------------------------------------------

def test_empty_int_falls_back_instead_of_raising(env):
    """Before this, an empty value reached int("") and killed the import."""
    env("GNW_TEST_BYTES", "")
    assert config._env_int("GNW_TEST_BYTES", 1234) == 1234


def test_malformed_int_falls_back(env):
    """A typo in a compose file must not stop the server booting on an optional knob."""
    env("GNW_TEST_BYTES", "64MB")
    assert config._env_int("GNW_TEST_BYTES", 1234) == 1234


def test_a_real_int_wins(env):
    env("GNW_TEST_BYTES", "999")
    assert config._env_int("GNW_TEST_BYTES", 1234) == 999


# --- the module actually imports under compose's empty-string world -----

def test_config_imports_with_every_knob_empty(monkeypatch):
    """The regression this guards: compose now forwards ten byte caps as `${VAR:-}`.
    If any one of them still went through a bare int(), importing config with them all
    empty — the default state for a user with no .env — would raise ValueError and the
    container would not start."""
    for name in ("GNW_CORS_ORIGINS", "GNW_MAX_ROM_BYTES", "GNW_MAX_VIDEO_BYTES",
                 "GNW_MAX_MUSIC_BYTES", "GNW_MAX_FIRMWARE_BYTES", "GNW_MAX_EXTRA_BYTES",
                 "GNW_MAX_CD_FILE_BYTES", "GNW_MAX_CD_TOTAL_BYTES",
                 "GNW_MAX_CHUNK_BYTES", "GNW_MAX_UPLOAD_TOTAL_BYTES",
                 "GNW_API_PORT", "GNW_FRONTEND_PORT", "GNW_DATA_DIR"):
        monkeypatch.setenv(name, "")

    reloaded = importlib.reload(config)
    try:
        assert reloaded.MAX_ROM_BYTES == 64 * 1024 * 1024
        assert reloaded.MAX_CD_FILE_BYTES == 1024 * 1024 * 1024
        assert reloaded.CORS_ORIGINS == ["*"]
        assert reloaded.API_PORT == 38080
    finally:
        # Other tests monkeypatch this module's paths; hand back the real one.
        importlib.reload(config)
