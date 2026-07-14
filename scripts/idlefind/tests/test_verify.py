# -*- coding: utf-8 -*-
"""The rules, pinned. Every case here is a real rom that taught us the rule.

If one of these ever goes green when it should be red, an unverified address is on its way
into a device's firmware table — which is the failure this whole tool exists to prevent.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gbaidle.verify import (  # noqa: E402
    FRAME_CYCLES, MIN_DROP, Reading, is_unmeasured, judge, screens_shared,
)


def reading(cycles, *, seq="a", distinct=100, frames=None):
    return Reading(exec_cycles=cycles, seq=seq, distinct=distinct, frames=frames)


# Kurukuru Kururin: the shape of a correct answer. The work collapses and every frame is
# byte-identical, because an idle skip removes waiting and nothing else.
def test_a_real_wait_loop_passes():
    off = reading(279446, seq="0x4e6cc1ad", frames=(1, 2, 3, 4))
    on = reading(71724, seq="0x4e6cc1ad", frames=(1, 2, 3, 4))

    v = judge(off, on)

    assert v.ok and v.exact
    assert v.drop == pytest.approx(0.743, abs=0.01)


# Final Fight One. Two frames of 1200 differ — the halt lands on the event boundary a touch
# differently — and requiring bit-identical frames threw this REAL loop away.
def test_a_wait_loop_that_shifts_a_frame_still_passes():
    # 1200 frames, two of them different — which is what Final Fight actually looks like.
    off = reading(280642, seq="A", frames=tuple(range(1200)))
    on = reading(76363, seq="B", frames=tuple(range(1198)) + (9998, 9999))

    v = judge(off, on)

    assert v.ok and not v.exact
    assert v.shared > 0.99


# KOF EX2, Ghost Trap, Space Invaders, F-Zero Climax — all four "looked right" and were
# doing precisely nothing. exec was below a full frame in every one of them, which is why
# that check is not the check.
def test_an_address_that_changes_nothing_fails():
    off = reading(70082, seq="A", frames=(1, 2, 3))
    on = reading(70018, seq="A", frames=(1, 2, 3))

    v = judge(off, on)

    assert not v.ok
    assert "no drop" in v.why
    assert v.drop < MIN_DROP


# Gunstar Super Heroes at 0x300041c: a 99.6% "drop" — because the game froze on one frame
# and stayed there. A big drop is not evidence on its own.
def test_an_address_that_freezes_the_game_fails():
    off = reading(278320, seq="A", distinct=855, frames=tuple(range(100)))
    on = reading(1100, seq="B", distinct=1, frames=(0,) * 100)

    v = judge(off, on)

    assert not v.ok
    assert "real work" in v.why
    assert v.drop > 0.9        # the drop was huge, and meaningless


# Bomberman Max 2: alive, 60% lighter, and half the screens it reaches are screens the
# unskipped run never drew. It did not shift — it diverged.
def test_an_address_that_sends_the_game_elsewhere_fails():
    off = reading(271677, seq="A", frames=tuple(range(0, 100)))
    on = reading(107600, seq="B", frames=tuple(range(50, 150)))

    v = judge(off, on)

    assert not v.ok
    assert v.shared == pytest.approx(1 / 3, abs=0.01)     # 50 shared of 150 seen


def test_screens_fall_back_to_the_distinct_count_when_there_are_no_frame_hashes():
    """The A/B path always asks for frame hashes, but a caller that did not must still be
    able to tell a frozen game from a waiting one."""
    assert screens_shared(reading(100, distinct=800), reading(50, distinct=1)) < 0.01
    assert screens_shared(reading(100, distinct=800), reading(50, distinct=790)) > 0.95


def test_a_missing_reading_is_not_a_pass():
    assert not judge(reading(0), reading(0)).ok


# The number that reads as "the heaviest game in the library" and means "we failed to
# measure it". Kirby US = 45% of budget; Kirby JP, the SAME GAME, lands here at 176%.
class TestUnmeasured:
    def test_a_full_frame_with_no_address_is_not_a_heavy_game(self):
        assert is_unmeasured(FRAME_CYCLES, None)

    def test_an_address_makes_the_number_mean_what_it_says(self):
        assert not is_unmeasured(FRAME_CYCLES, "0x8000422")

    def test_a_light_game_is_measured_even_without_an_address(self):
        # It waits through the BIOS, which gpSP already skips. Nothing to look up.
        assert not is_unmeasured(50000, None)
