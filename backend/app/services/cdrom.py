"""Server-side CD extraction. Disc sectors are never patched or rewritten."""
from __future__ import annotations

import asyncio
from pathlib import Path
import re
import shutil
import subprocess

from fastapi import HTTPException

from .. import config

CD_SYSTEMS = frozenset({"segacd", "pcecd"})


def _extract(source: Path, output: Path) -> list[dict]:
    executable = shutil.which("chdman")
    if not executable:
        raise HTTPException(status_code=503, detail="chdman not installed on server (install mame-tools)")
    try:
        result = subprocess.run(
            [executable, "extractcd", "-f", "-i", str(source), "-o", str(output), "--splitbin"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=3600,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=422, detail="CHD conversion timed out")
    if result.returncode:
        raise HTTPException(status_code=422, detail="CHD conversion failed: " + result.stderr.decode(errors="replace")[-1000:])
    if not output.is_file():
        raise HTTPException(status_code=422, detail="CHD conversion produced no CUE")
    refs = re.findall(r'^\s*FILE\s+"([^"]+)"\s+BINARY\s*$', output.read_text(), re.MULTILINE | re.IGNORECASE)
    if not refs or len(refs) != len(set(refs)):
        raise HTTPException(status_code=422, detail="CHD conversion produced invalid track references")
    extra = []
    cue_text = output.read_text()
    total = output.stat().st_size
    for index, name in enumerate(refs, 1):
        track = output.parent / name
        if Path(name).name != name or "\\" in name or not name.lower().endswith(".bin") or not track.is_file():
            raise HTTPException(status_code=422, detail="CHD conversion produced a missing or invalid BIN")
        size = track.stat().st_size
        if not size or size % 2352:
            raise HTTPException(status_code=422, detail="CHD conversion produced a non-raw track (expected 2352-byte sectors)")
        total += size
        if size > config.MAX_CD_FILE_BYTES or total > config.MAX_CD_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="Extracted CD exceeds configured size limits")
        # chdman versions may emit Track 1 or Track 01. Use stable two-digit
        # names; only CUE references and filenames change, never BIN contents.
        canonical = f"{output.stem} (Track {index:02d}).bin"
        if name != canonical:
            track.rename(output.parent / canonical)
            cue_text = cue_text.replace(f'"{name}"', f'"{canonical}"')
        extra.append({"name": canonical, "size": size})
    output.write_text(cue_text)
    return extra


async def extract_chd(source: Path, output: Path) -> list[dict]:
    # chdman runs in a worker so uploads do not block the ASGI event loop.
    worker = asyncio.create_task(asyncio.to_thread(_extract, source, output))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        # Let chdman stop before the caller removes its staging directory.
        try:
            await worker
        finally:
            raise


async def convert_library_chd(session_id: str, rom_id: str) -> dict:
    """Convert an existing entry in place, retaining its ID, metadata and cover.

    The CHD stays intact until extraction, file promotion and DB commit succeed.
    This is shared by the library action and the offline cleanup tool.
    """
    import json
    import os
    from .. import db
    from . import covers, storage

    with db.connect() as conn:
        row = conn.execute("SELECT * FROM roms WHERE id=? AND session_id=?", (rom_id, session_id)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="ROM not found")
        rom = dict(row)
    if rom["system_key"] not in CD_SYSTEMS or Path(rom["rom_path"]).suffix.lower() != ".chd":
        raise HTTPException(status_code=400, detail="This entry is not a CD CHD")
    root = storage.session_root(session_id)
    source = root / rom["rom_path"]
    if not source.is_file():
        raise HTTPException(status_code=409, detail="CHD missing from disk")
    source_stat = source.stat()
    roms_root = storage.roms_dir(session_id, rom["system_key"])
    # Existing folder games keep their directory; flat CHDs gain their own.
    final = source.parent if source.parent != roms_root else roms_root / storage.safe_name(source.stem)
    if source.parent == roms_root:
        base = final.name
        n = 2
        while final.exists():
            final = roms_root / f"{base} ({n})"
            n += 1
    stage = roms_root / f".incoming-{storage.new_id()}"
    stage.mkdir(parents=True)
    output = stage / f"{final.name}.cue"
    promoted = []
    created_folder = False
    try:
        extra = await extract_chd(source, output)
        stored_name = output.name
        rom_rel = storage.relative_to_session(session_id, final / stored_name)
        cover_rel = rom["cover_path"]
        with db.connect() as conn:
            current = conn.execute("SELECT rom_path FROM roms WHERE id=? AND session_id=?", (rom_id, session_id)).fetchone()
            if current is None or current["rom_path"] != rom["rom_path"] or not source.exists():
                raise HTTPException(status_code=409, detail="ROM changed during conversion; original CHD kept")
            if not final.exists():
                final.mkdir()
                created_folder = True
            for path in stage.iterdir():
                target = final / path.name
                if target.exists():
                    raise HTTPException(status_code=409, detail="CUE/BIN already exists; original CHD kept")
                path.rename(target)
                promoted.append(target)
            # Covers normally share the CHD/CUE stem. Handle older mismatched
            # folder names too, without losing or overwriting existing artwork.
            if cover_rel:
                old_cover = root / cover_rel
                new_cover = storage.covers_dir(session_id, rom["system_key"]) / covers.cover_filename(stored_name)
                if old_cover.is_file() and new_cover != old_cover:
                    if new_cover.exists():
                        raise HTTPException(status_code=409, detail="Cover name already exists; original CHD kept")
                    shutil.copyfile(old_cover, new_cover)
                    promoted.append(new_cover)
                    cover_rel = storage.relative_to_session(session_id, new_cover)
            # A host cleanup tool may run as root while the app owns the library.
            # Preserve that ownership so later uploads and cover edits still work.
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                for path in promoted:
                    os.chown(path, source_stat.st_uid, source_stat.st_gid)
                if created_folder:
                    os.chown(final, source_stat.st_uid, source_stat.st_gid)
            conn.execute("UPDATE roms SET stored_name=?, rom_path=?, extra_files=?, cover_path=? WHERE id=?",
                         (stored_name, rom_rel, json.dumps(extra), cover_rel, rom_id))
    except BaseException:
        for path in promoted:
            path.unlink(missing_ok=True)
        if created_folder:
            final.rmdir()
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    # Commit has succeeded: the source is now redundant and may be removed.
    source.unlink()
    if cover_rel != rom["cover_path"] and rom["cover_path"]:
        (root / rom["cover_path"]).unlink(missing_ok=True)
    return {"rom_id": rom_id, "stored_name": stored_name, "rom_path": rom_rel,
            "tracks": len(extra), "removed_chd": True}
