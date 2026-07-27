# -*- coding: utf-8 -*-
"""_resume_covers — going back for the covers a restart abandoned.

The bug this fixes: both the prober and the cover fetcher keep their queue in memory,
and a restart empties both. The prober was re-queued at boot; the cover fetcher was
flipped to cover_status='none' and forgotten. 'none' is indistinguishable from "this
game has no art anywhere", so nothing tried again — a bulk upload plus a few restarts
left 953 of 2,281 snes roms permanently blank with the art sitting on IGDB.

These pin the three properties that make the retry safe to run on every boot: it only
touches blanks, it is bounded, and one failing rom does not take the rest down.
"""
import pytest

import app.main as main

# The hook is async; pytest-asyncio runs in strict mode here.
pytestmark = pytest.mark.asyncio


async def _run_resume(monkeypatch, seen):
    """Run the startup hook with autofill captured instead of hitting the network."""
    async def fake_autofill(session_id, rom):
        seen.append(rom["stored_name"])
        return True

    monkeypatch.setattr("app.routers.covers.autofill_rom", fake_autofill)
    # The hook creates a background task; await it directly so the test is deterministic.
    created = []
    monkeypatch.setattr(main.asyncio, "create_task", lambda coro: created.append(coro))
    await main._resume_covers()
    for coro in created:
        await coro


async def test_fills_roms_left_without_a_cover(session_id, make_rom, monkeypatch):
    make_rom(system_key="snes", name="Final Fantasy V.sfc", cover_status="none")
    seen = []
    await _run_resume(monkeypatch, seen)
    assert seen == ["Final Fantasy V.sfc"]


async def test_never_touches_a_rom_that_already_has_art(session_id, make_rom, monkeypatch):
    """The whole point is filling blanks. Re-fetching a cover someone already has —
    possibly one they set by hand — would be a boot that quietly undoes their work."""
    make_rom(system_key="snes", name="Has Cover.sfc", cover_status="ok")
    seen = []
    await _run_resume(monkeypatch, seen)
    assert seen == []


async def test_skips_pico8(session_id, make_rom, monkeypatch):
    """PICO-8 art is rendered from the cart itself at upload, never fetched. Asking a
    provider for it would be a guaranteed miss on every boot, forever."""
    make_rom(system_key="pico8", name="cart.p8", cover_status="none")
    seen = []
    await _run_resume(monkeypatch, seen)
    assert seen == []


async def test_is_bounded_by_the_page_limit(session_id, make_rom, monkeypatch):
    """Each rom is two or three provider round-trips. A boot must take a bite, not the
    whole backlog — the rest is picked up by the next restart."""
    monkeypatch.setattr(main, "_RESUME_COVER_LIMIT", 3)
    for i in range(7):
        make_rom(system_key="snes", name=f"Game {i}.sfc", cover_status="none")
    seen = []
    await _run_resume(monkeypatch, seen)
    assert len(seen) == 3


async def test_one_failing_rom_does_not_stop_the_others(session_id, make_rom, monkeypatch):
    """A provider 500 on one title must not cost the whole page."""
    for i in range(3):
        make_rom(system_key="snes", name=f"Game {i}.sfc", cover_status="none")

    calls = []

    async def flaky(session_id, rom):
        calls.append(rom["stored_name"])
        if len(calls) == 1:
            raise RuntimeError("provider exploded")
        return True

    monkeypatch.setattr("app.routers.covers.autofill_rom", flaky)
    created = []
    monkeypatch.setattr(main.asyncio, "create_task", lambda coro: created.append(coro))
    await main._resume_covers()
    for coro in created:
        await coro

    assert len(calls) == 3


async def test_does_nothing_when_the_library_has_converged(session_id, make_rom, monkeypatch):
    """The steady state, which is most boots: one query and no task at all."""
    make_rom(system_key="snes", name="Covered.sfc", cover_status="ok")
    created = []
    monkeypatch.setattr(main.asyncio, "create_task", lambda coro: created.append(coro))
    await main._resume_covers()
    assert created == []
