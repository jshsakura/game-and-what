# idlefind — will this GBA game run on the real hardware?

Two questions the ROM header cannot answer, so we answer them by **running the game**.

```bash
make                                   # build the binary (patched mGBA, headless)
./idlefind.py measure Zelda.gba        # what does it cost, and can we skip its wait?
./idlefind.py sweep   /roms/gba        # …a whole directory
./idlefind.py table   /roms/gba --write   # fold the results into the shared table
./idlefind.py show                     # what the table already knows
```

```
AMZE  슈퍼마리오USA.gba   0x8001cfc (ROM)  280,200 -> 89,918 cy/frame
                          (68% less work, identical frames)  [CPU 100% of the device's budget]
FDKE  클래식 NES - 동키콩  no wait loop to skip — the frame goes into real work (227,722 cy/frame)
```

Self-contained: a python package, a C file, a Makefile and a patch. **Copy the directory
into another repo** (the firmware's, say), run `make`, and it works. The only python
dependency is `capstone`, and only to prefer a branch pc over a landing point.

---

## 1. Where is its VBlank wait loop?

gpSP has **no automatic idle-loop detection.** `gba_memory.c` defaults
`idle_loop_target_pc` to `0xFFFFFFFF` and only overrides it when the cart's 4-char game
code is found in its hand-maintained table (`gba_over.h`). A game missing from that table
**busy-waits through the entire frame** — 280,896 cycles of emulating a spin — and has no
chance of full speed on the Game & Watch's M7, however light it really is.

That table is also wrong in places, and **a Korean patch defeats it entirely**: the patch
keeps the original cart header, so gpSP looks the game up under the original code and
applies the original address, which the patch has moved. Nothing in the filename, the
header or the region code warns you. The game simply never gets the skip.

You cannot find the loop by reading the ROM. A spin loop and an ordinary polling loop are
the same shape in a disassembly — a 1MB scan turns up ~95 candidates per game, and picking
the most plausible one is right about 59% of the time. What separates them is *behaviour*.

## 2. How much work does it actually do per frame?

Knowing the loop only says the skip is *available*. Whether it is *enough* depends on how
much of the frame the game really idles.

`mgba-cycle-counter.patch` adds a counter to mGBA's `ARMRunLoop` that accumulates only the
cycles spent **executing instructions**. Idle-skip and HALT move the clock forward outside
that loop, so they never land in the count. What is left, per frame, is the game's real
work against a 280,896-cycle frame — and against the ~90,000 the M7 can emulate in one.

---

## The rules (`gbaidle/verify.py`)

**An address is not proven until it has been A/B'd.** Each rule below is here because
something got through without it. They live in ONE module, and `backend/app/services/
gba_probe.py` — the upload prober — is an adapter over it: an uploaded rom is judged by
exactly the same gate as an offline sweep. It used to have its own copy of the logic with
no A/B at all, and that is how an address mGBA merely *detected* could reach the shipped
table.

**1. The detector is not an oracle.** mGBA detects Super Mario World's loop at `0x80016d4`.
Hand gpSP that address and it skips nothing — the frame stays pinned at 280,896 cycles. The
real loop is at `0x80005ec`. Across a 633-rom sweep, **17 of 111 detections were like this.**

**2. "exec is below a full frame" proves nothing.** This is the trap. A game that already
waits via the BIOS sits far below a full frame *no matter what address you give it*, so a
bogus address sails straight through that check. Five passed it and were doing precisely
nothing: KOF EX2 (×2), Ghost Trap, Space Invaders, F-Zero Climax.

**3. Only the difference is evidence.** Run the game twice — with the skip disabled
(`0x8FFFFFE`, a pc the game never executes) and with the address — and keep it only if the
work **measurably drops** (≥15%).

**4. A drop is not enough either.** Forcing an address makes mGBA *halt* there, so an
address that is really doing WORK also "drops" the cycles — by strangling the game. So the
game must still be **drawing what it drew**: mGBA is deterministic and an idle skip removes
only waiting, so the screens it reaches must be the same screens.

**5. But not bit-identical.** Requiring every frame to match threw away a real loop. The
bar is the **set of screens reached** (≥97%):

| | drop | screens | |
|---|---|---|---|
| Kurukuru Kururin (known answer) | 74% | frame-for-frame identical | ship |
| Final Fight One | 73% | 99.6% shared (2 frames of 1200 differ) | ship |
| Bomberman Max 2 | 60% | **50.3%** — half its screens are *different* screens | reject |
| Gunstar Super Heroes (`0x300041c`) | 99.6% | distinct 855 → **1** (frozen) | reject |

---

## When the detector is silent: ask the frame where its cycles went

mGBA only records a loop it can *prove* is idle, and it wants the same jump target twice in
a row (`memory.c:263`). **A loop that hops is invisible to it.** Super Mario Advance:

```
0x8001cde  poll the flag the VBlank IRQ sets
0x8001cf2  beq  #0x8001cfc      <- the pc libretro and ReGBA both ship
0x8001cfc  b    #0x8001cbc
0x8001cbc  b    #0x8001cde      <- three hops, back to the body
```

gpSP skips that happily — `cpu.cc:3063` is a bare PC compare, run after *every*
instruction — while our probe called the game 175% and unmeasurable. **97 roms sat in that
hole.**

So `idlefind` histograms every executed cycle against the PC that spent it
(`gIdleFindPcHist`, patched into `ARMRunLoop`). A game that is waiting spends the frame in
the wait — that is what waiting IS — so the loop is at the top of that list, and `hunt.py`
**forces the hottest 20 addresses in turn.** If one is a landing point of the wait, mGBA
halts there and the work collapses; if not, nothing happens. The ranking is a hypothesis;
the A/B is the answer.

Three things this had to learn the hard way:

- **The loop is not always in ROM.** The Classic NES / Famicom Mini / Hudson carts are
  emulators: they copy a 6502 interpreter into IWRAM and run it there, and a ROM-only
  histogram sees 0.1% of the frame. The histogram covers EWRAM and IWRAM, and the binary
  dumps the bytes at each hot pc **from the emulated bus** — RAM code is not in the rom
  file. Three shipped addresses are RAM addresses.
- **Do not guess the loop's shape.** Reading a "body + backward branch" out of the
  disassembly missed the hopping loops twice: the lowest hot address was the branch that
  *enters* the loop, and starting a Thumb disassembly there put the decoder out of phase so
  everything after it read as garbage. Forcing a hot address needs no shape at all.
- **A hot loop is not always a wait.** A blit loop is just as hot. Rule 4 is what tells
  them apart.

## Other things that bit us

- **Match roms on the cart HEADER, never the filename.** A library renames files, so a name
  lookup can quietly hand you a different game — it A/B'd F-Zero Climax's address against
  another rom entirely, and *passed* it. A Korean patch keeps the original header too,
  which is why the header is the only key worth trusting. Walked into twice.
- **A rom whose loop is never found reports ~280,896 cycles.** That reads as "the heaviest
  game in the library" and means "not measured". Kirby's US release measures 45% of budget;
  the Japanese release of the SAME GAME lands at 176%. `verify.is_unmeasured()` is that
  distinction, and `idle_hunted` in the table is what lets a game we DID search be called
  heavy honestly.
- **"Light" can mean "mGBA skipped it for us".** A rom can measure light only because
  mGBA's own detector found and removed a loop we cannot hand to gpSP — on the device it
  will spin. Guilty Gear X read 16k and was really 280k. Any rom with no shippable address
  must be re-measured with the skip OFF; that is what it will actually cost.
- **`GBA_IDLE_LOOP_NONE` is `0xFFFFFFFF`, not 0.** Seeding a loop variable with a bare 0
  made an undetected rom report a loop at `0x00000000`.
- **The build flags are not optional.** `struct mCore`'s layout depends on mGBA's own cmake
  flags (`ENABLE_DEBUGGERS` alone changes its size by 4 KB); compile against a different
  set and you get a null vtable and a segfault on the first call — silently, at run time.
  The Makefile reads mGBA's flags back out of its own build rather than guessing them.

---

## Layout

```
idlefind.py                the CLI: measure · sweep · table · show
gbaidle/verify.py          THE RULES. Pure, tested, and the only copy.
gbaidle/hunt.py            detector first, then the frame's cycle histogram. Ends at verify.
gbaidle/runner.py          drives the binary; degrades to None when it is not installed
gbaidle/rom.py             the cart header — and the rule to match on it, never the name
gbaidle/table.py           the shared JSON the firmware's C table is generated from
idlefind.c                 the binary: mGBA + cycle counter + per-PC histogram
shot.c                     render one frame — the only way to spot a Korean patch
mgba-cycle-counter.patch   what gets patched into mGBA
tests/                     the rules, pinned. `make check` runs them.
```

The results go to `scripts/gba_idle_loop_db.json`, and `scripts/gen_gba_over.py` turns that
into `firmware/gba/gba_idle_loop.c` for the device. See `docs/GBA_IDLE_SKIP.md` for what
the tool has found so far and what it bought.
