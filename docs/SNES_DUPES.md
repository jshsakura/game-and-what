# SNES duplicates — why a 2,281-cart library had the same games in it twice

> The tool is `backend/snes_dupes.py` (read-only; `--json` feeds a review page).
> This document is the **result**: what was actually in there, how the same cart was
> told apart from a different one, and what was removed on 2026-07-31.

## The fact the whole cleanup turns on

**Not one pair of files was byte-identical.** Every `content_hash` in the library is
unique — across all 4,946 roms, not just SNES. So "duplicate" here never meant a file
copied twice; `backend/dedup_hash.py` already collapses that case and it found nothing.

What it meant was this:

```
혼두라 스피리츠 (Contra Spirits).smc      1024KB  crc B8CFE377
혼두라 스피릿츠.smc                       1024KB  crc EA97F25E
```

Two different dumps of one cartridge, sitting under two spellings of one title. The
library is named from **two Korean sources** — the curated `한글 (English)` dataset and a
blog-derived list of bare 한글 names — and when both had a game, both entries landed.

That is why the filename cannot be the identity. The cart's own header can:

| what the header gives | why it identifies the cart |
|---|---|
| internal title (21 bytes) | the name the cart calls itself, before anyone renamed it |
| ROM size | 4 Mbit is not 8 Mbit, whatever the label says |
| destination byte (`+0x19`) | 일본 / 미국 / 유럽 — a region, not a guess |

`snes_dupes.py` groups on **title + size**, then reads the destination byte from
`0x7fc0` (LoROM) or `0xffc0` (HiROM) to say what each dump is.

## What the region byte changed

The first pass ignored region and proposed 77 deletions. Reading the byte turned up
**일본 89 · 미국 52 · 유럽 16 · 기타 4**, and most "duplicates" were a Japanese and a US
dump of one game. Those are two releases. Keeping one throws a release away, which is a
different decision from removing a redundant copy — so the tool now proposes dropping
**at most one per region**, and the count fell 77 → 26.

## Why the header alone is not enough

A bootleg keeps its host cart's header. So does a hack:

```
CHESTER CHEETAH 1024KB   체스터 치타 (Chester Cheetah - Too Cool to Fool)
CHESTER CHEETAH 1024KB   바나나 인 파자마 (Bananas de Pijamas)      ← Brazilian bootleg
Super Metroid  4096KB    슈퍼 메트로이드 (Super Metroid)
Super Metroid  4096KB    아레나.smc                                 ← a hack
```

Header, size and region all agree; the games do not. So an entry whose name reads
nothing like the one being kept is never proposed for deletion — it is flagged
`⚠확인` and left alone. Same for anything marked as a Korean patch, a hack, a beta, a
version number, or a competition cart: those pairs exist **on purpose**.

## The four buckets

| bucket | what it is | default |
|---|---|---|
| `subtitle` | same title written to different lengths — `플래시백` / `플래시백 - 아이덴티티를 찾아서` | one per region |
| `unclear` | same cart, unrelated names — `소년 축구단 5` / `캡틴 츠바사 5`, foreign release names | one per region, dissimilar ones flagged |
| `patch` | 한글패치 + its original | keep both |
| `hack` | hacks, betas, competition carts | keep both |

## What was removed (2026-07-31)

The library went **2,281 → 2,210** SNES entries in three passes, all through the API, so
every file is in `_trash` and the activity feed can restore it for 30 days. DB backup:
`backend/data/gnw.db.bak.20260730`.

| pass | count | rule |
|---|---|---|
| raw English dump beside its Korean-named twin | 14 | `Aladdin (U) [!].smc` → the `알라딘 (Aladdin).smc` entry stays |
| `(2)` / `(3)` re-upload suffixes | 14 | same name, same size (or an unparsable header) |
| same cart, transliteration only | 43 | one curated entry, bare-name copies dropped |

Plus 7 renames where the `(n)` suffix outlived its sibling, and 3 Odyssey² rows whose
files had gone missing (`videopac` 94 → 91, matching the folder exactly).

One rename was wrong and is worth recording: a file named `악마성 드라큘라 XX … (3)` was
kept as "a different-size dump of XX". Its header says `AKUMAJO DRACULA`, 1 MB, 일본 —
it is a second dump of **Super Castlevania IV**, not of Dracula XX (2 MB,
`DRACULA XX`). Renamed to `악마성 드라큘라 (Akumajou Dracula) (다른 덤프).smc`. The
header answers questions the filename only guesses at; ask it first.

## What is still there

**78 groups / 165 entries**, because they need a person: 26 are same-region duplicates the
tool would drop, and the rest are region variants, patches and hacks. Re-run any time:

```bash
docker exec game-and-what sh -c 'cd /app/backend && python3 snes_dupes.py'
```

Deleting goes through the app, never the DB directly — that is what puts the file in
`_trash`, moves the cover with it, and writes the `rom_delete` event the feed restores from:

```bash
curl -X DELETE localhost:38081/api/sessions/public/roms/<id>
```

## Notes for the next sweep

- SNES is not shipping to the card anyway: 2,208 of 2,210 entries are `sd_exclude=1`. This
  is library hygiene, not SD content — the zip is unchanged by all of it.
- `(2)`-style suffixes exist **only** on SNES. Every other system was clean, and the one
  GBC hit (`1942 (1942).gbc`) is a real title whose English name is a number.
- The generic header titles (`SFC`, `SFX 1`, `ADD-ON BASE CASSETE`, `SUPER MARIOWORLD`)
  identify nothing — 30 Mario World hacks share the last one — and are skipped.
