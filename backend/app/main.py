"""gnw-retro-manager API — FastAPI entry point."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, db
from .routers import covers, data, downloads, extra, firmware, gamelist, igdb, jobs, lang, manage, music, package, roms, sessions, sgdb, tgdb, uploads, videos
from .services.video import ffmpeg_available
from .systems import SYSTEMS

app = FastAPI(title="gnw-retro-manager", version="0.1.0")

# No cookies/auth, so wildcard origins are fine (credentials must be off with "*").
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers — must be registered BEFORE the SPA catch-all below.
app.include_router(sessions.router)
app.include_router(roms.router)
app.include_router(videos.router)
app.include_router(jobs.router)
app.include_router(package.router)
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
    from .services import langfill
    with db.connect() as conn:
        langfill.backfill(conn)
        langfill.backfill_region(conn)


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
