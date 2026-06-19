"""Import an EmulationStation-style gamelist.xml as a Korean-name source and
RENAME matching library rom files to the curated Korean name.

Key insight: the device shows the FILENAME, so Korean = the file must be renamed.
gamelist <path> uses MAME shortnames (gnw_ball) while uploaded roms use
descriptive names (Ball (Nintendo)), so we match on the English title that
appears in BOTH the gamelist name ("볼 (Ball)") and the stored name
("Ball (Nintendo)")."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .. import config
from . import storage

_PAREN_ENG = re.compile(r"\(([A-Za-z0-9][^)]*)\)")

# ES/Batocera gamelist folder name (in <path>) -> our system key.
_FOLDER_TO_SYSTEM = {
    "gnw": "gw", "gw": "gw", "gameandwatch": "gw",
    "nes": "nes", "fds": "nes", "gb": "gb", "gbc": "gbc", "gamegear": "gg",
    "gg": "gg", "mastersystem": "sms", "sms": "sms", "megadrive": "md",
    "genesis": "md", "md": "md", "sg1000": "sg", "sg": "sg", "pcengine": "pce",
    "pce": "pce", "colecovision": "col", "coleco": "col", "msx": "msx",
    "atari2600": "a2600", "atari7800": "a7800", "amstradcpc": "amstrad",
    "amstrad": "amstrad", "supervision": "wsv", "wsv": "wsv", "pokemini": "mini",
    "pokemonmini": "mini", "tamagotchi": "tama", "tama": "tama", "pico8": "pico8",
    "homebrew": "homebrew",
    "famicom": "nes", "fc": "nes",
    # Neo Geo Pocket + WonderSwan are combined folders: mono+Color share one
    # system, so ngpc→ngp and wsc→ws (a 'gamelist-ngpc.xml' feeds the ngp tab).
    "ngp": "ngp", "ngc": "ngp", "ngpc": "ngp", "neogeopocket": "ngp",
    "ws": "ws", "wsc": "ws", "wonderswan": "ws", "swancrystal": "ws",
    # identity keys so 'gamelist-a2600.xml' etc infer directly
    "nes": "nes", "gbc": "gbc", "a2600": "a2600", "a7800": "a7800", "mini": "mini",
}


def _norm(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


# Generic platform/edition/region tokens that must never be a sole match key.
_STOP_KEYS = {
    "gb", "gbc", "gba", "sgb", "nes", "snes", "md", "dx", "the", "usa", "jpn",
    "jp", "eur", "kor", "kr", "en", "ko", "rev", "ver",
}


def _is_matchable(key: str) -> bool:
    """A usable English key needs real latin substance (≥3 letters) and must not
    be a generic platform/edition tag — so Korean-named files whose only latin is
    'GB'/'DX' never collide ('팝픈 뮤직 GB' → 'gb' is rejected)."""
    if len(re.findall(r"[a-z]", key)) < 3:
        return False
    return key not in _STOP_KEYS


def _english_key(text: str) -> str:
    """Extract the English title from a label and normalize it.
    '(K) Contra' → 'contra'; 'Ball (Nintendo)' → 'ball'; '볼 (Ball)' → 'ball'."""
    s = re.sub(r"^\(k\)\s*", "", text or "", flags=re.I)   # drop leading (K)
    paren = _PAREN_ENG.search(s)
    before = re.split(r"\s*\(", s, 1)[0].strip()
    # pick the more-English candidate (the part before parens, unless it has no
    # latin letters — then use the ascii inside the first paren, e.g. '볼 (Ball)')
    if re.search(r"[A-Za-z]", before):
        cand = before
    elif paren:
        cand = paren.group(1)
    else:
        cand = before
    return _norm(cand)


def _gamelist_keys(name: str, path: str) -> set[str]:
    """Normalized English keys for a gamelist game — from BOTH the <name> and the
    <path> leaf (covers gw-style 'Ball' in name AND gb-style 'Contra' in path)."""
    keys = set()
    k1 = _english_key(name)
    if k1:
        keys.add(k1)
    leaf = Path((path or "").strip()).stem
    if leaf and not re.match(r"(gnw|mame|sgb)_", leaf.lower()):  # skip MAME codes
        k2 = _english_key(leaf)
        if k2:
            keys.add(k2)
    return {k for k in keys if _is_matchable(k)}


def _has_hangul(s: str) -> bool:
    return bool(re.search(r"[가-힣]", s or ""))


def _clean_korean(name: str) -> str:
    """Korean display part: drop leading '(K) '. Keep a trailing English paren if
    present (it already IS 'Korean (English)', e.g. gw '볼 (Ball)')."""
    return re.sub(r"^\(k\)\s*", "", name or "", flags=re.I).strip()


def _clean_english(text: str) -> str:
    """English title for the '(English)' suffix / scraper: drop '(K) ' and any
    trailing tags. '(K) Madou Monogatari I' → 'Madou Monogatari I'."""
    s = re.sub(r"^\(k\)\s*", "", text or "", flags=re.I).strip()
    paren = _PAREN_ENG.search(s)
    before = re.split(r"\s*\(", s, 1)[0].strip()
    cand = before if re.search(r"[A-Za-z]", before) else (paren.group(1) if paren else before)
    return cand.strip()


def _kor_key(text: str) -> str:
    """Normalized Korean key: drop '(K)', any '(...)' tags and spacing →
    '(K) 슈퍼 로봇 대전' → '슈퍼로봇대전'. Used to re-match already-Korean files."""
    s = re.sub(r"\(k\)", "", text or "", flags=re.I)
    s = re.sub(r"\([^)]*\)", "", s)            # drop English/other parens
    return re.sub(r"[^가-힣0-9]", "", s)


def compose_name(korean: str, english: str) -> str:
    """Build the user's preferred 'Korean (English)' filename base — keeps English
    so scrapers can still pull cover art. Falls back gracefully."""
    kor = _clean_korean(korean)
    if _PAREN_ENG.search(kor):       # already 'Korean (English)'
        return kor
    eng = _clean_english(english)
    if _has_hangul(kor) and eng and _norm(eng) != _norm(kor):
        return f"{kor} ({eng})"
    return kor or eng


_PS1_BLOCK = re.compile(r"@\{(.*?)\}", re.S)
_PS1_STR = re.compile(r"['\"]([^'\"]+?)['\"]")


def parse_ps1(text: str) -> list[dict]:
    """Parse a 꿀렁 .ps1 ($games = @( @{Name=..; TargetPattern=..; BasePattern=@(..)} ))
    into [{korean, english, patterns}]. Patterns are the regex aliases used to
    match messy romset filenames (romaji/Korean/typos)."""
    out = []
    for block in _PS1_BLOCK.findall(text):
        nm = re.search(r"Name\s*=\s*['\"](.+?)['\"]", block, re.S)
        tp = re.search(r"TargetPattern\s*=\s*['\"](.+?)['\"]", block, re.S)
        bp = re.search(r"BasePattern\s*=\s*@\((.*?)\)", block, re.S)
        if not nm or not bp:
            continue
        patterns = _PS1_STR.findall(bp.group(1))
        if patterns:
            out.append({"korean": nm.group(1), "english": (tp.group(1) if tp else nm.group(1)),
                        "patterns": patterns})
    return out


def _games_from_root(root) -> list[dict]:
    out = []
    for g in root.findall("game"):
        nm = (g.findtext("name") or "").strip()
        if not nm:
            continue
        p = (g.findtext("path") or "").strip()
        parts = p.strip("./").split("/")
        out.append({"name": nm, "path": p, "folder": parts[0].lower() if len(parts) > 1 else ""})
    return out


def parse_games(path) -> list[dict]:
    """Return [{name, path, folder}] for each <game> with a non-empty <name>."""
    return _games_from_root(ET.parse(path).getroot())


ARCHIVE_SUFFIXES = (".zip", ".7z")


def _read_archive(p: Path) -> dict:
    """Return {member_name: bytes} for a .zip or .7z archive."""
    suf = p.suffix.lower()
    if suf == ".zip":
        import zipfile
        with zipfile.ZipFile(p) as zf:
            return {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    if suf == ".7z":
        import py7zr
        with py7zr.SevenZipFile(p, "r") as z:
            return {n: bio.read() for n, bio in z.readall().items()}
    return {}


def load_games(path) -> dict:
    """Unified loader → {regex, key}: BOTH sources so coverage is maximal.
      - regex: [{korean, english, patterns}] from .ps1 BasePattern blocks.
      - key:   [{name, path, folder}] gamelist.xml entries (broad coverage).
    Accepts .zip / .7z archives (꿀렁 bundles) or a bare .xml."""
    p = Path(path)
    if p.suffix.lower() not in ARCHIVE_SUFFIXES:
        return {"regex": [], "key": parse_games(path)}

    contents = _read_archive(p)
    regex, key = [], []
    for n in sorted((n for n in contents if n.lower().endswith(".ps1")),
                    key=lambda n: 0 if "patched" in n.lower() else 1):
        try:
            regex.extend(parse_ps1(contents[n].decode("utf-8", "ignore")))
        except Exception:
            continue
    xmls = [n for n in contents if n.lower().endswith("gamelist.xml")]
    if xmls:
        try:
            key = _games_from_root(ET.fromstring(contents[xmls[0]]))
        except ET.ParseError:
            pass
    return {"regex": regex, "key": key}


def system_from_filename(name: str) -> str | None:
    """Infer the system from a gamelist filename, e.g. 'gamelist-gb.xml' → 'gb',
    '…-megadrive.xml' → 'md'. Falls back to None."""
    tokens = re.split(r"[^a-z0-9]+", (name or "").lower())
    for tok in tokens:
        if tok in _FOLDER_TO_SYSTEM:
            return _FOLDER_TO_SYSTEM[tok]
    return None


def infer_system(games: list[dict]) -> str | None:
    """Most-common gamelist folder mapped to our system key (e.g. gnw → gw)."""
    counts: dict[str, int] = {}
    for g in games:
        sys = _FOLDER_TO_SYSTEM.get(g["folder"])
        if sys:
            counts[sys] = counts.get(sys, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _index_keygames(key_games, by_eng, by_kor):
    """Populate English + Korean lookup dicts from gamelist entries."""
    for g in key_games:
        leaf = Path(g.get("path", "")).stem
        entry = {"name": g["name"],
                 "english": _clean_english(leaf) or _clean_english(g["name"])}
        for key in _gamelist_keys(g["name"], g.get("path", "")):
            by_eng.setdefault(key, entry)
        kk = _kor_key(g["name"])
        if kk:
            by_kor.setdefault(kk, entry)


def _resolve(stem, regex_games, by_eng, by_kor):
    """Gather candidates from every source (ps1 regex, English key, Korean key)
    and PREFER one with Hangul — so a Korean 'best' list never loses to an English
    'best' list. Returns 'Korean (English)' or None."""
    cands = []
    for g in regex_games:
        if any(re.search(p, stem, re.I) for p in g["patterns"]):
            cands.append(compose_name(g["korean"], g["english"]))
    key = _english_key(stem)
    if _is_matchable(key) and key in by_eng:
        g = by_eng[key]
        cands.append(compose_name(g["name"], g["english"]))
    kk = _kor_key(stem)
    if kk and kk in by_kor:
        g = by_kor[kk]
        cands.append(compose_name(g["name"], g["english"]))
    if not cands:
        return None
    korean = [c for c in cands if _has_hangul(c)]
    return (korean or cands)[0]


_SOURCE_CACHE: dict[str, tuple] = {}  # system -> (data_signature, sources)


def source_files(session_id: str) -> list[Path]:
    """All Korean-name source files, in priority order: the bundled seed
    (config.KOREAN_NAMES_DIR/gamelists — source of truth, lives in the app source
    tree so a data/ wipe can't lose it) first, then the session's scratch _data
    (user-uploaded lists). Only .xml / archive files are returned."""
    files: list[Path] = []
    seed = config.KOREAN_NAMES_DIR / "gamelists"
    if seed.exists():
        files.extend(sorted(seed.iterdir()))
    scratch = storage.scratch_dir(session_id)
    if scratch.exists():
        files.extend(sorted(scratch.iterdir()))
    return [f for f in files if f.suffix.lower() in (*ARCHIVE_SUFFIXES, ".xml")]


def gamelist_xmls(session_id: str) -> list[Path]:
    """The per-system gamelist*.xml sources (seed + scratch)."""
    return [f for f in source_files(session_id)
            if f.suffix.lower() == ".xml" and f.name.startswith("gamelist")]


def _data_signature(session_id: str) -> tuple:
    """Fingerprint of the Korean-name sources (paths + mtimes) — any change busts
    the cache. Spans both the bundled seed and the session scratch."""
    return tuple(sorted(
        (str(f), int(f.stat().st_mtime)) for f in source_files(session_id)
    ))


def get_sources(session_id: str, system: str) -> tuple[list, dict, dict]:
    """Cached build_sources_for_system — parses the (big) 꿀렁 archives only when
    DATA actually changed, so repeated uploads don't re-parse them."""
    sig = _data_signature(session_id)
    cached = _SOURCE_CACHE.get(system)
    if cached and cached[0] == sig:
        return cached[1]
    src = build_sources_for_system(session_id, system)
    _SOURCE_CACHE[system] = (sig, src)
    return src


def build_sources_for_system(session_id: str, system: str) -> tuple[list, dict, dict]:
    """Merge every Korean-name source (seed + scratch) for `system` →
    (regex, by_eng, by_kor)."""
    regex: list = []
    by_eng: dict[str, dict] = {}
    by_kor: dict[str, dict] = {}
    for f in source_files(session_id):
        sysk = system_from_filename(f.name)
        try:
            loaded = load_games(f)
        except Exception:
            continue
        if sysk is None and f.suffix.lower() == ".xml":
            sysk = infer_system(loaded["key"])
        if sysk != system:
            continue
        regex.extend(loaded["regex"])
        _index_keygames(loaded["key"], by_eng, by_kor)
    return regex, by_eng, by_kor


def resolve_with_sources(regex_games, by_eng, by_kor, filename: str) -> str | None:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return _resolve(stem, regex_games, by_eng, by_kor)


def build_plan(conn, session_id: str, source_path, system: str | None = None) -> dict:
    """Match library roms to a 꿀렁 source and plan renames to 'Korean (English)'.
    HYBRID: ps1 BasePattern regexes first (romaji/Korean/typo variants), then the
    bundled gamelist.xml by English title (broad coverage). System-scoped so a
    G&W list never touches a NES rom. Returns {system, plan:[{rom_id,old,new}]}."""
    loaded = load_games(source_path)
    regex_games, key_games = loaded["regex"], loaded["key"]

    target_system = system or infer_system(key_games)
    by_eng: dict[str, dict] = {}
    by_kor: dict[str, dict] = {}
    _index_keygames(key_games, by_eng, by_kor)

    if target_system:
        rows = conn.execute(
            "SELECT id, system_key, stored_name FROM roms WHERE session_id = ? AND system_key = ?",
            (session_id, target_system),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, system_key, stored_name FROM roms WHERE session_id = ?",
            (session_id,),
        ).fetchall()

    plan = []
    for r in rows:
        stem = r["stored_name"].rsplit(".", 1)[0]
        base = _resolve(stem, regex_games, by_eng, by_kor)
        if not base:
            continue
        ext = r["stored_name"].rsplit(".", 1)[-1] if "." in r["stored_name"] else ""
        new = storage.safe_name(base) + (f".{ext}" if ext else "")
        if new != r["stored_name"]:
            plan.append({"rom_id": r["id"], "system": r["system_key"],
                         "old": r["stored_name"], "new": new})
    return {"system": target_system, "plan": plan}
