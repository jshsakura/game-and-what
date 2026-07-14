# data/ — the parts of this project that are worth having on their own

Without a dictionary, this is a file manager. `names.ko.json` is the dictionary: **1,908
Korean game names, keyed by the SHA-256 of the ROM's contents.** It is months of matching
— by list, and by hand — and it is the one thing a fresh install cannot work out for
itself. So it ships here rather than living only in my database.

```
{ "hash": "004ec2…", "system": "a2600", "name": "…",
  "original_name": "…the filename it arrived under…", "source": "atari-collection" }
```

## No ROMs move, and nothing here is about anybody

A hash is a fingerprint, not a file. You hash your own ROM, you get a name back. **No ROM
is distributed, and none can be reconstructed from this.**

The safety of it is the *shape of the table*, not any scrubbing: `rom_names` has no
session, no path, no filename of mine, no timestamp. Everything that would describe my
library rather than a game lives in other tables and never leaves them — the activity log
(`events`, which is a behavioural trace), personal media (`music`, `videos`), uploads, and
on `roms` the paths, stored names, favourites and SD in/exclude flags. Those are my
choices; these are facts.

`backend/tests/test_dataset.py::test_export_leaks_nothing_personal` pins that. If someone
adds a column to `rom_names` later, that test is what fails.

**Two things are deliberately NOT here, and neither is for privacy:**

- **Cover images.** We record where a cover came from (`cover_source`), never the file.
  Fetch your own from libretro-thumbnails / SteamGridDB / IGDB.
- **IGDB scores.** They are IGDB's data under IGDB's terms, not ours to redistribute.

`source` travels with every row, so provenance is per-name, not a blanket claim:
`localize-2026-06` (987), `atari-collection` (740), `manual` (111, hand-fixed), `꿀렁` …

## Use it

```bash
# seed a database from it (a Korean deploy does this automatically at startup, once,
# only while rom_names is empty — see app/services/dataset.py)
python3 backend/dataset_cli.py import data/names.ko.json

# regenerate it after naming more games
python3 backend/dataset_cli.py export
```

Merging is **additive and idempotent** (`INSERT OR IGNORE`): a name you fixed by hand
always outranks anything a file says, so importing an update can never undo your work.

## A limit worth knowing

**A hash is per-dump.** A different dump of the same game hashes differently and will
miss. That is why `original_name` rides along — `name_index.lookup_by_name()` falls back
to `(system, original filename)` — and why, for a system that has a stable identifier of
its own, that identifier is the better key. GBA is the example: its table
(`scripts/gba_idle_loop_db.json`) is keyed on the **cart header code** at `rom[0xAC]`,
which survives redumps and renames alike.

## Not built yet: serving this from a server

A read-only `GET /api/dataset/names` would let anyone pull the current dictionary from a
running instance instead of waiting for a release, and let an install refresh itself. It
was written and then pulled back out, because publishing an endpoint is a decision about
*hosting*, not about data:

- it must be session-less and public, so it needs its own answer on abuse and rate limits;
- this deploy sits behind Cloudflare Access, which would have to let that one path through;
- and once a URL exists, people pin to it — so the format and the promise to keep serving
  it are the actual commitment, not the code.

The export itself is already the hard part and it is done (`app/services/dataset.py` builds
the payload; `dataset_cli.py` writes it). Serving it is a router on top when the hosting
question has an answer.
