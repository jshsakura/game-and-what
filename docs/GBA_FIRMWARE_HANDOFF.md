# GBA on the hardware — handoff to `game-and-watch-retro-go-sd`

**Nothing in `game-and-watch-retro-go-sd` has been touched.** This is the spec for whoever
wires the core there. The analyzer stays here, in `game-and-what`; only its **results**
travel to the firmware.

Everything below was measured, not assumed. Where a claim is unverified, it says so.

---

## 1. The one fact that decides the whole port

**gpSP has no automatic idle-loop detection.**

| | |
|---|---|
| `gba_memory.c:2903` | `idle_loop_target_pc = 0xFFFFFFFF` — the default never matches |
| `gba_memory.c:1641` | overridden **only** if the cart's 4-char code is in `gba_over.h` |
| `cpu.cc:3063`, `arm/arm_emit.h:455` | at that PC, the remaining cycles are zeroed → jump to the next event |

So a game absent from that table **busy-waits through the entire frame**. It is not "a bit
slower" — it has no chance of full speed at all. The table is the shortlist, and it is
hand-maintained, so it is both incomplete and, in places, wrong.

**This bites Korean patches hardest.** A patch keeps the original cart header — same game
code, same region letter, same everything. gpSP therefore looks the game up under the
ORIGINAL code and applies the ORIGINAL address, which the patch has moved. Nothing in the
filename, the header or the region warns you. The game simply never gets the skip.

---

## 2. What to build in the firmware

### 2.1 Do NOT fork gpSP to edit `gba_over.h`

gpSP exposes the target as a plain global:

```c
/* gpsp/cpu.h:161 */
extern u32 idle_loop_target_pc;
```

So the porting layer can override it **after** the ROM is loaded, from a table we ship.
No fork, no patched submodule, and it corrects gpSP's own wrong entries for free.

```c
/* Core/Src/porting/gba/main_gba.c — after gpSP has loaded the rom */
extern u32 idle_loop_target_pc;

const u32 pc = gba_idle_loop_lookup(gamepak_code);   /* the 4 chars at rom[0xAC] */
if (pc) {
    idle_loop_target_pc = pc;                        /* our measured value wins */
}
```

`gba_idle_loop_lookup()` is the generated table (§3). Its entries are keyed on the same
4-char code gpSP uses, so an entry silently replaces gpSP's when both exist — which is
exactly what we want for FireRed and LeafGreen, where gpSP is wrong.

### 2.2 Suggested paths (matching how the other cores sit)

Cores are submodules under `external/`, glue under `Core/Src/porting/<system>/`:

```
external/gpsp/                              # submodule, UNMODIFIED upstream
Core/Src/porting/gba/main_gba.c             # glue: input, video, audio, save
Core/Src/porting/gba/gba_idle_loop.c        # ← generated here, copied over
Core/Src/porting/gba/gba_idle_loop.h
```

`gba_idle_loop.c` is **generated, not hand-edited.** Regenerate it here and copy; do not
patch it in place, or the next measurement run will silently disagree with the firmware.

### 2.3 Buttons

The real Game & Watch has **no shoulder buttons**, and GBA needs L and R.

The firmware's existing wiring (`Core/Src/porting/odroid_input.c:48-59`):

| G&W button | logical key |
|---|---|
| `B_GAME` | `START` |
| `B_TIME` | `SELECT` |
| `B_PAUSE` | `VOLUME` (the menu key) |
| `B_A` / `B_B` | `A` / `B` |
| `B_START` / `B_SELECT` → X/Y | **not physical** — REMOTE_INPUT only |

Mario has A/B only. Zelda has a third button wired to X (`main_gwenesis.c:652-661`:
`isZelda ? ODROID_INPUT_X : ODROID_INPUT_VOLUME`). Mega Drive hit the same shortage and
solved it with a runtime reassign menu — `s_md_keydefine`, 6 combos
(`main_gwenesis.c:112-120, 356-370`). **Copy that pattern for L/R.** (The web player
leaves L/R on the keyboard — its on-screen pad is a replica of the device face, which
has no shoulder buttons to draw.)

---

## 3. The data, and how to regenerate it

**121 addresses**, each one measured. **515 game codes** carry a frame cost — of those,
**340 need no entry at all** (they wait via the BIOS, which gpSP already skips), **48 have
no wait loop to skip** (they really are that heavy — see below), and 6 do not boot.

Files you copy: `firmware/gba/gba_idle_loop.{c,h}`.

> **Two things changed shape in this table.** Both are fine for gpSP's interpreter, and
> both would look like corruption if you were not told:
>
> - **Three addresses are not in ROM.** `ZMDE` is in EWRAM (`0x20314a6`), `AYPE`/`AYPP` in
>   IWRAM (`0x3005d18`). An emulator-cart copies its core into RAM and waits there.
>   `cpu.cc:3063` compares `reg[REG_PC]` after *every* instruction and does not care which
>   region it is in, and the game links its RAM code at a fixed address, so the pc is
>   stable across boots.
> - **Not every pc is a backward branch.** Where a wait loop hops rather than branching
>   straight back (Super Mario Advance takes three hops), the pc is a landing point inside
>   the loop. Same reason it works: the loop executes it every iteration.
>
> The 48 "no wait loop" games are a verdict, not a gap. The clearest case is the Classic
> NES / Famicom Mini / Hudson carts: they are 6502 interpreters, their hot code is a
> jump-table dispatch in IWRAM, and they spend the whole frame emulating a NES. No address
> exists that would make them lighter.

```bash
# in game-and-what
python3 scripts/gen_gba_over.py --c > firmware/gba/gba_idle_loop.c   # the C table
python3 scripts/gen_gba_over.py                                      # gba_over.h entries
python3 scripts/gen_gba_over.py --korean                             # just the Korean games
```

`scripts/gba_idle_loop_db.json` is the source of truth. Fields that matter:

| field | meaning |
|---|---|
| `idle_verified` | the **backward BRANCH** pc — what gpSP compares against |
| `verify_tier` | `R` = the game was RUN and demonstrably does less work with this address. **The only tier that ships.** Anything else is a guess. |
| `exec_median` / `exec_p90` | cycles of real CPU work per frame with the skip active, out of 280,896 |
| `verify_how` | how it was settled, e.g. `A/B: 48% less work with the address` |

### How an address earns its place

Three filters, and each one killed addresses that the previous one let through:

1. **The detector finds a backward branch.** 111 of them, across 633 roms.
2. **Does gpSP actually skip on it?** Run the game with that address and watch the
   cycle count. **17 died here** — the loop is real, the skip does nothing, the frame
   stays full. mGBA's detector is not an oracle.
3. **Does the address do any WORK?** This is the one that matters, and the obvious
   check misses it. "exec is below a full frame" proves nothing: a game that already
   waits via the BIOS sits far below a full frame *no matter what address you hand it*,
   so a bogus one sails straight through. The only honest test is the **difference** —
   run with the skip off, run with the address, keep it only if the game measurably
   does less. **5 more died here**, all at a 0% drop: KOF EX2 (×2), Ghost Trap, Space
   Invaders, F-Zero Climax.

89 survive. Every one has a measured drop behind it.

> One of those five only surfaced after fixing a bug in the harness itself: it looked
> roms up **by filename**, and this library renames files, so F-Zero Climax's address
> was being A/B'd against a different game entirely — and passed. **Match on the cart
> header. Never the name.** It is the same lesson the Korean patches teach (§ below),
> and it was walked into twice.

### The 13 Korean games — measured

`exec` = real CPU work per frame with the skip **active**, out of a 280,896-cycle frame.
The CPU budget on the M7 at a 340 MHz OC is roughly **160,000 cycles** (that figure is the
project's own estimate — see §5).

| game | code | `idle_loop_target_pc` | exec (median) | p90 | idle |
|---|---|---|---|---|---|
| 다운타운 열혈물어EX | `BDTE` | `0x800065a` | 55,917 | 276,959 | 80% |
| 포켓몬 사파이어 | `AXPK` | **none needed** (BIOS halt) | 72,648 | 90,930 | 74% |
| 포켓몬 루비 | `AXVK` | **none needed** (BIOS halt) | 73,266 | 91,087 | 74% |
| 포켓몬 리프그린 | `BPGE` | `0x80008c6` | 74,872 | 115,306 | 73% |
| 캐슬바니아 - 서클 오브 더 문 | `AAMJ` | `0x80003ce` | 76,369 | 153,710 | 73% |
| 포켓몬 파이어레드 | `BPRE` | `0x80008c6` | 76,509 | 132,138 | 73% |
| 리듬세상 | `BRIJ` | `0x80013d4` | 78,061 | 121,983 | 72% |
| 포켓몬 에메랄드 | `BPEK` | `0x80008ce` | 78,294 | 120,515 | 72% |
| 파이널 판타지 택틱스 어드밴스 | `AFXJ` | `0x8000428` | 116,375 | 280,289 | 59% |
| 록맨 제로 4 | `B4ZJ` | `0x8000914` | 119,971 | 165,681 | 57% |
| 슈퍼마리오월드 | `AA2C` | `0x80005ec` | 137,516 | 280,695 | 51% |
| 메이드 인 와리오 | `AZWJ` | `0x8000f5e` | 140,911 | 162,699 | 50% |
| 록맨 제로 3 | `BZ3J` | `0x80019c4` | 142,669 | 176,478 | 49% |

Note this is only the Korean subset. The table ships **89 addresses in total**, from
sweeping all 633 roms of the source library — see "How an address earns its place"
above. Nothing in it was guessed: an address that had only been *inferred* turned out
to be wrong the moment it was finally executed (Prince of Persia, `BPYP`: our own table
said `0x808fff6`, the game says `0x80900f2`).

### gpSP's own table is wrong in three places

All three confirmed by disassembling the ROM **and** by running it.

| code | game | gpSP `gba_over.h` says | actually |
|---|---|---|---|
| `BPRE` | Pokémon FireRed | `0x80008b2` — **no loop there** | `0x80008c6` |
| `BPGE` | Pokémon LeafGreen | `0x80008b2` — **no loop there** (ReGBA is wrong too) | `0x80008c6` |
| `APDE` | Pinball of the Dead | `0x800030` — **outside ROM space** (`0x8000000+`) | `0x8000300` (a digit was dropped) |

The override in §2.1 fixes these without touching gpSP.

### Ruby and Sapphire need no entry

They have **no busy-wait loop at all**. They wait via BIOS `SWI 5`/`SWI 2`
(IntrWait/Halt), and gpSP already fast-forwards a halted CPU (`cpu.cc:1499`,
`update_gba()`). Measured 74k cycles/frame, 74% idle, with no idle-loop entry. They are not
slow — there is simply nothing to skip.

---

## 4. RAM — the wall that comes BEFORE the idle loop

`RAM_EMU` is **724 KB (741,376 B)** and holds the core's text+rodata+data **and** its BSS
(`STM32H7B0VBTx_SDCARD.ld:74,105` — `__RAM_EMU_LENGTH__ = 1024K - __RAM_UC_LENGTH__`, the
300 KB being the LCD framebuffer pool; the heaviest existing cores already sit at 94–99.8%).

gpSP's static memory, as shipped:

| | |
|---|---|
| `ewram[1024*256*2]` | 512 KB |
| `iwram[1024*32*2]` | 64 KB |
| `vram[1024*96]` | 96 KB |
| `gamepak_backup[1024*128]` (save) | 128 KB |
| `bios_rom[1024*16]` | 16 KB |
| `open_gba_bios` in `.data` (`bios_data.S`) | 16 KB |
| palette / OAM | 3 KB |
| **total** | **835 KB** |

**111 KB over budget before a single byte of code**, and gpSP's JIT wants another
2.4 MB (`SMALL_TRANSLATION_CACHE`: 2 MB ROM cache + 384 KB RAM cache, `gpsp_config.h:15-20`).

### The levers, in the order they should be pulled

1. **BIOS → flash. Free, no downside. Do this first.**
   `bios_data.S` puts the open BIOS in `.data` (i.e. RAM), and gpSP then `memcpy`s it into
   the `bios_rom[16K]` BSS array (`libretro.c:1200,1213`). `open_gba_bios_rom` is only ever
   a memcpy **source** — never written. Move it to `.rodata`, point the 0x0 region straight
   at it, drop the BSS copy: **−32 KB**.
   *(And note: no BIOS file for the user to supply. gpSP embeds `bios/open_gba_bios.bin`
   via `.incbin` and falls back to it automatically — unlike pcecd/videopac/c64.)*

2. **Save → SD.** `gamepak_backup` is 128 KB. AHB SRAM is 120 KB, so it does not fit there;
   it has to stream. **−128 KB**.

3. **gpSP's code → XIP from external flash**, the `sm.xip` trick already in the tree
   (`SM_CODE : ORIGIN = 0xDEAD0000`, `store_file_in_flash_relocate()`). Frees ~250–300 KB.

With 1+2+3: 675 KB of BSS against 724 + 64 (ITCM) + 120 (AHB) = 908 KB → **~233 KB left for
the JIT cache.** That is far under gpSP's default, but the cache flushes and recompiles when
full — it *works*, it just gets slower.

4. **Last resort: drop the `ewram`/`iwram` doubling** (−288 KB → ~521 KB of JIT cache).
   **Understand what you are giving up.** The upper halves are the JIT's dirty map for code
   executing out of RAM (`cpu_threaded.c:3370,3397` memset `&ewram[0x40000]`). GBA games
   routinely copy hot loops into IWRAM and run them there — Pokémon included. Without the
   map you must recompile or interpret that code, and the CPU headroom we measured
   (79k of a 160k budget) can evaporate. **Try 1–3 first and see whether Pokémon runs.**

---

## 5. What is NOT verified — read before trusting the numbers

- **Nothing here ran on real hardware.** All cycle counts come from mGBA on a PC.
- **The 160,000-cycle budget is the project's own estimate, and the device says it is too
  generous.** The port's own DWT timings (`gnw-gba`, `1eec5c72` and `f08cfd6c`) split the
  16.67 ms frame as `Emulate 12.3 / Draw 4.1` and, after the renderer moved,
  `Emulate 7.58 / Draw 9.08`. Ruby measures 73,266 cycles here, so the M7 is spending
  ~103–168 ns per emulated GBA cycle — and whatever Draw leaves is what the CPU gets. Back
  out the arithmetic and the real budget is **roughly 73k–121k cycles, not 160k**, and it
  moves with the player's scaling/filter setting because that is what Draw costs. Every
  "within budget" verdict in this repo is optimistic by something like 1.3–2.2×. Pin the
  number by timing ONE known game on the device before trusting any of them.
- **The measurements describe what the bot reached.** It presses START/A/B, the d-pad and
  the shoulders, and gets through intros and early play — not a Pokémon battle, not a
  late-game boss. The p90 column is the honest warning: several games already touch a full
  frame in the window we sampled.
- **The RAM figures in §4 are static arithmetic**, not a link. The linker's `ASSERT` is the
  only authority.
- **`verify_tier: B` entries are guesses.** They are addresses found by rescanning near a
  known-wrong one and never confirmed by running the game. Do not ship them without running
  them first (see §6).

---

## 6. How to check an address is actually right

**The cycle count is the arbiter, not the detector.** This is not theoretical — mGBA's
detector picked `0x80016d4` for 슈퍼마리오월드 (`AA2C`), and feeding gpSP that address skips
nothing: the frame stays pinned at 280,896 cycles. The real loop is at `0x80005ec`.

```bash
# in game-and-what — see scripts/idlefind/README.md for the build
./idlefind rom.gba 1800 0x80005e6      # the loop's START (not the branch)
```

If `exec_median` does not **drop well below 280,896**, the address is wrong. A ROM whose
loop is never found reports ~280,896 — a full frame — which reads as "heavy game" but means
"loop not found". Four of these looked heavy for exactly that reason and turned out to idle
73% of the frame once given the right address.

---

## 7. Where everything lives (in `game-and-what`)

| path | what |
|---|---|
| `scripts/gba_idle_loop_db.json` | the measured database — source of truth |
| `scripts/gen_gba_over.py` | → paste-ready `gba_over.h` entries for the 13 Korean games |
| `scripts/gba_idle_match.py` | reads a ROM's header, reports/copies the ones the table covers |
| `scripts/idlefind/README.md` | **read this first** — how the harness works and how it lies |
| `scripts/idlefind/idlefind.c` | the harness: detect the loop + count per-frame cycles |
| `scripts/idlefind/shot.c` | render a frame headless — the only way to spot a Korean patch |
| `scripts/idlefind/mgba-cycle-counter.patch` | the `ARMRunLoop` instrumentation |
| `backend/korean_gba.py` | which 13 roms are Korean, and the on-screen evidence for each |
| `backend/import_gba.py` | rom import; sets `roms.idle_loop` from the header code |
| `backend/app/services/gba_probe.py` | the upload path: look the header up, run the game only if it is new |
| `backend/gba_measure.py` | push the table's numbers onto the library's rows |
| `backend/gba_export.py` | pull roms measured live by the upload prober back INTO the table |
| `firmware/gba/gba_idle_loop.{c,h}` | **what the firmware copies.** Generated — never hand-edit |
| `Dockerfile` (`gba-probe-builder`) | builds `idlefind` into the image, mGBA pinned |

### It measures on upload, too

A GBA rom uploaded to the library resolves itself: the header is looked up in the table
(instant, and a rename cannot fool it), and only a game we have never seen is actually
run — in the background, one at a time, with the card showing `측정 중` until it lands.
Anything measured that way can be folded back into the shared table with
`backend/gba_export.py --write`, and then into the firmware with `gen_gba_over.py --c`.
