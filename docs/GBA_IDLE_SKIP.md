# The GBA idle skip — what it is, what it bought, and what it cost to find out

> The tool is `scripts/idlefind` (its README is the method). The table it produces is
> `scripts/gba_idle_loop_db.json`. What the firmware takes is
> `firmware/gba/gba_idle_loop.c`. This document is the **result**.

## The one fact the whole port turns on

A GBA game spends most of every frame doing nothing. It sets up the screen, then sits in a
tight loop reading a flag until the VBlank interrupt fires:

```
0x800041a  ldrh r0, [r1]     ; poll
0x800041e  cmp  r0, #0
0x8000422  beq  #0x800041a   ; still waiting → go round again
```

On real hardware that costs nothing — it is a CPU idling. **In an emulator it is the most
expensive thing in the frame**, because the emulator faithfully executes every one of those
instructions.

gpSP can jump over it. `cpu.cc:3063` compares the PC after every instruction, and when it
matches `idle_loop_target_pc` it ends the frame slice and moves the clock to the next event.
But **gpSP cannot find that address by itself.** It defaults to `0xFFFFFFFF` and only
overrides it when the cart's 4-char code is in a hand-maintained table (`gba_over.h`).

> **A game absent from that table busy-waits through the whole 280,896-cycle frame.**
> It is not "a bit slower". It has no chance of full speed, however light it really is.

So the table IS the port's performance. And it is incomplete, wrong in places, and
**defeated entirely by a Korean patch** — the patch keeps the original header, so gpSP
applies the original game's address, which the patch has moved.

## What it bought

| | |
|---|---|
| Without an address: the spin fills the frame | **280,896 cy** = 312% of the device's budget |
| With one: the median measured game | **76,000 cy** = 85% of budget |
| Games that clear the budget, of the 121 with an address | **77** |
| …without the skip | **0** |

The device agrees. Pokémon Emerald measures 78,294 cycles here; on hardware it runs at full
speed and sits idle **1.65 ms of every frame waiting for the LCD**. Take its address away
and it would be emulating a spin for that whole frame instead.

## The state of the table

515 game codes carry a measured frame cost. Every address was proven by running the game.

| | |
|---|---|
| **idle-loop address, A/B verified** | **121** |
| no address needed — the game waits through the BIOS, which gpSP already skips | 340 |
| **hunted, and there IS no wait loop → genuinely heavy** | **48** |
| the rom does not boot (5 are peripherals: TV tuner, movie player, minicam…) | 6 |
| has an address and *still* over budget | 44 |

**The 48 are a verdict, not a gap.** The clearest case is the emulator-carts — Classic NES,
Famicom Mini, Hudson Best Collection. They are 6502 interpreters: their hot code is a
jump-table dispatch (`ldr pc, [ip, r1, lsl #2]`) sitting in IWRAM, and they spend the entire
frame emulating a NES. There is no wait to skip. (On this device, run the NES rom in the NES
core instead.)

## Three addresses are not in ROM

`ZMDE` is in EWRAM (`0x20314a6`), `AYPE`/`AYPP` in IWRAM (`0x3005d18`). An emulator-cart
copies its core into RAM and waits there. gpSP does not care which region a PC is in —
`cpu.cc:3063` is a bare compare — and the game links its RAM code at a fixed address, so the
pc is stable across boots. **This would look like corruption if you were not told.**

And not every pc is a backward branch. Where a wait loop *hops* rather than branching
straight back, the pc is a landing point inside it. Same reason it works: the loop executes
it every iteration.

## What it cost to find out

The honest part. Three filters, each catching what the last let through.

**111 detections → 89 shipped.** Then a second hunt, for the loops the detector cannot see
at all, took it to **121**.

1. **The detector is not an oracle.** mGBA detects Super Mario World's loop at an address
   gpSP skips nothing on. **17 of 111 died here.**
2. **"exec is below a full frame" proves nothing.** A game that already waits through the
   BIOS sits far below a full frame *whatever* address you give it, so a bogus one sails
   through. **5 more died here at a 0% drop.**
3. **Only the difference is evidence.** Run with the skip off, run with the address, keep it
   only if the work measurably drops.

Then the second hunt added a fourth, because forcing an address makes mGBA *halt* there —
so an address that is really doing WORK also "drops" the cycles, by strangling the game:

4. **The game must still be drawing what it drew.** Gunstar Super Heroes "drops" 99.6% at
   `0x300041c` — and renders one frozen frame forever. Bomberman Max 2 drops 60% and stays
   alive, but half the screens it then reaches are screens the unskipped run never drew. It
   did not shift; it diverged. Both rejected.
5. **…but not bit-identically.** Requiring every frame to match threw away Final Fight One,
   which keeps 99.8% of its frames and *all* of its screens (two frames of 1200 differ,
   because the halt lands on the event boundary a touch differently). The bar is the SET of
   screens reached.

### The 97 that could not be judged

A rom whose loop is never found spins, the spin gets counted as work, and it comes back at a
full frame — reading as the heaviest game in the library when it means **"we failed to
measure it"**. Proof, inside the library: Kirby's US release measures 45% of budget; the
Japanese release of the *same game* landed at 176%.

97 roms sat there. They are all resolved now:

| | |
|---|---|
| a proven address found | **32** |
| were fine all along (the old probe was stuck in an intro) | 11 |
| genuinely heavy — hunted, and there is no wait loop | 48 |
| do not boot | 6 |

The one that broke it open was **Super Mario Advance**. Its wait loop hops three times
before it comes back, and mGBA's detector wants the same jump target twice in a row
(`memory.c:263`) — so the detector is silent, forever, no matter how long you run it. Both
libretro and ReGBA ship that address. We were calling the game 175% and unmeasurable.

The answer was to stop asking the detector and **ask the frame where its cycles went**: a
per-PC cycle histogram, then force the hottest addresses in turn. A game that is waiting
spends the frame in the wait — that is what waiting is.

## The budget is a model, and it moves

The card shows CPU load against **90,000 cycles**. That number is not a hardware constant.
It is what the M7 can *emulate* in the 16.74 ms frame once the renderer has taken its share,
and it was timed on the device:

| | Emu only | PPU | Scale | ns per emulated cycle | its own budget |
|---|---|---|---|---|---|
| Pokémon Emerald | 10.05 ms | 1.87 ms | 1.01 ms | 128 ns (78,294 cy) | 107,900 cy |
| FFTA | 17.89 ms | 3.56 ms | 0.96 ms | 154 ns (116,375 cy) | 79,500 cy |

Both figures move per game — a bigger working set means worse cache and a dearer cycle, and
the PPU costs what the game draws — so 90,000 is the middle of the two, and it reproduces
what the hardware does: Emerald runs, FFTA does not (0.75x).

**It tracks how fast the interpreter is, so it rises when the interpreter does.** Get FFTA
from 154 ns/cycle to 113 and it plays at 0.95x, the budget becomes ~110,000, and 91 of the
121 games fit instead of 77. Re-derive it — do not guess it forward:

```
budget = (16.74 ms − PPU − Scale) ÷ (that game's interpreter ms ÷ its exec_cycles)
```

It used to say 160,000, which was this project's own arithmetic. It called FFTA 73% and
painted it green — a game that cannot hold 60fps with the renderer switched **off**.

## Keeping it true

The tool is not a one-off script; it is how the table stays honest.

```bash
cd scripts/idlefind && make
./idlefind.py table /path/to/roms --write     # hunt anything the table has never seen
python3 ../gen_gba_over.py --c > ../../firmware/gba/gba_idle_loop.c
```

An **upload** goes through the same gate: `backend/app/services/gba_probe.py` is a thin
adapter over the same package and owns no rules of its own, so a rom uploaded to the library
is judged exactly as an offline sweep judges one — look it up, and only if we have never
seen it, hunt it and A/B what we find.
