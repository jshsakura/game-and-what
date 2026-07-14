"""THE RULES. An address is not proven until it has passed these, and nothing ships that
has not.

This module is deliberately pure — no subprocess, no filesystem, no emulator. It takes two
readings and returns a verdict, so the rules can be tested, and so there is exactly ONE
place they live. They used to be copy-pasted across three scripts and MISSING from the
upload prober, which is how unverified addresses reached the shipped table.

Each rule is here because something got through without it:

1. **The detector is not an oracle.** mGBA finds Super Mario World's loop at an address
   gpSP skips nothing on. 17 of 111 detections died on this.

2. **"exec is below a full frame" proves nothing.** A game that already waits through the
   BIOS sits far below a full frame *whatever* address you hand it, so a bogus one sails
   through. 5 more died here, all at a 0% drop.

3. **Only the DIFFERENCE is evidence.** Run with the skip disabled, run with the address,
   and keep it only if the work measurably drops.

4. **A drop is not enough either.** Forcing an address makes mGBA halt there, so an
   address that is really doing WORK also "drops" the cycles — by strangling the game.
   Gunstar Super Heroes drops 99.6% at 0x300041c and renders one frozen frame forever.
   So the game must still be drawing what it drew: mGBA is deterministic and an idle skip
   removes only waiting, so the screens it reaches must be the same screens.

5. **But not bit-identical.** Requiring every frame to match threw away Final Fight One,
   which keeps 99.8% of its frames and all of its screens — it differs on two frames of
   1200 because the halt lands on the event boundary a touch differently. The bar is the
   SET of screens reached, which still rejects Bomberman Max 2 (60% drop, and half its
   screens are screens the unskipped run never drew).
"""
from __future__ import annotations

from dataclasses import dataclass

# A rom address the game never executes. Forcing it means nothing is skipped — that is the
# "off" side of every A/B, and it is what makes the comparison a comparison.
NO_SKIP = "0x8FFFFFE"

MIN_DROP = 0.15          # below this the address is not where the frame was going
SAME_SCREENS = 0.97      # the game must still reach the screens it reached
FRAME_CYCLES = 280896


@dataclass(frozen=True)
class Reading:
    """One run of the emulator. `frames` is every rendered frame's hash, in order."""
    exec_cycles: int
    seq: str | None = None            # rolling digest of `frames`
    distinct: int | None = None
    frames: tuple[int, ...] | None = None


@dataclass(frozen=True)
class Verdict:
    ok: bool
    drop: float                       # share of the work the address removed
    shared: float                     # share of the screens both runs reached
    exact: bool                       # every frame identical
    why: str


def screens_shared(off: Reading, on: Reading) -> float:
    """How much of what the game drew is the same, as a SET.

    Frozen -> ~0 (Gunstar: 855 distinct screens -> 1). Merely waiting less -> ~1.
    Falls back to the distinct-frame count when we have no per-frame hashes, which is a
    weaker signal but still catches a game that died.
    """
    if off.frames and on.frames:
        a, b = set(off.frames), set(on.frames)
        return len(a & b) / len(a | b) if a and b else 0.0
    if off.distinct and on.distinct:
        return min(on.distinct / off.distinct, 1.0)
    return 0.0


def judge(off: Reading, on: Reading) -> Verdict:
    """Does this address earn its place? Both halves, or it does not ship."""
    if not off.exec_cycles or on.exec_cycles is None:
        return Verdict(False, 0.0, 0.0, False, "no reading")

    drop = (off.exec_cycles - on.exec_cycles) / off.exec_cycles
    shared = screens_shared(off, on)
    exact = bool(off.seq and on.seq and off.seq == on.seq)
    safe = exact or shared >= SAME_SCREENS

    if drop < MIN_DROP:
        # The address is real code, but it is not where the frame was going. gpSP fed this
        # would be ending the frame slice somewhere arbitrary, for nothing.
        return Verdict(False, drop, shared, exact, "no drop: the address does nothing")
    if not safe:
        # It took cycles away by taking WORK away. That is not a wait loop.
        return Verdict(False, drop, shared, exact,
                       "the game went somewhere else: this loop is doing real work")
    return Verdict(True, drop, shared, exact, "")


def is_unmeasured(exec_cycles: int, idle_pc: str | None) -> bool:
    """A rom whose loop was never found spins, and the spin gets counted as work — so it
    comes back at a full frame and reads as the heaviest game in the library. It is not a
    heavy game; it is a rom we failed to measure, and it must not be reported as one.

    (Kirby's US release measures 45% of budget. The Japanese release of the SAME GAME
    lands here at 176%.)
    """
    return not idle_pc and exec_cycles >= 0.97 * FRAME_CYCLES
