"""One-off: fetch libretro-thumbnails box art for the Virtual Boy library and set
each ROM's cover IN-PROCESS (reusing the backend cover pipeline), because the
running container image predates the `vb` system and its cover render 500s.
Matches by exact No-Intro base name (libretro sanitizes filesystem-illegal chars:
& -> _, : -> _, etc.), then a normalized fallback.
"""
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from app import db
from app.routers import covers as cov

SESSION = "public"
SYSTEM = "vb"
BOXART_BASE = (
    "https://raw.githubusercontent.com/libretro-thumbnails/"
    "Nintendo_-_Virtual_Boy/master/Named_Boxarts/"
)
BOXART_LIST = Path("/tmp/claude-1001/-home-ubuntu-app-jupyterLab-notebooks-game-and-what"
                   "/7c12ff2e-defd-465c-b3fd-00afcbd114a5/scratchpad/vb_boxarts.txt")

_ILLEGAL = '&*/:`<>?\\|"'


def sanitize(name: str) -> str:
    return "".join("_" if c in _ILLEGAL else c for c in name)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower()
    return "".join(ch for ch in s if ch.isalnum())


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "gnw-cover/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


available = [ln.strip() for ln in BOXART_LIST.read_text().splitlines() if ln.strip()]
by_exact = set(available)
by_norm: dict[str, str] = {}
for a in available:
    by_norm.setdefault(norm(a), a)

with db.connect() as conn:
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM roms WHERE system_key=? AND session_id=? ORDER BY stored_name",
        (SYSTEM, SESSION),
    )]

set_ok = missed = 0
for rom in rows:
    base = rom["stored_name"].rsplit(".", 1)[0]
    cand = sanitize(base)
    match = cand if cand in by_exact else by_norm.get(norm(base))
    if not match:
        print(f"  MISS  {base}")
        missed += 1
        continue
    url = BOXART_BASE + urllib.parse.quote(match + ".png")
    try:
        raw = fetch(url)
        cover_bytes = cov._render_cover(rom, raw)
        cover_rel = cov._save_cover(SESSION, rom, cover_bytes, raw)
        with db.connect() as conn:
            cov._update_cover_db(conn, rom["id"], cover_rel, "ok", "manual")
        set_ok += 1
    except Exception as exc:  # noqa: BLE001
        print(f"  ERR   {base}: {exc}")
        missed += 1

print(f"vb covers: set {set_ok}, missed {missed}, total {len(rows)}")
