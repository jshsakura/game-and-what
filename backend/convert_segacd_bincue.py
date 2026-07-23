"""One-off: convert the flat .chd Sega CD roms into folder-per-game .cue +
per-track .bin sets, matching the pcecd convention exactly (real hardware CD
I/O — when the segacd firmware port gets that far — reads bin/cue via FatFs,
NOT chd; browser play already works fine with either).

Pipeline per game: chdman extractcd (chd -> single combined bin+cue) ->
binmerge -s (split into per-track bins, redump-style) -> rename tracks to
zero-padded "(Track NN).bin" (binmerge emits unpadded "(Track N).bin") ->
move into roms/segacd/<game>/ -> update the DB row to the folder-upload shape
(rom_path -> the .cue, extra_files -> the track list) -> delete the old .chd
and all temp files. Sequential, one game at a time, to keep peak disk usage
bounded (~2x one game's size, not 2x the whole library).
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from app import db, config
from app.services import storage, name_index

SESSION = "public"
SYSTEM = "segacd"
BINMERGE = "/tmp/binmerge.py"

root = storage.session_root(SESSION)
rom_dir = root / "roms" / SYSTEM
tmp_root = config.DATA_DIR / "tmp" / "segacd_convert"
tmp_root.mkdir(parents=True, exist_ok=True)

TRACK_RE = re.compile(r"^(.*) \(Track (\d+)\)\.bin$")


def convert_one(chd_path: Path) -> tuple[str, list[dict]]:
    """Returns (cue_filename, [{"name":..., "size":...}, ...]) for the tracks."""
    game = chd_path.stem
    work = tmp_root / game
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    combined_cue = work / "combined.cue"
    r = subprocess.run(
        ["chdman", "extractcd", "-i", str(chd_path), "-o", str(combined_cue)],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"chdman failed: {r.stderr[-500:]}")

    split_dir = work / "split"
    r = subprocess.run(
        [sys.executable, BINMERGE, "-s", "-o", str(split_dir), str(combined_cue), game],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"binmerge failed: {r.stderr[-500:]}")

    # binmerge names tracks "(Track N).bin" (no zero-pad) — rename to "(Track NN).bin"
    # to match the pcecd convention, and rewrite the cue's FILE lines to match.
    split_files = sorted(split_dir.iterdir())
    cue_file = next(f for f in split_files if f.suffix == ".cue")
    renames: dict[str, str] = {}
    for f in split_files:
        if f.suffix != ".bin":
            continue
        m = TRACK_RE.match(f.name)
        if not m:
            continue
        base, num = m.groups()
        new_name = f"{base} (Track {int(num):02d}).bin"
        if new_name != f.name:
            renames[f.name] = new_name
            f.rename(f.with_name(new_name))

    cue_text = cue_file.read_text(encoding="utf-8")
    for old, new in renames.items():
        cue_text = cue_text.replace(f'"{old}"', f'"{new}"')
    final_cue_name = f"{game}.cue"
    cue_file.write_text(cue_text, encoding="utf-8")
    if cue_file.name != final_cue_name:
        cue_file.rename(cue_file.with_name(final_cue_name))

    # Move the whole split_dir content into the real roms/segacd/<game>/ folder.
    game_dir = rom_dir / storage.safe_name(game)
    if game_dir.exists():
        raise RuntimeError(f"target folder already exists: {game_dir}")
    game_dir.mkdir(parents=True)
    tracks = []
    for f in split_dir.iterdir():
        dest = game_dir / f.name
        f.rename(dest)
        if f.suffix == ".bin":
            tracks.append({"name": f.name, "size": dest.stat().st_size})
    tracks.sort(key=lambda t: t["name"])

    shutil.rmtree(work, ignore_errors=True)
    return final_cue_name, tracks


def main():
    chds = sorted(p for p in rom_dir.iterdir() if p.suffix.lower() == ".chd")
    print(f"{len(chds)} .chd files to convert")
    ok = fail = 0
    for i, chd_path in enumerate(chds, 1):
        game = chd_path.stem
        print(f"[{i}/{len(chds)}] {game}")
        try:
            cue_name, tracks = convert_one(chd_path)
        except Exception as e:
            print(f"  FAILED: {e}")
            fail += 1
            continue

        game_dir = storage.safe_name(game)
        cue_path = rom_dir / game_dir / cue_name
        rom_rel = f"roms/{SYSTEM}/{game_dir}/{cue_name}"
        content_hash = name_index.hash_bytes(cue_path.read_bytes())

        with db.connect() as conn:
            row = conn.execute(
                "SELECT id FROM roms WHERE session_id=? AND system_key=? AND rom_path=?",
                (SESSION, SYSTEM, f"roms/{SYSTEM}/{chd_path.name}")).fetchone()
            if not row:
                print(f"  WARN: no matching DB row for {chd_path.name}, leaving folder as-is")
                fail += 1
                continue
            conn.execute(
                """UPDATE roms SET stored_name=?, rom_path=?, extra_files=?, content_hash=?
                   WHERE id=?""",
                (cue_name, rom_rel, json.dumps(tracks), content_hash, row["id"]),
            )
        chd_path.unlink()
        print(f"  OK: {len(tracks)} tracks, {sum(t['size'] for t in tracks) / 1e6:.0f} MB")
        ok += 1

    shutil.rmtree(tmp_root, ignore_errors=True)
    print(f"\ndone: {ok} converted, {fail} failed")


if __name__ == "__main__":
    main()
