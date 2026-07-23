"""ROM upload → metadata/Korean name → cover (186x100 .img) → persist."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import config, db
from ..systems import accepts_extension, get_system
from ..services import covers, covers_pico8, cps1 as cps1_svc, events, gamelist, gba_probe, langtag, metadata, name_index, patchver, pico8_compat, pico8_memhint, romcheck, romtag, storage
from .sessions import require_session, require_system_enabled

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["roms"])


def _pico8_cover(rom_path: Path) -> bytes | None:
    """PICO-8 label art, rendered from the cart itself — the only cover made inline
    at upload (no network, so it's fast even for a big batch). Every other system's
    art is fetched by the background autofill."""
    try:
        return covers_pico8.render_pico8_cover(rom_path)
    except covers.CoverError:
        return None


@router.post("/sessions/{session_id}/roms")
async def upload_roms(
    session_id: str,
    system: str = Form(...),
    files: list[UploadFile] = File(...),
) -> dict:
    """Bulk-upload ROMs for one system. Each is named, covered, and stored."""
    # Upload to the SELECTED system (the tab the user chose).
    try:
        sys_obj = get_system(system)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown system: {system}")
    require_system_enabled(sys_obj)

    with db.connect() as conn:
        require_session(conn, session_id)

    # Auto-naming source: cached 꿀렁 lists for this system (re-parsed only when
    # DATA changes — keeps repeated uploads cheap).
    gl_regex, gl_by_eng, gl_by_kor = gamelist.get_sources(session_id, sys_obj.key)

    results = []
    pending_cover: list[dict] = []   # roms still without a cover → background autofill
    pending_probe: list[dict] = []   # GBA roms whose idle loop/frame cost must be measured
    for upload in files:
        # NFC at the very entry boundary so every derived name (metadata, stored,
        # cover) is composed — NFD uploads (macOS) would otherwise show broken jamo.
        original = storage.nfc(upload.filename) or "rom"
        if not accepts_extension(sys_obj, original):
            results.append({"name": original, "ok": False, "error": "extension not accepted"})
            continue

        data = await upload.read()
        if len(data) > config.MAX_ROM_BYTES:
            results.append({"name": original, "ok": False, "error": "too large"})
            continue

        # EXACT-duplicate guard: if the same bytes already exist in this session,
        # keep the existing entry (it may already be Korean-named) and skip this one.
        chash = name_index.hash_bytes(data)
        with db.connect() as conn:
            dup = conn.execute(
                "SELECT stored_name FROM roms WHERE session_id = ? AND content_hash = ? "
                "AND system_key = ? LIMIT 1", (session_id, chash, sys_obj.key)).fetchone()
        if dup:
            results.append({"name": original, "ok": False, "error": "duplicate",
                            "duplicate_of": dup["stored_name"]})
            continue

        header_warning = romcheck.md_header_warning(sys_obj.key, data)

        meta = metadata.resolve_metadata(sys_obj.key, original)
        # Filename is kept AS UPLOADED — NO automatic Korean conversion (it caused
        # mismatches; Korean naming is now done manually by the user). Uploads only
        # store the original name + auto-fetch a cover. (꿀렁/name_index lookup is
        # intentionally not used here anymore.)
        stored_name = storage.safe_name(original)
        # The region tag lives in its own DB column — keep it OUT of the on-device
        # filename. (original_name below still preserves the full tagged name.)
        _, _cleaned = romtag.extract_region(stored_name)
        stored_name = _cleaned.strip() or stored_name
        rom_path = storage.roms_dir(session_id, sys_obj.dirname) / stored_name
        storage.write_bytes(rom_path, data)

        # Covers: Pico-8 renders LOCALLY from the cart (fast, no network). Every
        # other system fetches art over the NETWORK — far too slow to do inline
        # for a big batch (a 2000-file upload would fire thousands of sequential
        # requests and stall the whole upload). So only Pico-8 is made here; the
        # rest are deferred to the background autofill below — upload just saves
        # the file + resolved name fast, covers stream in as the library refreshes.
        cover_rel = None
        cover_status = "none"
        if sys_obj.pico8:
            cover_bytes = _pico8_cover(rom_path)
            if cover_bytes:
                cover_name = covers.cover_filename(stored_name)
                cover_path = storage.covers_dir(session_id, sys_obj.dirname) / cover_name
                storage.write_bytes(cover_path, cover_bytes)
                cover_rel = storage.relative_to_session(session_id, cover_path)
                cover_status = "ok"
                # Pico-8 preview = the 128x128 cart label as a 100x100 square.
                try:
                    prev = covers_pico8.render_pico8_preview(rom_path)
                    prev_path = storage.previews_dir(session_id, sys_obj.dirname) / (
                        Path(stored_name).stem + ".webp")
                    storage.write_bytes(prev_path, prev)
                except covers.CoverError:
                    pass

        # Language/패치/region come from the ORIGINAL filename — it still carries the
        # 'J-K' marker / region tag that the Korean stored_name no longer has.
        li = langtag.detect(original)
        region = romtag.region_of(original)

        # 한글패치 is a Korea-specific flag — only honor it in Korean mode.
        ko_patched = bool(li.is_korean_patched) and config.KOREAN_MODE

        # Default cover flag = filename-derived (한글패치→ko, else play/orig lang),
        # only if we have an asset for it. The user can change/clear it later.
        # In non-Korean mode, never auto-assign the 'ko' flag.
        _cf = ("ko" if ko_patched else (li.play_lang or li.orig_lang or "")).lower()
        if not config.KOREAN_MODE and _cf == "ko":
            _cf = ""
        cover_flag = _cf if _cf in covers.FLAG_CODES else None

        # A rom that still needs artwork goes out as 'pending', not 'none': the
        # background autofill below is about to look for it, and the UI polls that
        # state to turn a spinner into the cover the moment it lands.
        needs_cover = cover_status != "ok" and not sys_obj.pico8
        if needs_cover:
            cover_status = "pending"

        # A GBA rom's fate on the real device turns on a number its header does not
        # carry: whether gpSP knows its VBlank idle loop, and how much work it actually
        # does per frame. Finding that out means RUNNING the game (~15s), so it cannot
        # happen inside the upload — the rom lands 'pending' and _probe_gba fills it in.
        probe_status = "pending" if sys_obj.key == "gba" else None

        rom_id = storage.new_id()
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO roms (id, session_id, system_key, original_name,
                       stored_name, korean_name, rom_path, cover_path, cover_status,
                       orig_lang, play_lang, is_korean_patched, lang_source, region, cover_flag,
                       content_hash, crc32, pico8_compat, pico8_mem_hint, patch_ver, probe_status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rom_id, session_id, sys_obj.key, storage.nfc(meta.original_name), stored_name,
                 storage.nfc(meta.korean_name), storage.relative_to_session(session_id, rom_path),
                 cover_rel, cover_status,
                 li.orig_lang, li.play_lang, int(ko_patched), li.source, region, cover_flag,
                 chash, name_index.crc32_bytes(data, sys_obj.key),
                 pico8_compat.lookup(stored_name) if sys_obj.pico8 else None,
                 pico8_memhint.estimate(rom_path) if sys_obj.pico8 else None,
                 patchver.parse(original), probe_status),
            )
            events.log(conn, session_id, "rom_upload", rom_id=rom_id,
                       rom_name=stored_name, system_key=sys_obj.key)
        if needs_cover:
            pending_cover.append({
                "id": rom_id, "system_key": sys_obj.key, "stored_name": stored_name,
                "original_name": storage.nfc(meta.original_name),
                "korean_name": storage.nfc(meta.korean_name),
                "rom_path": storage.relative_to_session(session_id, rom_path),
                # Carry the flag so the BACKGROUND cover render bakes it in — without
                # this a freshly-fetched cover is baked flagless and a 한글패치 ROM
                # shows no 🇰🇷 until something re-bakes it.
                "cover_flag": cover_flag,
            })
        if probe_status == "pending":
            pending_probe.append({"id": rom_id, "rom_path": rom_path})
        results.append({
            "id": rom_id,
            "name": original,
            "ok": True,
            "system_key": sys_obj.key,
            "system_name": sys_obj.name,
            "stored_name": stored_name,
            "korean_name": meta.korean_name,
            "screenshot_url": meta.screenshot_url,
            "cover_status": cover_status,
            "probe_status": probe_status,
            "warning": header_warning,
        })

    # Auto-fetch covers asynchronously AFTER responding — the user doesn't wait,
    # covers appear as the library refreshes (no manual '자동 채우기' needed).
    if pending_cover:
        asyncio.create_task(_autofill_covers(session_id, pending_cover))
    if pending_probe:
        asyncio.create_task(_probe_gba(session_id, pending_probe))

    stored = sum(1 for r in results if r.get("ok"))
    return {"session_id": session_id, "stored": stored, "results": results}


async def _probe_gba(session_id: str, roms: list[dict]) -> None:
    """Background: work out whether each freshly-uploaded GBA rom can run on the device.

    A rom the database already knows is settled instantly; anything new is RUN for ~15s
    (see services/gba_probe). Serialised there, so a bulk upload measures one at a time
    instead of burying the box.

    Every rom here was stored probe_status='pending' and MUST leave it — 'ok' or
    'failed'. One left 'pending' would spin in the UI forever.
    """
    for rom in roms:
        status, idle_pc, cycles, drop, hunted = "failed", None, None, None, False
        audio_cycles = audio_variant = audio_name = None
        try:
            result = await gba_probe.probe(Path(rom["rom_path"]))
            if result:
                status = "ok"
                idle_pc, cycles = result.idle_pc, result.exec_cycles
                # Both of these are new facts the probe now has and the row must keep.
                # `idle_drop` is what the skip bought (the card shows it); `idle_hunted`
                # says we RAN this game and searched — so a full frame of work is the
                # game's own answer ("it is this heavy"), not the probe's failure to
                # measure it, and the UI must stop calling it "not measured".
                drop, hunted = result.idle_drop, result.hunted
                # The sound driver — set only on a table lookup (a live hunt leaves it None).
                # It is what makes the card's third ring, and the mixer HLE the device gets
                # for free, so a fresh upload that the table already knows shows it at once.
                audio_cycles = result.audio_cycles
                audio_variant, audio_name = result.audio_variant, result.audio_name
        except Exception:                                    # noqa: BLE001 — never wedge the queue
            log.exception("gba probe crashed for %s", rom["id"])

        try:
            with db.connect() as conn:
                conn.execute(
                    "UPDATE roms SET probe_status = ?, idle_loop = ?, idle_pc = ?, "
                    "exec_cycles = ?, idle_drop = ?, idle_hunted = ?, "
                    "audio_cycles = ?, audio_variant = ?, audio_name = ? "
                    "WHERE id = ? AND session_id = ?",
                    (status, int(bool(idle_pc)), idle_pc, cycles, drop, int(hunted),
                     audio_cycles, audio_variant, audio_name,
                     rom["id"], session_id),
                )
        except Exception:                                    # noqa: BLE001
            log.exception("could not store the gba probe for %s", rom["id"])


async def _autofill_covers(session_id: str, roms: list[dict]) -> None:
    """Background: best-effort IGDB/TheGamesDB cover for each freshly-uploaded rom.
    Paced (~4/s) to stay under IGDB's rate limit, with one retry pass for the
    transient failures a fast burst would otherwise drop.

    Every rom here was stored as cover_status='pending', so each one MUST end up
    resolved — 'ok' (autofill_rom sets it) or back to 'none'. A rom left 'pending'
    would spin in the UI forever and keep the library polling."""
    from .covers import autofill_rom
    still: list[dict] = []
    for rom in roms:
        try:
            if not await autofill_rom(session_id, rom):
                still.append(rom)
        except Exception:
            still.append(rom)
        await asyncio.sleep(0.25)
    for rom in still:                 # retry the ones that missed (often transient)
        found = False
        try:
            found = await autofill_rom(session_id, rom)
        except Exception:
            pass
        if not found:
            _settle_cover(rom["id"])
        await asyncio.sleep(0.25)


def _settle_cover(rom_id: str) -> None:
    """Clear a 'pending' rom that never got artwork, so the UI stops waiting."""
    with db.connect() as conn:
        conn.execute(
            "UPDATE roms SET cover_status = 'none' WHERE id = ? AND cover_status = 'pending'",
            (rom_id,),
        )


def _basename(rel: str) -> str:
    """Last path segment of a (possibly backslash) relative path, NFC-normalized."""
    return Path((storage.nfc(rel) or "").replace("\\", "/")).name


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


@router.post("/sessions/{session_id}/roms/cdfolder")
async def upload_cd_folder(
    session_id: str,
    system: str = Form(...),
    paths: str = Form(...),               # JSON list of webkitRelativePath, aligned to files
    files: list[UploadFile] = File(...),
) -> dict:
    """Folder-per-game upload for CD systems (e.g. PC Engine CD).

    The whole game folder is stored INTACT under roms/<dir>/<game>/ — a .cue plus
    its track files (.bin/.iso/.wav…), or a single .chd. One rom row is created:
    rom_path → the .cue/.chd, extra_files → the co-located tracks. The SD packager
    (tree walk) and per-rom download (parent-dir derivation) then ship the folder
    as-is. Track files keep their EXACT names so the .cue's FILE refs stay valid;
    everything is streamed to disk (CD images are large)."""
    try:
        sys_obj = get_system(system)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown system: {system}")
    require_system_enabled(sys_obj)
    with db.connect() as conn:
        require_session(conn, session_id)

    try:
        rel_paths = list(json.loads(paths))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid paths payload")
    if len(rel_paths) != len(files):
        raise HTTPException(status_code=400, detail="paths/files length mismatch")
    if not files:
        raise HTTPException(status_code=400, detail="No files")

    # Per-file basenames (kept EXACT — never safe_name'd — so .cue FILE refs work).
    names = [_basename(rel_paths[i]) or storage.nfc(f.filename) or f"track{i}"
             for i, f in enumerate(files)]
    # Primary = the .cue (preferred) or a single .chd; the game is built around it.
    primary_i = next((i for i, n in enumerate(names) if _ext(n) == "cue"), None)
    if primary_i is None:
        primary_i = next((i for i, n in enumerate(names) if _ext(n) == "chd"), None)
    if primary_i is None:
        raise HTTPException(status_code=400, detail="폴더에 .cue 또는 .chd가 없습니다")

    # Game folder = the dropped folder's top dir; fall back to the primary's stem.
    def _top(rel: str) -> str:
        norm = (storage.nfc(rel) or "").replace("\\", "/").strip("/")
        return norm.split("/", 1)[0] if "/" in norm else ""
    tops = [t for t in (_top(p) for p in rel_paths) if t]
    game = tops[0] if tops else Path(names[primary_i]).stem
    game_dir = storage.safe_name(game)
    roms_root = storage.roms_dir(session_id, sys_obj.dirname)
    # Write into a private staging dir first, then atomically rename into the final
    # game folder once we know it's not a duplicate — so a re-upload of an existing
    # game can NEVER clobber the live folder it shares a name with.
    stage_dir = roms_root / f".incoming-{storage.new_id()}"
    stage_dir.mkdir(parents=True, exist_ok=True)

    written: list[dict] = []
    total = 0
    h = hashlib.sha256()
    try:
        for i, upload in enumerate(files):
            name = names[i]
            if "/" in name or "\\" in name or name in ("", ".", ".."):
                raise HTTPException(status_code=400, detail=f"잘못된 파일명: {name}")
            target = stage_dir / name
            size = 0
            with target.open("wb") as out:
                while True:
                    chunk = await upload.read(1 << 20)
                    if not chunk:
                        break
                    size += len(chunk)
                    total += len(chunk)
                    if size > config.MAX_CD_FILE_BYTES:
                        raise HTTPException(status_code=413, detail=f"파일이 너무 큽니다: {name}")
                    if total > config.MAX_CD_TOTAL_BYTES:
                        raise HTTPException(status_code=413, detail="폴더가 너무 큽니다")
                    out.write(chunk)
                    if i == primary_i:
                        h.update(chunk)
            written.append({"name": name, "size": size})

        chash = h.hexdigest()
        primary_name = names[primary_i]
        with db.connect() as conn:
            dup = conn.execute(
                "SELECT stored_name FROM roms WHERE session_id = ? AND content_hash = ? "
                "AND system_key = ? LIMIT 1", (session_id, chash, sys_obj.key)).fetchone()
        if dup:
            shutil.rmtree(stage_dir, ignore_errors=True)
            return {"session_id": session_id, "stored": 0,
                    "results": [{"name": game, "ok": False, "error": "duplicate",
                                 "duplicate_of": dup["stored_name"]}]}

        # Promote staging → final folder, keeping a fresh name if one already exists
        # (same game, different content) so nothing is overwritten.
        final_dir = roms_root / game_dir
        n = 2
        while final_dir.exists():
            final_dir = roms_root / f"{game_dir} ({n})"
            n += 1
        os.rename(stage_dir, final_dir)
        game_dir = final_dir.name
    except BaseException:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise

    # Display name = the primary file's name (so rom_path basename == stored_name,
    # same invariant as cartridge uploads). Region tag stays in its own column.
    stored_name = primary_name
    rom_rel = f"{config.ROMS_DIR_NAME}/{sys_obj.dirname}/{game_dir}/{primary_name}"
    extra = [w for j, w in enumerate(written) if j != primary_i]

    li = langtag.detect(game)
    region = romtag.region_of(game)
    rom_id = storage.new_id()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO roms (id, session_id, system_key, original_name,
                   stored_name, korean_name, rom_path, cover_path, cover_status,
                   orig_lang, play_lang, is_korean_patched, lang_source, region,
                   cover_flag, content_hash, extra_files)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rom_id, session_id, sys_obj.key, storage.nfc(game), stored_name, None,
             rom_rel, None, "none", li.orig_lang, li.play_lang, 0, li.source, region,
             None, chash, json.dumps(extra)),
        )
        events.log(conn, session_id, "rom_upload", rom_id=rom_id,
                   rom_name=stored_name, system_key=sys_obj.key)

    asyncio.create_task(_autofill_covers(session_id, [{
        "id": rom_id, "system_key": sys_obj.key, "stored_name": stored_name,
        "original_name": storage.nfc(game), "korean_name": None, "rom_path": rom_rel,
    }]))

    return {"session_id": session_id, "stored": 1, "results": [{
        "id": rom_id, "name": game, "ok": True, "system_key": sys_obj.key,
        "system_name": sys_obj.name, "stored_name": stored_name,
        "tracks": len(extra), "cover_status": "none",
    }]}


@router.post("/sessions/{session_id}/roms/cps1")
async def upload_cps1_romsets(
    session_id: str,
    files: list[UploadFile] = File(...),
) -> dict:
    """Drop CPS-1 MAME romset ZIPs in — any number, in any combination.

    There is no parent/child slot to fill. Every archive is hashed, the chips are
    matched against the romset table by CRC32, and what comes out is one game per
    RELEASE, with this rule deciding which archives are games and which were only
    chip donors:

        a set that could not complete on its own borrowed chips, so it is the
        release being added; whatever it borrowed from was a donor.

    Upload a clone and its base release and you get the clone, once. Upload a base
    release alone and you get the base release. Two clones sharing one donor give
    two games, and EACH folder carries its own copy of the donor's chips, because
    a game folder the device can only read if a different folder still exists is a
    game that breaks the day that folder is deleted.

    The card gets loose chip dumps, never the zip: the firmware caches each chip
    into external flash and reads it in place, which needs raw chip bytes. The
    archives stay in the folder as the master copy (services/cps1.py explains why
    that is the right way round for a browser arcade core).
    """
    sys_obj = get_system("cps1")
    require_system_enabled(sys_obj)
    with db.connect() as conn:
        require_session(conn, session_id)
    if not files:
        raise HTTPException(status_code=400, detail="No files")

    roms_root = storage.roms_dir(session_id, sys_obj.dirname)
    stage = roms_root / f".incoming-{storage.new_id()}"
    stage.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    try:
        # 1) Land every archive in a staging dir. Nothing is judged until they
        #    are all here -- a clone is only recognisable next to its donor.
        staged: list[tuple[str, Path]] = []
        for upload in files:
            name = storage.nfc(upload.filename) or "romset.zip"
            name = Path(name).name
            if not name.lower().endswith(".zip") or name in ("", ".", ".."):
                results.append({"name": name, "ok": False, "error": "not a .zip"})
                continue
            target = stage / name
            size = 0
            with target.open("wb") as out:
                while True:
                    chunk = await upload.read(1 << 20)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > config.MAX_CD_FILE_BYTES:
                        raise HTTPException(status_code=413, detail=f"파일이 너무 큽니다: {name}")
                    out.write(chunk)
            staged.append((name, target))

        if not staged:
            shutil.rmtree(stage, ignore_errors=True)
            return {"session_id": session_id, "stored": 0, "results": results}

        try:
            games = cps1_svc.plan_games(staged)
        except Exception as exc:                       # a corrupt zip, say
            logging.warning("cps1: could not read an archive: %s", exc)
            games = []

        if not games:
            # Say WHICH set it nearly is and what is missing -- "unrecognised"
            # and "you are four chips short of wofj" look identical otherwise.
            ident = cps1_svc.identify(staged)
            shutil.rmtree(stage, ignore_errors=True)
            results.append({"name": ", ".join(n for n, _ in staged), "ok": False,
                            "error": "incomplete", "detail": ident.message()})
            return {"session_id": session_id, "stored": 0, "results": results}

        # 2) One folder per game, each self-contained.
        for game in games:
            title = game.title or game.setname
            folder = storage.safe_name(title)
            final_dir = roms_root / folder
            n = 2
            while final_dir.exists():
                final_dir = roms_root / f"{folder} ({n})"
                n += 1
            final_dir.mkdir(parents=True)
            for archive_name in game.archives:
                src = dict(staged)[archive_name]
                shutil.copy2(src, final_dir / archive_name)
            # Pre-build the device's chip folder NOW, once. The card build and
            # the device then read these loose <crc>.bin files straight; a
            # download copies them and never re-composes the set from the zips.
            # The zips stay for the browser core (it runs a MAME romset .zip) --
            # two forms of the same game, deliberately.
            cps1_svc.materialize_chips(final_dir)

            primary = game.archives[0]
            chash = hashlib.sha256((final_dir / primary).read_bytes()).hexdigest()
            rom_rel = f"{config.ROMS_DIR_NAME}/{sys_obj.dirname}/{final_dir.name}/{primary}"
            li = langtag.detect(title)
            rom_id = storage.new_id()
            with db.connect() as conn:
                dup = conn.execute(
                    "SELECT stored_name FROM roms WHERE session_id = ? AND content_hash = ? "
                    "AND system_key = ? LIMIT 1", (session_id, chash, sys_obj.key)).fetchone()
                if dup:
                    shutil.rmtree(final_dir, ignore_errors=True)
                    results.append({"name": title, "ok": False, "error": "duplicate",
                                    "duplicate_of": dup["stored_name"]})
                    continue
                conn.execute(
                    """INSERT INTO roms (id, session_id, system_key, original_name,
                           stored_name, korean_name, rom_path, cover_path, cover_status,
                           orig_lang, play_lang, is_korean_patched, lang_source, region,
                           cover_flag, content_hash, extra_files)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (rom_id, session_id, sys_obj.key, title, primary, None,
                     rom_rel, None, "none", li.orig_lang, li.play_lang, 0, li.source,
                     romtag.region_of(title), None, chash,
                     json.dumps(list(game.archives[1:]))),
                )
                events.log(conn, session_id, "rom_upload", rom_id=rom_id,
                           rom_name=primary, system_key=sys_obj.key)
            results.append({
                "id": rom_id, "name": title, "ok": True, "system_key": sys_obj.key,
                "system_name": sys_obj.name, "stored_name": primary,
                "romset": game.setname, "cover_status": "none",
                "donors": list(game.borrowed_from),
            })
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    return {"session_id": session_id,
            "stored": sum(1 for r in results if r.get("ok")), "results": results}


@router.post("/sessions/{session_id}/roms/{rom_id}/cdtracks")
async def add_cd_tracks(
    session_id: str, rom_id: str, files: list[UploadFile] = File(...)
) -> dict:
    """Add track file(s) to an existing CD game's folder — one (small) request at a
    time. CD folders total hundreds of MB, but the public tunnel (Cloudflare) caps
    a single request body at ~100 MB, so the client uploads the .cue via /cdfolder
    then streams each track here separately. Files land in the rom's OWN folder
    (rom_path's parent) with EXACT names (so the .cue's FILE refs resolve) and are
    appended to extra_files."""
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute("SELECT * FROM roms WHERE id=? AND session_id=?",
                           (rom_id, session_id)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="ROM을 찾을 수 없습니다")
        rom = dict(row)

    base = storage.session_root(session_id) / Path(rom["rom_path"]).parent
    base.mkdir(parents=True, exist_ok=True)
    primary_name = Path(rom["rom_path"]).name
    extra = _extra_list(rom)
    added = []
    for upload in files:
        name = _basename(upload.filename)
        if "/" in name or "\\" in name or name in ("", ".", ".."):
            raise HTTPException(status_code=400, detail=f"잘못된 파일명: {name}")
        if name == primary_name:
            continue                                   # never clobber the .cue/.chd
        target = base / name
        size = 0
        with target.open("wb") as out:
            while True:
                chunk = await upload.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > config.MAX_CD_FILE_BYTES:
                    out.close(); target.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail=f"파일이 너무 큽니다: {name}")
                out.write(chunk)
        extra = [e for e in extra if e.get("name") != name]   # replace if re-sent
        extra.append({"name": name, "size": size})
        added.append(name)

    with db.connect() as conn:
        conn.execute("UPDATE roms SET extra_files=? WHERE id=?", (json.dumps(extra), rom_id))
    return {"rom_id": rom_id, "added": added, "tracks": len(extra)}


@router.post("/sessions/{session_id}/roms/{rom_id}/replace")
async def replace_rom_file(
    session_id: str, rom_id: str, file: UploadFile = File(...)
) -> dict:
    """Swap the underlying ROM binary while keeping the same entry — name, cover
    and slot are untouched. Useful for a better dump / patched build of the same
    game. The new file's extension must be valid for the system."""
    with db.connect() as conn:
        require_session(conn, session_id)
        row = conn.execute(
            "SELECT * FROM roms WHERE id = ? AND session_id = ?", (rom_id, session_id)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="ROM not found in session")
        rom = dict(row)

    sys_obj = get_system(rom["system_key"])
    upload_name = storage.nfc(file.filename) or "rom"
    if not accepts_extension(sys_obj, upload_name):
        raise HTTPException(status_code=400, detail=f"{sys_obj.name}에 맞지 않는 확장자입니다")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다")
    if len(data) > config.MAX_ROM_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다")

    # Move the OLD file to _trash first (recoverable) — never destroy in place,
    # then write the new bytes at the same path (keep the stored filename + ext).
    storage.move_to_trash(session_id, rom["rom_path"])
    abs_path = storage.session_root(session_id) / rom["rom_path"]
    storage.write_bytes(abs_path, data)
    # Remember the NEW file hash → same name, so re-uploading it auto-resolves.
    with db.connect() as conn:
        name_index.store(conn, name_index.hash_bytes(data), rom["system_key"],
                         Path(rom["stored_name"]).stem, "replace")

    return {"rom_id": rom_id, "stored_name": rom["stored_name"], "size_bytes": len(data)}


# ── Extra files on a card (homebrew: e.g. smw_assets.dat alongside the .bin
#    template) ───────────────────────────────────────────────────────────────
def _extra_list(rom: dict) -> list[dict]:
    try:
        return json.loads(rom.get("extra_files") or "[]")
    except (ValueError, TypeError):
        return []


@router.post("/sessions/{session_id}/roms/{rom_id}/files")
async def add_rom_file(session_id: str, rom_id: str, file: UploadFile = File(...)) -> dict:
    """Attach (or REPLACE, by filename) an extra data file on a card — e.g. the
    smw_assets.dat that sits next to the read-only Super Mario World.bin template.
    Stored next to the rom (roms/<dir>/<name>), recorded in extra_files, and
    shipped to the SD by the normal packaging rule (.dat always)."""
    with db.connect() as conn:
        require_session(conn, session_id)
        rom = conn.execute("SELECT * FROM roms WHERE id=? AND session_id=?",
                           (rom_id, session_id)).fetchone()
        if rom is None:
            raise HTTPException(status_code=404, detail="ROM을 찾을 수 없습니다")
        rom = dict(rom)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다")
    if len(data) > config.MAX_ROM_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다")

    name = storage.safe_name(storage.nfc(file.filename or "file"))
    parts = Path(rom["rom_path"]).parts          # ('roms', '<dir>', '<file>')
    dirname = parts[1] if len(parts) >= 3 else "homebrew"
    rel = f"{config.ROMS_DIR_NAME}/{dirname}/{name}"
    if name == Path(rom["stored_name"]).name:
        raise HTTPException(status_code=400, detail="기본(템플릿) 파일과 같은 이름은 쓸 수 없습니다")

    storage.write_bytes(storage.session_root(session_id) / rel, data)
    extra = [e for e in _extra_list(rom) if e.get("name") != name]   # replace if same name
    extra.append({"name": name, "size": len(data)})
    with db.connect() as conn:
        conn.execute("UPDATE roms SET extra_files=? WHERE id=?", (json.dumps(extra), rom_id))
    return {"rom_id": rom_id, "extra_files": extra}


@router.delete("/sessions/{session_id}/roms/{rom_id}/files/{name}")
def delete_rom_file(session_id: str, rom_id: str, name: str) -> dict:
    """Remove an extra data file from a card (its template .bin is never touched)."""
    with db.connect() as conn:
        require_session(conn, session_id)
        rom = conn.execute("SELECT * FROM roms WHERE id=? AND session_id=?",
                           (rom_id, session_id)).fetchone()
        if rom is None:
            raise HTTPException(status_code=404, detail="ROM을 찾을 수 없습니다")
        rom = dict(rom)
    parts = Path(rom["rom_path"]).parts
    dirname = parts[1] if len(parts) >= 3 else "homebrew"
    storage.move_to_trash(session_id, f"{config.ROMS_DIR_NAME}/{dirname}/{name}")
    extra = [e for e in _extra_list(rom) if e.get("name") != name]
    with db.connect() as conn:
        conn.execute("UPDATE roms SET extra_files=? WHERE id=?", (json.dumps(extra), rom_id))
    return {"rom_id": rom_id, "extra_files": extra}
