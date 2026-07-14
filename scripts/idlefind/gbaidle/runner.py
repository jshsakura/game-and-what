"""Drive the `idlefind` binary and turn its JSON into a Reading.

The binary is the only thing here that is not portable python: it is mGBA, patched with a
per-frame cycle counter and a per-PC cycle histogram, driven headless. `make` builds it;
see the README for what the patch does and why the build flags are not optional.

If the binary is missing, `available()` is False and every caller degrades to lookup-only
rather than crashing. That is the deployed reality: a plain dev checkout has no binary,
and the app still has to serve the library.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from .verify import NO_SKIP, Reading

log = logging.getLogger(__name__)

DEFAULT_FRAMES = 1500        # ~25 s of play: past the intro, into the game
TIMEOUT = 300                # a hung rom must never wedge a queue

#: Override with IDLEFIND_BIN when it is not on PATH (the docker image installs it there).
BINARY = os.getenv("IDLEFIND_BIN") or shutil.which("idlefind")


def available() -> bool:
    return bool(BINARY and Path(BINARY).exists())


def run(rom: Path | str, *, forced_pc: str | None = None, frames: int = DEFAULT_FRAMES,
        want_frames: bool = False) -> Reading | None:
    """One run of the game.

    forced_pc = None      -> let mGBA's detector look for the loop itself
    forced_pc = NO_SKIP   -> nothing is skipped: the "off" side of an A/B
    forced_pc = <address> -> halt there: the "on" side

    want_frames asks the binary for every frame's hash, which is what lets us tell a game
    that merely waits less from one that has been strangled. It costs a little output and
    nothing in run time, so the A/B path always asks.
    """
    if not available():
        return None

    cmd = [BINARY, str(rom), str(frames)]
    if forced_pc:
        cmd.append(forced_pc)
    env = {**os.environ, "IDLEFIND_HASHES": "1"} if want_frames else None

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT, env=env)
        # mGBA logs to stdout, so the JSON is the LAST line, never the only one.
        data = json.loads(proc.stdout.decode(errors="replace").strip().splitlines()[-1])
    except (subprocess.TimeoutExpired, OSError, ValueError, IndexError) as exc:
        log.warning("idlefind failed on %s: %s", rom, exc)
        return None

    if not data.get("exec_median"):
        return None
    return _reading(data)


def raw(rom: Path | str, *, forced_pc: str | None = None, frames: int = DEFAULT_FRAMES,
        env: dict[str, str] | None = None) -> dict | None:
    """One run, returned as the binary's own JSON. For callers that want a field the
    Reading does not carry — e.g. `block_cycles`, what a game's sound driver costs."""
    if not available():
        return None
    cmd = [BINARY, str(rom), str(frames)] + ([forced_pc] if forced_pc else [])
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT,
                              env={**os.environ, **(env or {})})
        return json.loads(proc.stdout.decode(errors="replace").strip().splitlines()[-1])
    except (subprocess.TimeoutExpired, OSError, ValueError, IndexError) as exc:
        log.warning("idlefind failed on %s: %s", rom, exc)
        return None


def run_off(rom: Path | str, **kw) -> Reading | None:
    """The baseline: the game with nothing skipped. Everything is measured against this."""
    return run(rom, forced_pc=NO_SKIP, want_frames=True, **kw)


def detect(rom: Path | str, **kw) -> tuple[Reading | None, int | None, dict]:
    """Let mGBA's detector try. Returns (reading, loop_start, raw).

    The detector only records a loop it can PROVE is idle, and it wants the same jump
    target twice in a row (memory.c:263) — so it is silent on a loop that hops (Super
    Mario Advance takes three hops before it comes back). When it is silent, hunt.
    """
    if not available():
        return None, None, {}
    cmd = [BINARY, str(rom), str(kw.get("frames", DEFAULT_FRAMES))]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT)
        data = json.loads(proc.stdout.decode(errors="replace").strip().splitlines()[-1])
    except (subprocess.TimeoutExpired, OSError, ValueError, IndexError) as exc:
        log.warning("idlefind failed on %s: %s", rom, exc)
        return None, None, {}

    if not data.get("exec_median"):
        return None, None, data
    start = data.get("loop_start")
    return _reading(data), (int(start, 16) if start else None), data


def hot_pcs(rom: Path | str, **kw) -> tuple[Reading | None, list[tuple[int, int]], dict[int, bytes]]:
    """Where the frame's cycles actually went, with the skip OFF.

    A game that is waiting spends the frame in the wait — that is what waiting IS — so the
    loop is at the top of this list. Also returns the bytes at each hot pc, read from the
    emulated bus: RAM code is not in the rom file, and an emulator-cart's wait loop lives
    in IWRAM.
    """
    if not available():
        return None, [], {}
    cmd = [BINARY, str(rom), str(kw.get("frames", DEFAULT_FRAMES)), NO_SKIP]
    env = {**os.environ, "IDLEFIND_HASHES": "1"}
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT, env=env)
        data = json.loads(proc.stdout.decode(errors="replace").strip().splitlines()[-1])
    except (subprocess.TimeoutExpired, OSError, ValueError, IndexError) as exc:
        log.warning("idlefind failed on %s: %s", rom, exc)
        return None, [], {}

    if not data.get("exec_median"):
        return None, [], data

    hot = [(int(pc, 16), cy) for pc, cy in (data.get("hot") or [])]
    mem = {int(pc, 16): bytes.fromhex(blob) for pc, blob in (data.get("mem") or {}).items()}
    return _reading(data), hot, mem


def _reading(data: dict) -> Reading:
    frames = data.get("frames")
    return Reading(
        exec_cycles=data["exec_median"],
        seq=data.get("seq"),
        distinct=data.get("distinct"),
        frames=tuple(frames) if frames else None,
    )
