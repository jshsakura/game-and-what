"""gbaidle — find a GBA game's VBlank wait loop by RUNNING it, and prove the address works.

Why this exists, in one paragraph: gpSP has no automatic idle-loop detection. It defaults
`idle_loop_target_pc` to 0xFFFFFFFF and only overrides it when the cart's 4-char code is in
a hand-maintained table (`gba_over.h`). A game absent from that table busy-waits through
the WHOLE frame — 280,896 cycles of emulating a spin — and cannot reach full speed on the
Game & Watch's M7 however light it really is. The table is therefore the shortlist, and it
is incomplete, wrong in places, and defeated entirely by a Korean patch (the patch keeps
the original header, so gpSP applies the original game's address, which the patch moved).

You cannot read the answer off the rom: a spin loop and an ordinary polling loop are the
same shape in a disassembly (~95 candidates per rom; picking the likeliest is right 59% of
the time). So we run the game.

    from gbaidle import hunt, rom
    found, exec_off = hunt.find("Zelda.gba")
    print(rom.game_code("Zelda.gba"), hunt.summarise(found, exec_off))

Self-contained on purpose: a package, a C file, a Makefile and a patch. Copy the directory
into another repo (the firmware's, say), run `make`, and it works — the only python
dependency is capstone, and that only to prefer a branch pc over a landing point.

Modules, in the order they matter:

    verify   THE RULES. An address is not proven until it has passed them. Pure.
    hunt     detector first, then the frame's own cycle histogram. Ends at verify.
    runner   drives the patched-mGBA binary; degrades to None when it is not installed.
    rom      the cart header — and the rule to match on it and NEVER on the filename.
    table    the shared JSON the firmware's C table is generated from.
"""
from . import hunt, rom, runner, table, verify   # noqa: F401

__all__ = ["hunt", "rom", "runner", "table", "verify"]
