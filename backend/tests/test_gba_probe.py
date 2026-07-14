"""The GBA prober: look a rom up, and only run it when we have never seen it."""
import asyncio
from pathlib import Path

import pytest

from app.services import gba_probe


def _fake_rom(tmp_path: Path, code: str, *, magic: int = 0x96) -> Path:
    """A file with a GBA cart header and nothing else."""
    header = bytearray(0xC0)
    header[0xAC:0xB0] = code.encode()
    header[0xB2] = magic
    path = tmp_path / f"{code}.gba"
    path.write_bytes(bytes(header) + b"\x00" * 64)
    return path


def test_game_code_reads_the_header(tmp_path):
    assert gba_probe.game_code(_fake_rom(tmp_path, "BPEE")) == "BPEE"


def test_game_code_rejects_a_file_that_is_not_a_gba_rom(tmp_path):
    # e-Reader cards carry a .gba extension but no cart header; so does any stray file.
    assert gba_probe.game_code(_fake_rom(tmp_path, "BPEE", magic=0x00)) is None
    empty = tmp_path / "empty.gba"
    empty.write_bytes(b"")
    assert gba_probe.game_code(empty) is None


def test_lookup_returns_a_measured_game():
    # Pokémon Emerald (Korean release). Measured by running it — see scripts/idlefind.
    hit = gba_probe.lookup("BPEK")
    assert hit is not None
    assert hit.idle_pc == "0x80008ce"
    assert 0 < hit.exec_cycles < gba_probe.FRAME_CYCLES
    assert hit.source == "db"


def test_lookup_reports_no_idle_loop_for_a_game_that_halts():
    # Pokémon Ruby waits via the BIOS instead of spinning, so there is no loop to skip
    # — but it IS measured, and it is not slow.
    hit = gba_probe.lookup("AXVK")
    assert hit is not None
    assert hit.idle_pc is None
    assert hit.exec_cycles < gba_probe.FRAME_CYCLES


def test_lookup_misses_an_unknown_game():
    assert gba_probe.lookup("ZZZZ") is None


def test_probe_prefers_the_database_over_running_the_game(tmp_path, monkeypatch):
    ran = False

    async def _must_not_run(_rom):
        nonlocal ran
        ran = True
        return None

    monkeypatch.setattr(gba_probe, "measure", _must_not_run)
    result = asyncio.run(gba_probe.probe(_fake_rom(tmp_path, "BPEK")))

    assert result is not None and result.source == "db"
    assert not ran, "a rom we have already measured must not be run again"


def test_probe_falls_back_to_running_an_unknown_game(tmp_path, monkeypatch):
    async def _measured(_rom):
        return gba_probe.Probe("ZZZZ", "0x8000100", 50_000, "measured")

    monkeypatch.setattr(gba_probe, "measure", _measured)
    result = asyncio.run(gba_probe.probe(_fake_rom(tmp_path, "ZZZZ")))

    assert result is not None and result.source == "measured"


def test_probe_gives_up_quietly_on_a_file_that_is_not_a_rom(tmp_path):
    assert asyncio.run(gba_probe.probe(_fake_rom(tmp_path, "BPEK", magic=0))) is None


@pytest.mark.skipif(not gba_probe._runner.available(),
                    reason="idlefind is not in this build")
def test_measure_needs_a_real_rom(tmp_path):
    # A header with no code behind it cannot boot: the prober must return None rather
    # than leave the caller with a rom stuck 'pending'.
    assert asyncio.run(gba_probe.measure(_fake_rom(tmp_path, "ZZZZ"))) is None


def test_measure_is_skipped_when_the_tool_is_not_installed(tmp_path, monkeypatch):
    """A dev checkout has no binary. Lookup must still work and measurement must decline
    quietly — never crash, and never leave a rom stuck 'pending'."""
    monkeypatch.setattr(gba_probe._runner, "available", lambda: False)

    assert asyncio.run(gba_probe.measure(_fake_rom(tmp_path, "ZZZZ"))) is None


def test_the_prober_owns_no_rules_of_its_own():
    """The rules live in ONE place (scripts/idlefind/gbaidle/verify.py) and this module is
    an adapter over them. It used to keep its own copy — and its copy had no A/B at all, so
    an upload could write an address mGBA merely *detected* into the shared table, which is
    exactly what 22 of 111 detections turned out not to deserve."""
    import inspect

    src = inspect.getsource(gba_probe)

    for smell in ("MIN_DROP", "0.15", "SAME_SCREENS", "capstone", "_BRANCHES"):
        assert smell not in src, f"{smell} is a rule; it belongs in gbaidle.verify"


def test_a_hunted_rom_with_no_loop_is_reported_as_hunted(tmp_path, monkeypatch):
    """The distinction the old prober could not make. A full frame of work with `hunted`
    set is the GAME's answer ('it works the whole frame'), not ours ('we failed to find
    its loop') — and the UI must stop calling it 'not measured'."""
    monkeypatch.setattr(gba_probe._runner, "available", lambda: True)
    monkeypatch.setattr(gba_probe._hunt, "find", lambda _p: (None, 227722))

    result = asyncio.run(gba_probe.measure(_fake_rom(tmp_path, "FDKE")))

    assert result is not None
    assert result.idle_pc is None
    assert result.hunted is True
    assert result.exec_cycles == 227722
