# idlefind — will this GBA game run on the real hardware?

Two questions the ROM header cannot answer, so we answer them by **running** the game.

## 1. Where is its VBlank idle loop?

gpSP has **no automatic idle-loop detection.** `gba_memory.c` defaults
`idle_loop_target_pc` to `0xFFFFFFFF` and only overrides it when the cart's 4-char game
code is found in its hand-maintained table (`gba_over.h`). A game missing from that table
**busy-waits through the entire frame** and has no chance of full speed on the Game &
Watch's M7.

You cannot find that loop by reading the ROM. A spin loop and an ordinary polling loop are
the same shape in a disassembly — a 1MB scan turns up ~95 candidates per game, and picking
the most plausible one is right about 59% of the time. What separates them is *behaviour*.

mGBA already watches for exactly that (`IDLE_LOOP_DETECT`, `src/gba/memory.c`): it re-walks
a backward branch's body tracking which registers it can prove are unchanged, and records
the loop only if the body has no side effects and cannot exit on its own. `idlefind` drives
mGBA headless, forces detection on, and reports what it finds.

**This matters most for Korean patches.** A patch keeps the original cart header, so gpSP
looks the game up under the original code and applies the original address — which the
patch has moved. Nothing in the filename, the header or the region code warns you; the game
just never gets the skip.

## 2. How much work does it actually do per frame?

Knowing the loop only tells you the skip is *available*. Whether it's *enough* depends on
how much of the frame the game really idles — and nothing in the library said.

`mgba-cycle-counter.patch` adds a counter to mGBA's `ARMRunLoop` that accumulates only the
cycles spent **executing instructions**. Idle-skip and HALT jump the clock forward outside
that loop, so they never land in the count. What's left, per frame, is the game's real work
against a 280,896-cycle frame.

Compare it to what the hardware leaves the CPU (~160,000 cycles at a 340MHz OC, once the
PPU, audio and DMA have taken their share) and you get a verdict instead of a guess.

## An address is not proven until it is A/B'd

**This is the part that matters.** Detecting a loop is easy; knowing it is *the* loop is not,
and every shortcut here has already produced a wrong answer that looked right.

**1. The detector is not an oracle.** Super Mario World (한글패치) is detected at `0x80016d4`.
Hand gpSP that address and it skips nothing — the frame stays pinned at 280,896 cycles. The
real loop is at `0x80005ec`. Across a 633-rom sweep, **17 of 111 detections were like this.**

**2. "exec is below a full frame" proves nothing.** This is the trap. A game that already
waits via the BIOS sits far below a full frame *no matter what address you give it* — so a
bogus address sails straight through that check and ships. Five addresses passed it and were
doing precisely nothing: KOF EX2 (×2), Ghost Trap, Space Invaders, F-Zero Climax.

**3. Only the difference is evidence.** Run the game twice:

```bash
./idlefind rom.gba 1200 0x8FFFFFE     # a pc the game never executes -> nothing is skipped
./idlefind rom.gba 1200 <loop start>  # the real thing
```

Keep the address only if `exec_median` **measurably drops** (we require ≥15%). If it doesn't,
the address is not the wait loop, and gpSP fed it would be cutting the frame short somewhere
arbitrary.

## Other things that bit us

- **Match roms on the cart HEADER, never the filename.** The library renames files, so a name
  lookup can quietly hand you a different game. It A/B'd F-Zero Climax's address against
  another rom entirely — and passed it. A Korean patch keeps the original header too, which
  is why the header is the only key worth trusting.
- **A rom whose loop is never found reports ~280,896 cycles.** That reads as "heavy game" but
  means "loop not found". Four games looked heavy for exactly this reason and turned out to
  idle 73% of the frame once given the right address.
- **`GBA_IDLE_LOOP_NONE` is `0xFFFFFFFF`, not 0.** Seeding `idle_loop` with a bare 0 made an
  undetected rom report a loop at `0x00000000`, which read downstream as an IWRAM loop.
- **The harness mashes START/A.** It reaches the intro and early play, not a Pokémon battle.
  The numbers describe what it reached — which is why `exec_p90` is reported alongside the
  median, and why several games peak at a full frame in scenes the bot never got to.

## Build

Needs mGBA's source and a `libmgba.a` built from it.

```bash
git clone --depth 1 https://github.com/mgba-emu/mgba
cd mgba && git apply ../mgba-cycle-counter.patch      # the per-frame cycle counter
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT=OFF -DBUILD_SDL=OFF -DBUILD_GL=OFF \
         -DUSE_FFMPEG=OFF -DUSE_LIBZIP=OFF -DUSE_SQLITE3=OFF -DUSE_ELF=OFF \
         -DBUILD_STATIC=ON -DENABLE_SCRIPTING=OFF
make -j"$(nproc)" mgba
```

Compile the tools with **mGBA's own flags** — `struct mCore`'s layout depends on them, and
building against a different set silently yields a null vtable and a segfault at the first
call:

```bash
F=build/CMakeFiles/mgba.dir/flags.make
grep '^C_DEFINES'  "$F" | sed 's/^C_DEFINES *= *//'  > defs.rsp
grep '^C_INCLUDES' "$F" | sed 's/^C_INCLUDES *= *//' > incs.rsp
gcc -O2 @defs.rsp @incs.rsp -o idlefind idlefind.c build/libmgba.a -lz -lpng -lm -lpthread -ldl
gcc -O2 @defs.rsp @incs.rsp -o shot     shot.c     build/libmgba.a -lz -lpng -lm -lpthread -ldl
```

## Use

```bash
# detect the loop and measure the per-frame cost
./idlefind rom.gba 1800

# force an address you already have, to check it actually skips
./idlefind rom.gba 1800 0x80005e6        # NOTE: the loop's START, not the branch

# whole directory -> JSON, with the addresses converted to gpSP's (the BRANCH pc)
python3 idlefind.py ./idlefind /path/to/roms 1800 > out.json

# render a frame — the only way to tell a Korean patch from the original
./shot rom.gba 900 out.png
```

mGBA records the loop's **start**; gpSP's `gba_over.h` keys on the **backward branch** that
closes it (that is the PC `cpu.cc` compares against). `idlefind.py` disassembles forward from
the start to find it. `scripts/gen_gba_over.py` turns the results into paste-ready entries.
