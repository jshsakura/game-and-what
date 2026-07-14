# -*- coding: utf-8 -*-
"""The shared table: what may be written into it, and what may be read back out as shippable.

A row here becomes an entry in a device's firmware table, so the gate is not a formality.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gbaidle import rom, table   # noqa: E402


def test_only_a_run_verified_row_hands_out_its_address():
    """verify_tier R = the game was RUN and the address demonstrably works. An address
    that was guessed and never executed is worse than none: gpSP would end the frame slice
    at somewhere that is not the wait loop."""
    proven = {"game_code": "AKRJ", "idle_verified": "0x8000422", "verify_tier": "R"}
    guessed = {"game_code": "BPYP", "idle_verified": "0x808fff6", "verify_tier": "B"}

    assert table.shippable_pc(proven) == "0x8000422"
    assert table.shippable_pc(guessed) is None


def test_a_hunted_row_records_that_we_looked():
    """Without idle_hunted, a game with no address and a full frame of work is ambiguous,
    and the UI has to assume the kind reading ("not measured"). For a game we DID hunt,
    that hides a real verdict: the Classic NES carts have no wait loop because they spend
    the frame emulating a NES."""
    row = table.row_for("FDKE", name="Classic NES - Donkey Kong", exec_cycles=227722,
                        idle_pc=None, idle_drop=None, how="hunt: no wait loop exists")

    assert row["idle_hunted"] is True
    assert row["has_idle"] is False
    assert "verify_tier" not in row          # nothing to ship
    assert table.shippable_pc(row) is None


def test_a_found_row_carries_the_address_and_what_it_bought():
    row = table.row_for("AMZE", name="Super Mario Advance", exec_cycles=89918,
                        idle_pc="0x8001cfc", idle_drop=0.679, how="hunt: histogram + A/B")

    assert row["verify_tier"] == "R"
    assert table.shippable_pc(row) == "0x8001cfc"
    assert row["idle_drop"] == 0.679


def test_upsert_replaces_a_game_rather_than_duplicating_it():
    rows = [{"game_code": "AKRJ", "exec_median": 1}]

    once = table.upsert(rows, "AKRJ", exec_median=2)
    twice = table.upsert(once, "AMZE", exec_median=3)

    assert [r["game_code"] for r in twice] == ["AKRJ", "AMZE"]
    assert twice[0]["exec_median"] == 2
    assert rows[0]["exec_median"] == 1      # the input was not mutated


def test_an_unreadable_table_degrades_instead_of_exploding(tmp_path):
    """A missing table must mean 'measure it yourself', not a dead app."""
    assert table.load(tmp_path / "nope.json") == {}


def test_round_trip(tmp_path):
    path = tmp_path / "db.json"
    table.save([table.row_for("AKRJ", name="쿠루쿠루쿠루링", exec_cycles=71724,
                              idle_pc="0x8000422", idle_drop=0.743, how="t")], path)

    back = table.load(path)

    assert back["AKRJ"]["lib_name"] == "쿠루쿠루쿠루링"      # utf-8 survives the trip
    assert json.loads(path.read_text(encoding="utf-8"))[0]["idle_verified"] == "0x8000422"


class TestRomHeader:
    """Match on the header, never the filename. This has produced a wrong-but-passing
    address twice — a renamed library A/B'd F-Zero Climax's address against another rom."""

    def _rom(self, tmp_path, code=b"AKRJ", fixed=0x96):
        data = bytearray(0xC0)
        data[0xAC:0xB0] = code
        data[0xB2] = fixed
        path = tmp_path / "anything at all.gba"
        path.write_bytes(bytes(data))
        return path

    def test_the_code_comes_from_the_header_not_the_name(self, tmp_path):
        assert rom.game_code(self._rom(tmp_path)) == "AKRJ"

    def test_a_file_that_is_not_a_gba_rom_is_rejected(self, tmp_path):
        assert rom.game_code(self._rom(tmp_path, fixed=0x00)) is None

    def test_a_missing_file_is_not_an_exception(self, tmp_path):
        assert rom.game_code(tmp_path / "gone.gba") is None

    def test_regions_a_loop_can_live_in(self):
        # An emulator-cart (Classic NES) copies its core into IWRAM and waits THERE.
        assert rom.region_of(0x8001cfc) == "ROM"
        assert rom.region_of(0x3004a1c) == "IWRAM"
        assert rom.region_of(0x20314a6) == "EWRAM"
