"""Fetch & cache the PICO-8 core for the SD card.

retro-go-sd needs `cores/pico8*` present to run .p8 games. The core binaries are
distributed by Macs75/pico8_gnw_distro as a release asset; we download the latest
once, cache it, and bundle its `cores/` files into the SD ZIP.
"""
from __future__ import annotations

import io
import json
import urllib.request
import zipfile
from pathlib import Path

from .. import config

_REPO = "Macs75/pico8_gnw_distro"
_LATEST_API = f"https://api.github.com/repos/{_REPO}/releases/latest"
_CACHE = config.TMP_DIR / "pico8_cores"
_CORES = _CACHE / "cores"
_UA = {"User-Agent": "gnw-retro-manager"}


def _http(url: str, timeout: int = 30):
    return urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout)


def _cached() -> Path | None:
    return _CORES if (_CORES.exists() and any(_CORES.iterdir())) else None


def ensure_cores_dir(force: bool = False) -> Path | None:
    """Return a dir holding the PICO-8 `cores/*` files, downloading the latest
    release on first use (or when `force` — which always re-downloads, so it doubles
    as a repair for a half-written cache). Falls back to the cache on any network
    error and returns None only if nothing is available — never raises."""
    if _cached() and not force:
        return _CORES

    try:
        rel = json.load(_http(_LATEST_API))
        asset = next((a for a in rel.get("assets", []) if a["name"].endswith(".zip")), None)
        if not asset:
            return _cached()
        data = _http(asset["browser_download_url"]).read()
    except Exception:
        return _cached()

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        _CORES.mkdir(parents=True, exist_ok=True)
        for p in _CORES.glob("*"):
            if p.is_file():
                p.unlink()
        for name in zf.namelist():
            parts = name.split("/")
            if name.endswith("/") or "cores" not in parts:
                continue
            rel_name = "/".join(parts[parts.index("cores") + 1:])
            if not rel_name:
                continue
            dest = _CORES / rel_name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
        return _cached()
    except Exception:
        return _cached()
