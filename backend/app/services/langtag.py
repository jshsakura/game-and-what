"""Detect original language + Korean-patch status from a ROM filename.

The 꿀렁 Korean fan-translation convention encodes it in a paren tag, e.g.
  '... (Korea-patch J-K v20200316 v1.0).nes'  → J→K  (Japanese original, Korean patch)
  '... (Korea-patch U-K).nes'                  → U→K  (US/English original, Korean patch)
  '... (Korea-patch Unl-K).nes'                → Unl→K (unlicensed original, Korean patch)
A patch marker therefore yields BOTH the original language AND the fact that a
Korean translation exists. Without a marker we fall back to the standard region
tag ('(Japan)', '(USA)', '(Europe)', '(World)', '(Korea)'…) for the original
language; the play language then equals the original (no patch applied).

Other sites tag prepatched dumps their own way ('... (KP).gb' = Korean Patch);
those are NOT detected on purpose — one-off conventions aren't worth chasing.
Flag such a rom by hand instead (PATCH /roms/{id}/lang → lang_source='manual',
which the auto-scan then leaves alone).

Pure + immutable: every function returns a NEW frozen LangInfo, never mutates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

# 'X' in a 'X-Y' patch pair, or a region word → our language code.
# Region/dump letters are a proxy for the language a dump ships in.
_SRC_LANG = {
    "j": "ja", "u": "en", "e": "en", "w": "en", "k": "ko",
    "c": "zh", "s": "es", "g": "de", "f": "fr", "i": "it",
    "unl": "unl",
}

_REGION_LANG = {
    "japan": "ja", "jp": "ja", "jpn": "ja",
    "usa": "en", "us": "en", "world": "en", "europe": "en", "eur": "en",
    "korea": "ko", "kor": "ko",
    "china": "zh", "spain": "es", "germany": "de", "france": "fr", "italy": "it",
}

# After the word 'patch' (anywhere in a paren tag), the first 'LETTERS-LETTERS'
# pair is the source→target language. '(Korea-patch J-K v…)' → J , K.
_PATCH_RE = re.compile(r"patch[^)]*?\b([A-Za-z]+)\s*-\s*([A-Za-z]+)\b", re.I)
_REGION_RE = re.compile(
    r"\(\s*(japan|jpn|jp|usa|us|world|europe|eur|korea|kor|china|spain|germany|france|italy)\b",
    re.I,
)


@dataclass(frozen=True)
class LangInfo:
    """orig_lang: language of the source dump (None = unknown).
    play_lang : language the game actually runs in (= 'ko' once Korean-patched).
    is_korean_patched: a Korean translation patch is applied.
    source    : 'auto' (filename-derived) or 'manual' (user override)."""
    orig_lang: str | None
    play_lang: str | None
    is_korean_patched: bool
    source: str = "auto"


def _lang_code(token: str) -> str | None:
    return _SRC_LANG.get((token or "").strip().lower())


def detect(filename: str) -> LangInfo:
    """Best-effort language detection for one ROM. Works on a full filename or a
    bare stem. Never raises — an unrecognized name returns all-unknown."""
    name = filename or ""

    m = _PATCH_RE.search(name)
    if m:
        orig = _lang_code(m.group(1))
        patched = _lang_code(m.group(2))
        return LangInfo(
            orig_lang=orig,
            play_lang=patched or orig,
            is_korean_patched=(patched == "ko"),
        )

    r = _REGION_RE.search(name)
    orig = _REGION_LANG.get(r.group(1).lower()) if r else None
    return LangInfo(orig_lang=orig, play_lang=orig, is_korean_patched=False)


def detect_any(*names: str) -> LangInfo:
    """Detect across several name variants (e.g. original_name + stored_name) and
    return the most informative result: a Korean-patch hit wins outright, else the
    first variant that yields a known original language. Used to backfill EXISTING
    library roms whose Korean stored_name has lost the marker but whose
    original_name still carries it."""
    best = LangInfo(orig_lang=None, play_lang=None, is_korean_patched=False)
    for n in names:
        info = detect(n)
        if info.is_korean_patched:
            return info
        if best.orig_lang is None and info.orig_lang is not None:
            best = info
    return best


def manual_patch(info: LangInfo, patched: bool) -> LangInfo:
    """User override of the Korean-patch flag. Returns a NEW LangInfo marked
    'manual' so a later auto re-scan won't clobber the human decision."""
    return replace(
        info,
        is_korean_patched=patched,
        play_lang="ko" if patched else info.orig_lang,
        source="manual",
    )
