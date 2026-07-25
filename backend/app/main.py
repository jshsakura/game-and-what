"""gnw-retro-manager API — FastAPI entry point."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, db
from .routers import clock, covers, data, downloads, events, extra, firmware, gamelist, igdb, jobs, lang, libretro, manage, music, package, roms, scores, sessions, sgdb, tgdb, uploads, videos
from .services.video import ffmpeg_available
from .systems import available_systems

app = FastAPI(title="gnw-retro-manager", version="1.11.0")

# No cookies/auth, so wildcard origins are fine (credentials must be off with "*").
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _cross_origin_isolation(request, call_next):
    """Make the page cross-origin isolated so the in-browser ffmpeg.wasm
    MULTI-THREAD core can use SharedArrayBuffer (2–4× faster video convert).
    `credentialless` (not require-corp) keeps cross-origin <img> — e.g. the
    IGDB/TGDB cover-search thumbnails — loading without CORP headers."""
    response = await call_next(request)
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
    return response

# API routers — must be registered BEFORE the SPA catch-all below.
# videos/clock/music are fork-firmware features (avi media player, clock bg.gif,
# music app) → whole routers 403 unless GNW_EXPERIMENTAL_MODE is on.
_EXPERIMENTAL_ONLY = [Depends(sessions.require_experimental_mode)]
app.include_router(sessions.router)
app.include_router(roms.router)
app.include_router(videos.router, dependencies=_EXPERIMENTAL_ONLY)
app.include_router(clock.router, dependencies=_EXPERIMENTAL_ONLY)
app.include_router(jobs.router)
app.include_router(package.router)
app.include_router(scores.router)
app.include_router(downloads.router)
app.include_router(covers.router)
app.include_router(uploads.router)
app.include_router(manage.router)
app.include_router(music.router, dependencies=_EXPERIMENTAL_ONLY)
app.include_router(firmware.router)
app.include_router(extra.router)
app.include_router(igdb.router)
app.include_router(tgdb.router)
app.include_router(sgdb.router)
app.include_router(libretro.router)
app.include_router(data.router)
app.include_router(gamelist.router)
app.include_router(lang.router)
app.include_router(events.router)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    # A Korean deploy starts WITH the dictionary instead of with nothing — 1,900 names
    # are the one thing a fresh install cannot work out for itself, and without them the
    # Korean-name resolve this mode exists for has nothing to resolve against. Gated on
    # KOREAN_MODE for the same reason that resolve is: the international image stays free
    # of 한글 features. Only when the table is empty — after that the local database is
    # the authority, and a seed arriving with a release must not walk over a name the
    # user has fixed by hand.
    from .services import dataset as dataset_svc
    seeded, _ = dataset_svc.seed_if_empty()
    if seeded:
        print(f"[startup] seeded {seeded} Korean name(s) from data/names.ko.json")
    # The GBA measurements are a public good too: the idle addresses, per-frame cycles and
    # sound-driver costs we hunted on real runs ship in the image, but until now only a
    # hand-run of gba_measure.py put them on a rom's row. Stamp them onto every matching
    # rom at boot, so a fresh Docker install shows the CPU/idle/mixer verdict instead of a
    # spinner. Idempotent — a converged library changes nothing here on the next restart.
    from .services import gba_seed
    with db.connect() as conn:
        measured = gba_seed.apply_table(conn)
    if measured:
        print(f"[startup] seeded {measured} GBA measurement(s) from scripts/gba_idle_loop_db.json")
    # Reclaim disk from orphaned upload temps (.src_*) left by an encode that was
    # killed mid-run (crash/OOM/stop) before its finally-cleanup could fire.
    from .services import storage
    swept = storage.sweep_temp_uploads()
    if swept:
        print(f"[startup] swept {swept} orphaned upload temp file(s)")
    # Videos used to be filed under media/, which the firmware never reads (its
    # Video app browses /video). Move them once; no-op thereafter.
    moved_videos = storage.migrate_legacy_media_dir()
    if moved_videos:
        print(f"[startup] moved {moved_videos} video(s) from media/ to video/")
    # Backfill language/한글패치 for legacy roms (lang_source IS NULL) once — new
    # uploads already auto-detect, so this converges immediately and is a no-op
    # thereafter. Metadata-only: never touches filenames, covers or files.
    from .services import events, langfill
    with db.connect() as conn:
        langfill.backfill(conn)
        langfill.backfill_region(conn)
        # Seed the activity feed from the existing library (one upload event per
        # ROM that lacks one). Idempotent — no-ops once converged.
        seeded = events.seed_uploads(conn, config.SHARED_SESSION_ID)
        if seeded:
            print(f"[startup] seeded {seeded} upload event(s) into the activity feed")
    # A cover autofill only lives in memory (background task), so a restart mid-run
    # strands its roms on cover_status='pending' — a spinner that never resolves and
    # a library that polls forever. Nothing is in flight at boot: clear them.
    with db.connect() as conn:
        stranded = conn.execute(
            "UPDATE roms SET cover_status = 'none' WHERE cover_status = 'pending'").rowcount
    if stranded:
        print(f"[startup] cleared {stranded} stranded 'pending' cover(s)")
    # Purge deleted files past the recovery window so _trash can't grow forever.
    purged = storage.purge_trash(config.SHARED_SESSION_ID, events.RETENTION_DAYS)
    if purged:
        print(f"[startup] purged {purged} expired trash file(s)")
    # Same clock for the pre-encode source backups: recoverable for a while, then
    # gone (they are full-size videos — the biggest thing we keep).
    purged_src = storage.purge_orig_backups(config.SHARED_SESSION_ID, events.RETENTION_DAYS)
    if purged_src:
        print(f"[startup] purged {purged_src} expired source-video backup(s)")
    # Tidy the SD-zip build cache so it never lingers oversized.
    from .services import packaging
    pruned = packaging.prune_cache()
    if pruned:
        print(f"[startup] pruned {pruned} stale SD cache zip(s)")


@app.on_event("startup")
async def _resume_gba_probes() -> None:
    """Pick the measurement queue back up where a restart dropped it.

    Measuring a GBA rom means RUNNING it, one at a time (services/gba_probe holds a
    semaphore), so a hundred fresh roms is a queue that takes a while — and the queue lives
    only in memory. A restart in the middle of it left every rom still waiting stranded on
    probe_status='pending': a "측정 중" spinner that never resolves, on a card that will
    never be measured, forever. Covers already had this recovery; the prober did not.

    Re-queue rather than clear: the answer is worth having, and a rom already in the shared
    table costs nothing to resolve (lookup first, run only what we have never seen).
    """
    from .routers.roms import _probe_gba
    from .services import storage

    root = storage.session_root(config.SHARED_SESSION_ID)
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, rom_path FROM roms WHERE session_id = ? AND system_key = 'gba' "
            "AND probe_status = 'pending'", (config.SHARED_SESSION_ID,))]
    # The upload path hands the prober an ABSOLUTE path; the database stores a
    # session-relative one ("roms/gba/…"). Passing the stored value straight through would
    # have the prober open a file that is not there and quietly fail — which looks exactly
    # like the bug this is here to fix.
    for row in rows:
        row["rom_path"] = str(root / row["rom_path"])

    if rows:
        print(f"[startup] resuming {len(rows)} unfinished GBA measurement(s)")
        asyncio.create_task(_probe_gba(config.SHARED_SESSION_ID, rows))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "ffmpeg": ffmpeg_available()}


@app.get("/api/config")
def client_config() -> dict:
    """Runtime feature flags the frontend reads at startup. korean_mode gates the
    Korea-specific UI (한글패치 toggle, Korean-name resolve/gamelist). cover_sources
    tells the cover-search popup which providers are configured, so it can disable
    the ones without an API key (libretro is keyless → always on)."""
    return {
        "korean_mode": config.KOREAN_MODE,
        # "Personal lab" flag: fork-firmware extras (experimental systems, the
        # MEDIA tab). Off → the UI shows the upstream-official feature set only.
        "experimental_mode": config.EXPERIMENTAL_MODE,
        "cover_sources": {
            "libretro": True,
            "igdb": bool(config.IGDB_CLIENT_ID and config.IGDB_CLIENT_SECRET),
            "tgdb": bool(config.TGDB_API_KEY),
            "sgdb": bool(config.STEAMGRIDDB_API_KEY),
        },
    }


@app.get("/api/systems")
def list_systems() -> dict:
    """The systems this deploy exposes (upstream-official only unless experimental
    mode is on), with /roms/<dirname> + extensions. `experimental` marks fork-only
    systems so the UI can visually separate them from the official set."""
    return {
        "systems": [
            {
                "key": s.key,
                "name": s.name,
                "dirname": s.dirname,
                "exts": list(s.exts),
                "pico8": s.pico8,
                "experimental": s.experimental,
            }
            for s in available_systems()
        ]
    }


# Never let the HTML document (index.html / SPA fallback) be cached: it names the
# content-hashed JS/CSS bundle, so a stale cached copy pins the browser to an OLD
# build (icons/features don't update). StaticFiles sets no Cache-Control, and
# Cloudflare/browsers then cache it heuristically. Force revalidation on every
# load — the hashed /assets stay cacheable, only the tiny HTML is rechecked.
@app.middleware("http")
async def _no_cache_html(request, call_next):
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


# ── Production SPA static mount (Task D) ────────────────────────────────────
# When the Docker image is built the Vite output is copied to one of these
# candidate locations. We mount it ONLY when present so the dev workflow
# (Vite on :38081 proxying /api to :38080) is completely unaffected.
#
# Candidate order:
#   1. backend/app/static          (files copied into the Python package tree)
#   2. /app/frontend_dist          (Docker COPY target in the multi-stage build)
_SPA_CANDIDATES: tuple[Path, ...] = (
    Path(__file__).resolve().parent / "static",
    Path("/app/frontend_dist"),
)

for _spa_dir in _SPA_CANDIDATES:
    if (_spa_dir / "index.html").exists():
        # Serve static assets (JS/CSS/images) directly from the dist folder.
        app.mount(
            "/assets",
            StaticFiles(directory=str(_spa_dir / "assets")),
            name="spa-assets",
        )
        # SPA fallback: every non-/api path returns index.html.
        app.mount("/", StaticFiles(directory=str(_spa_dir), html=True), name="spa")
        break
