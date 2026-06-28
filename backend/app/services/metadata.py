"""
Per-ROM metadata + artwork resolution (screenshot, box art, Korean title).

Each ROM should expose a SCREENSHOT (사용자 요구). Resolution chain, best-effort,
never raises — missing pieces just come back None:

  1. Korean title : local mapping JSON (data/korean_names/<system>.json) first,
                    then provider regional names, else keep the original name.
  2. Screenshot   : libretro-thumbnails `Named_Snaps` (keyless, immediate).
  3. Box art      : libretro-thumbnails `Named_Boxarts` (fallback cover source).
  4. ScreenScraper / IGDB : richer metadata when keys are configured (env).

Cover art is generated from the screenshot by default, box art as fallback.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from .. import config

# our system key -> libretro-thumbnails repo name
_LIBRETRO_REPO = {
    "nes": "Nintendo - Nintendo Entertainment System",
    "gb": "Nintendo - Game Boy",
    "gbc": "Nintendo - Game Boy Color",
    "gg": "Sega - Game Gear",
    "sms": "Sega - Master System - Mark III",
    "md": "Sega - Mega Drive - Genesis",
    "sg": "Sega - SG-1000",
    "pce": "NEC - PC Engine - TurboGrafx 16",
    "col": "Coleco - ColecoVision",
    "msx": "Microsoft - MSX",
    "a2600": "Atari - 2600",
    "a7800": "Atari - 7800",
    "lynx": "Atari - Lynx",
    "amstrad": "Amstrad - CPC",
    "wsv": "Watara - Supervision",
    "mini": "Nintendo - Pokemon Mini",
    # gw / tama / videopac / pico8: no standard libretro thumbnail repo
}

_RAW_BASE = "https://raw.githubusercontent.com/libretro-thumbnails"


@dataclass(frozen=True)
class GameMeta:
    original_name: str
    title: str                 # display title (Korean if resolved, else original)
    korean_name: str | None
    screenshot_url: str | None
    boxart_url: str | None
    source: str                # which resolver produced the artwork

    @property
    def art_url(self) -> str | None:
        """Preferred cover source: screenshot first, box art as fallback."""
        return self.screenshot_url or self.boxart_url


def _rom_stem(filename: str) -> str:
    """'Super Mario Bros. (USA).nes' -> 'Super Mario Bros. (USA)'."""
    name = Path(filename).name
    return name.rsplit(".", 1)[0] if "." in name else name


def _libretro_url(system_key: str, kind: str, stem: str) -> str | None:
    repo = _LIBRETRO_REPO.get(system_key)
    if not repo:
        return None
    # The GitHub repo NAME uses underscores for spaces ("Sega - SG-1000" →
    # "Sega_-_SG-1000"); the file PATH keeps spaces (URL-encoded). Verified live.
    repo_slug = repo.replace(" ", "_")
    # libretro replaces filesystem-illegal chars with '_' in the filename
    safe = re.sub(r'[&*/:`<>?\\|"]', "_", stem)
    return f"{_RAW_BASE}/{repo_slug}/master/{kind}/{quote(safe)}.png"


def _load_korean_map(system_key: str) -> dict[str, str]:
    path = config.DATA_DIR / "korean_names" / f"{system_key}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _resolve_korean(system_key: str, stem: str) -> str | None:
    mapping = _load_korean_map(system_key)
    if stem in mapping:
        return mapping[stem]
    # try without region/version parens: 'Sonic (USA)' -> 'Sonic'
    base = re.sub(r"\s*[(\[].*?[)\]]", "", stem).strip()
    return mapping.get(base)


def resolve_metadata(system_key: str, filename: str) -> GameMeta:
    """
    Best-effort metadata for one ROM. Network/key-gated providers are layered
    on top of this in fetch_metadata(); this synchronous core gives the
    immediately-available libretro URLs + local Korean mapping.
    """
    stem = _rom_stem(filename)
    korean = _resolve_korean(system_key, stem)
    screenshot = _libretro_url(system_key, "Named_Snaps", stem)
    boxart = _libretro_url(system_key, "Named_Boxarts", stem)
    return GameMeta(
        original_name=stem,
        title=korean or stem,
        korean_name=korean,
        screenshot_url=screenshot,
        boxart_url=boxart,
        source="libretro" if (screenshot or boxart) else "none",
    )
