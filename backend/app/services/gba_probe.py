"""Work out whether an uploaded GBA rom can run on the real hardware.

Two things decide it, and the cart header carries neither.

1. **Where is the game's VBlank wait loop?** gpSP has no automatic detection — it defaults
   `idle_loop_target_pc` to 0xFFFFFFFF and only overrides it when the cart's 4-char code is
   in a hand-maintained table. A game absent from that table busy-waits through the whole
   frame and cannot reach full speed on the M7 however light it really is.

2. **How much work does the game actually do per frame?** Knowing the loop only says the
   skip is *available*, not that it is *enough*.

Neither can be read off the rom, so we run the game. **This module is a thin adapter over
`scripts/idlefind` — the tool that does that — and it deliberately owns no rules of its
own.** It used to: it took whatever mGBA's detector reported, converted it to a branch pc
and wrote it down as a verified address. That is precisely the mistake the tool exists to
prevent — across a 633-rom sweep, 22 of 111 detections were doing nothing at all, and one
of them would still have been shipped into a firmware table. Now an upload goes through
the same gate as everything else: the address must measurably cut the work AND leave the
game drawing what it drew (`gbaidle/verify.py`).

Two paths, in order:

* **Look it up.** `scripts/gba_idle_loop_db.json` holds everything already measured — free,
  instant, and it covers the games we have.
* **Hunt it.** Only for a rom we have never seen. It is a full core for ~30 s (detector,
  then the frame's own cycle histogram, then an A/B per candidate), so callers run it in
  the background and behind a semaphore.

If the `idlefind` binary is not in the image (a plain dev checkout, say), measurement is
skipped and lookup still works. Never raises: a probe that fails leaves the rom unmeasured,
which the UI shows honestly rather than calling it heavy.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# The tool lives in scripts/idlefind and is copied into the image beside the app. It is a
# standalone package on purpose — the firmware repo can take the same directory and use it.
_TOOL = Path(__file__).resolve().parents[3] / "scripts" / "idlefind"
if str(_TOOL) not in sys.path:
    sys.path.insert(0, str(_TOOL))

from gbaidle import hunt as _hunt          # noqa: E402
from gbaidle import rom as _rom            # noqa: E402
from gbaidle import runner as _runner      # noqa: E402
from gbaidle import table as _table        # noqa: E402
from gbaidle import verify as _verify      # noqa: E402

FRAME_CYCLES = _verify.FRAME_CYCLES

# One at a time. A hunt is a full core for ~30 s, and a bulk upload would otherwise bury
# the box under a rom-per-core stampede while someone is trying to browse.
_probe_lock = asyncio.Semaphore(1)


@dataclass(frozen=True)
class Probe:
    """What we learned about a rom.

    `idle_pc` is the PC gpSP ends the frame slice at — usually the backward branch that
    closes the wait loop, or a landing point inside it where the loop hops rather than
    branching straight back. It is None unless the address PASSED the A/B.
    """
    game_code: str
    idle_pc: str | None
    exec_cycles: int | None
    source: str            # "db" | "measured"
    idle_drop: float | None = None   # what the skip bought, measured
    hunted: bool = False             # we ran it and searched: a full frame is the GAME's answer


def game_code(path: Path) -> str | None:
    """The 4 chars at rom[0xAC]. The key — never the filename, which a library renames."""
    return _rom.game_code(path)


def lookup(code: str) -> Probe | None:
    """A rom the table has already measured."""
    row = _table.load().get(code)
    if not row or not _table.measured(row):
        return None
    return Probe(
        game_code=code,
        idle_pc=_table.shippable_pc(row),
        exec_cycles=row["exec_median"],
        source="db",
        idle_drop=row.get("idle_drop"),
        hunted=bool(row.get("idle_hunted")),
    )


def _hunt_sync(rom_path: Path, code: str) -> Probe | None:
    found, exec_off = _hunt.find(rom_path)
    if not found and not exec_off:
        return None                     # the rom did not run at all
    if found:
        return Probe(code, found.pc_hex, found.exec_cycles, "measured",
                     idle_drop=round(found.verdict.drop, 3), hunted=True)
    # Hunted, and there is nothing to skip. The no-skip cost IS what the device will pay,
    # so it is the honest number — and `hunted` is what stops the UI calling it unmeasured.
    log.info("gba: no wait loop in %s (%d cy/frame — it works the whole frame)",
             rom_path.name, exec_off)
    return Probe(code, None, exec_off, "measured", hunted=True)


async def measure(rom_path: Path) -> Probe | None:
    """Run the game. None if we have no binary, or the rom would not boot."""
    code = game_code(rom_path)
    if not code or not _runner.available():
        return None

    async with _probe_lock:
        # The hunt is blocking subprocess work; keep it off the event loop.
        return await asyncio.to_thread(_hunt_sync, rom_path, code)


async def probe(rom_path: Path) -> Probe | None:
    """Look it up; hunt only if we have never seen it."""
    code = game_code(rom_path)
    if not code:
        return None
    return lookup(code) or await measure(rom_path)
