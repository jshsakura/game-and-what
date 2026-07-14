# -*- coding: utf-8 -*-
"""The shareable dataset: what it carries, and what it must never carry.

The dictionary is the project's real work — 1,900 Korean names — and it is meant to be
handed out. The whole safety argument is that `rom_names` is keyed by the sha256 of a
rom's CONTENTS and holds nothing about my library. These tests pin that: if someone adds
a column to rom_names later, `test_export_leaks_nothing_personal` is what fails.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from app.services import dataset


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        """CREATE TABLE rom_names (
               hash TEXT PRIMARY KEY, system_key TEXT NOT NULL, korean_name TEXT NOT NULL,
               source TEXT, created_at TEXT DEFAULT (datetime('now')),
               lang TEXT NOT NULL DEFAULT 'ko', original_name TEXT)"""
    )
    return c


def add(conn, h, system="nes", name="별의 커비", source="꿀렁", original="Kirby.nes"):
    conn.execute(
        "INSERT INTO rom_names (hash, system_key, korean_name, source, lang, original_name)"
        " VALUES (?, ?, ?, ?, 'ko', ?)", (h, system, name, source, original))


def test_export_carries_the_name_and_its_provenance(conn):
    add(conn, "a" * 64)
    out = dataset.export_names(conn)

    assert out["count"] == 1
    row = out["names"][0]
    assert row["hash"] == "a" * 64
    assert row["name"] == "별의 커비"
    assert row["system"] == "nes"
    # source travels with the row: a shared file says where each name came from.
    assert row["source"] == "꿀렁"


def test_export_leaks_nothing_personal(conn):
    """The row shape IS the privacy guarantee — no paths, no session, no timestamps."""
    add(conn, "b" * 64)
    row = dataset.export_names(conn)["names"][0]

    assert set(row) == {"hash", "system", "name", "original_name", "source"}
    blob = json.dumps(dataset.export_names(conn), ensure_ascii=False)
    for leak in ("session", "rom_path", "stored_name", "created_at", "favorite", "/home/"):
        assert leak not in blob


def test_export_is_sorted_so_a_reexport_diffs_cleanly(conn):
    add(conn, "f" * 64, system="nes")
    add(conn, "a" * 64, system="msx")
    add(conn, "c" * 64, system="msx")

    got = [(r["system"], r["hash"]) for r in dataset.export_names(conn)["names"]]
    assert got == sorted(got)


def test_import_never_overwrites_a_local_name(conn):
    """A name I fixed by hand outranks anything a shared file says. Merges are additive."""
    add(conn, "a" * 64, name="내가 고친 이름", source="manual")
    payload = {"format": 1, "lang": "ko", "names": [
        {"hash": "a" * 64, "system": "nes", "name": "파일이 주장하는 이름", "source": "list"},
        {"hash": "b" * 64, "system": "nes", "name": "새 이름", "source": "list"},
    ]}

    added, skipped = dataset.import_names(conn, payload)

    assert (added, skipped) == (1, 1)
    kept = conn.execute("SELECT korean_name FROM rom_names WHERE hash = ?",
                        ("a" * 64,)).fetchone()["korean_name"]
    assert kept == "내가 고친 이름"


def test_import_is_idempotent(conn):
    payload = {"format": 1, "lang": "ko", "names": [
        {"hash": "a" * 64, "system": "nes", "name": "이름", "source": "list"}]}

    assert dataset.import_names(conn, payload) == (1, 0)
    assert dataset.import_names(conn, payload) == (0, 1)


def test_import_skips_a_row_missing_its_key(conn):
    payload = {"format": 1, "lang": "ko", "names": [
        {"system": "nes", "name": "해시 없음"},
        {"hash": "a" * 64, "name": "시스템 없음"},
        {"hash": "b" * 64, "system": "nes", "name": "정상"},
    ]}

    added, skipped = dataset.import_names(conn, payload)

    assert (added, skipped) == (1, 2)


def test_import_refuses_an_unknown_format(conn):
    with pytest.raises(ValueError, match="format"):
        dataset.import_names(conn, {"format": 99, "names": []})


def test_the_shipped_seed_is_the_shape_the_importer_expects():
    """The file in the repo is the one a fresh Korean install boots from. If it ever
    stops matching, an install silently starts with no dictionary at all."""
    payload = json.loads(dataset.SEED_PATH.read_text(encoding="utf-8"))

    assert payload["format"] == dataset.FORMAT
    assert payload["lang"] == "ko"
    assert payload["count"] == len(payload["names"]) > 1000
    for row in payload["names"]:
        assert set(row) <= {"hash", "system", "name", "original_name", "source"}
        assert len(row["hash"]) == 64
