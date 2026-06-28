"""gnw-retro-manager API — FastAPI entry point."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, db
from .routers import covers, data, downloads, events, extra, firmware, gamelist, igdb, jobs, lang, manage, music, package, roms, scores, sessions, sgdb, tgdb, uploads, videos
from .services.video import ffmpeg_available
from .systems import SYSTEMS

app = FastAPI(title="gnw-retro-manager", version="1.5.1")

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
app.include_router(sessions.router)
app.include_router(roms.router)
app.include_router(videos.router)
app.include_router(jobs.router)
app.include_router(package.router)
app.include_router(scores.router)
app.include_router(downloads.router)
app.include_router(covers.router)
app.include_router(uploads.router)
app.include_router(manage.router)
app.include_router(music.router)
app.include_router(firmware.router)
app.include_router(extra.router)
app.include_router(igdb.router)
app.include_router(tgdb.router)
app.include_router(sgdb.router)
app.include_router(data.router)
app.include_router(gamelist.router)
app.include_router(lang.router)
app.include_router(events.router)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    # Reclaim disk from orphaned upload temps (.src_*) left by an encode that was
    # killed mid-run (crash/OOM/stop) before its finally-cleanup could fire.
    from .services import storage
    swept = storage.sweep_temp_uploads()
    if swept:
        print(f"[startup] swept {swept} orphaned upload temp file(s)")
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
    # Purge deleted files past the recovery window so _trash can't grow forever.
    purged = storage.purge_trash(config.SHARED_SESSION_ID, events.RETENTION_DAYS)
    if purged:
        print(f"[startup] purged {purged} expired trash file(s)")
    # Tidy the SD-zip build cache so it never lingers oversized.
    from .services import packaging
    pruned = packaging.prune_cache()
    if pruned:
        print(f"[startup] pruned {pruned} stale SD cache zip(s)")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "ffmpeg": ffmpeg_available()}


@app.get("/api/config")
def client_config() -> dict:
    """Runtime feature flags the frontend reads at startup. korean_mode gates the
    Korea-specific UI (한글패치 toggle, Korean-name resolve/gamelist)."""
    return {"korean_mode": config.KOREAN_MODE}


@app.get("/api/systems")
def list_systems() -> dict:
    """The systems the SD firmware registers, with /roms/<dirname> + extensions."""
    return {
        "systems": [
            {
                "key": s.key,
                "name": s.name,
                "dirname": s.dirname,
                "exts": list(s.exts),
                "pico8": s.pico8,
            }
            for s in SYSTEMS
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
