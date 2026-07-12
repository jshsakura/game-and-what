"""App configuration. Secrets come from the environment, never hardcoded."""
from __future__ import annotations

import os
from pathlib import Path


def _load_env_file() -> None:
    """Lightweight .env loader (no dependency). Reads the project-root .env — the
    single source of truth, also what docker-compose injects — if present; does
    NOT override variables already set in the real environment (e.g. by compose)."""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

# Persistent library root — files live here permanently ("날아가면 안 됨").
DATA_DIR = Path(os.getenv("GNW_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
LIBRARY_DIR = DATA_DIR / "library"        # /library/<session>/{roms,covers,media}
DB_PATH = DATA_DIR / "gnw.db"

# Bundled Korean-name source — part of the app SOURCE TREE (NOT under DATA_DIR),
# so a data/ wipe never loses the curated Korean naming feature. Holds the
# per-system gamelists (gamelists/*.xml) the Korean-rename feature reads, plus
# reference datasets under _reference/. Korean-only feature data.
KOREAN_NAMES_DIR = Path(__file__).resolve().parent / "assets" / "korean_names"

# Single SHARED library: no per-user isolation — everyone uploads to and sees
# the same workspace. The frontend always uses this fixed session id.
SHARED_SESSION_ID = "public"

# Korea-specific features (한글패치 toggle, Korean-name auto-resolve / gamelist,
# the cover-flag 'ko' default) are gated behind this. OFF by default so the
# PUBLIC Docker image is international; a Korean deploy sets GNW_KOREAN_MODE=true
# (e.g. in backend/.env). Exposed to the frontend via GET /api/config.
KOREAN_MODE = os.getenv("GNW_KOREAN_MODE", "false").strip().lower() in ("1", "true", "yes", "on")

# "Personal lab" mode. The public image tracks ONLY what the upstream firmware
# (github.com/sylverb/game-and-watch-retro-go-sd) officially supports — systems
# up to Atari Lynx, no media extras. Everything that needs the jshsakura fork
# firmware (extra systems like NGP/WonderSwan/PCE-CD/Virtual Boy…, the MEDIA
# tab's video/music/clock converters, the experimental-releases link) is gated
# behind this flag. OFF by default; a fork-firmware deploy sets
# GNW_EXPERIMENTAL_MODE=true. Exposed to the frontend via GET /api/config.
EXPERIMENTAL_MODE = os.getenv("GNW_EXPERIMENTAL_MODE", "false").strip().lower() in ("1", "true", "yes", "on")

# SD-card folder names (must mirror the device layout exactly).
ROMS_DIR_NAME = "roms"
COVERS_DIR_NAME = "covers"
# The fork firmware's Video app browses /video (VIDEO_ROOT in main_video.c) — it
# has never read /media, so anything we shipped there was invisible on the
# device. LEGACY_MEDIA_DIR_NAME is only for the one-time migration at startup.
MEDIA_DIR_NAME = "video"
LEGACY_MEDIA_DIR_NAME = "media"
MUSIC_DIR_NAME = "music"   # firmware Music app scans /music (MP3 played directly)

# External metadata/art providers — keys via env only (security rule).
IGDB_CLIENT_ID = os.getenv("IGDB_CLIENT_ID", "")
IGDB_CLIENT_SECRET = os.getenv("IGDB_CLIENT_SECRET", "")
# TheGamesDB (thegamesdb.net) — keyless-ish public API key, instant. Monthly quota.
TGDB_API_KEY = os.getenv("TGDB_API_KEY", "")
# SteamGridDB (steamgriddb.com) — community box-art, broad coverage. Bearer token.
# Used as an extra cover-search source when TheGamesDB's monthly quota is spent.
STEAMGRIDDB_API_KEY = os.getenv("STEAMGRIDDB_API_KEY", "")

# Upload limits.
MAX_VIDEO_BYTES = int(os.getenv("GNW_MAX_VIDEO_BYTES", str(512 * 1024 * 1024)))
MAX_ROM_BYTES = int(os.getenv("GNW_MAX_ROM_BYTES", str(64 * 1024 * 1024)))
# CD folder-per-game uploads (PC Engine CD etc.): a single data/audio track or a
# .chd can dwarf a cartridge, and a full disc is hundreds of MB, so these get
# their own much larger per-file / per-folder caps.
MAX_CD_FILE_BYTES = int(os.getenv("GNW_MAX_CD_FILE_BYTES", str(1024 * 1024 * 1024)))
MAX_CD_TOTAL_BYTES = int(os.getenv("GNW_MAX_CD_TOTAL_BYTES", str(2 * 1024 * 1024 * 1024)))
MAX_MUSIC_BYTES = int(os.getenv("GNW_MAX_MUSIC_BYTES", str(64 * 1024 * 1024)))
MAX_FIRMWARE_BYTES = int(os.getenv("GNW_MAX_FIRMWARE_BYTES", str(64 * 1024 * 1024)))
MAX_EXTRA_BYTES = int(os.getenv("GNW_MAX_EXTRA_BYTES", str(128 * 1024 * 1024)))

# Service ports (3xxxx range; Docker maps these later).
API_PORT = int(os.getenv("GNW_API_PORT", "38080"))
FRONTEND_PORT = int(os.getenv("GNW_FRONTEND_PORT", "38081"))

# CORS origins. Default "*" — this is a private tool on a Tailscale network
# with no auth/cookies, accessed via varying IPs/hostnames. Override with
# GNW_CORS_ORIGINS (comma-separated) to lock down.
CORS_ORIGINS = os.getenv("GNW_CORS_ORIGINS", "*").split(",")


# Chunked upload settings.
TMP_DIR = DATA_DIR / "tmp"
MAX_CHUNK_BYTES = int(os.getenv("GNW_MAX_CHUNK_BYTES", str(10 * 1024 * 1024)))  # 10 MB
MAX_UPLOAD_TOTAL_BYTES = int(
    os.getenv("GNW_MAX_UPLOAD_TOTAL_BYTES", str(512 * 1024 * 1024))  # 512 MB
)


def ensure_dirs() -> None:
    """Create the persistent directories at startup."""
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
