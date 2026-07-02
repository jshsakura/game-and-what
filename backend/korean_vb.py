"""Fill Korean display names for the Virtual Boy library (no Korean release exists,
so these are LLM transliterations). Renames each rom to 'Korean (English) (tags)'.

Unlike the Lynx pass, VB No-Intro names carry REGION tags (Japan/USA), not years,
and include region-variant pairs (Red Alarm, Vertical Force). So we KEEP the
original tag suffix on the stored name — the Korean+English go in front, the tags
stay behind — which keeps every name unique (no clash), reversible, and preserves
the JP/US distinction. korean_name column is left NULL on purpose (see note below).

Writes data/korean_names/vb.json (english base -> Korean; reused on re-import).
"""
import json
import re

from app import config, db
from app.services import gamelist, name_index, renames, storage

SID = config.SHARED_SESSION_ID
SYSTEM = "vb"

# Tag-stripped English title -> Korean transliteration.
KMAP = {
    "3-D Tetris": "3-D 테트리스",
    "Bound High": "바운드 하이",
    "Galactic Pinball": "갤럭틱 핀볼",
    "Golf": "골프",
    "Innsmouth no Yakata": "인스머스 노 야카타",
    "Jack Bros.": "잭 브로스",
    "Jack Bros. no Meiro de Hiihoo!": "잭 브로스 노 메이로 데 히호!",
    "Mario Clash": "마리오 클래시",
    "Mario's Tennis": "마리오 테니스",
    "Nester's Funky Bowling": "네스터스 펑키 볼링",
    "Niko-chan Battle": "니코짱 배틀",
    "Panic Bomber": "패닉 봄버",
    "Red Alarm": "레드 알람",
    "SD Gundam - Dimension War": "SD 건담 - 디멘션 워",
    "Space Invaders - Virtual Collection": "스페이스 인베이더 - 버추얼 컬렉션",
    "Space Pinball": "스페이스 핀볼",
    "Space Squash": "스페이스 스쿼시",
    "T&E Virtual Golf": "T&E 버추얼 골프",
    "Teleroboxer": "텔레로복서",
    "Tobidase! Panibon": "토비다세! 파니봉",
    "V-Tetris": "V-테트리스",
    "Vertical Force": "버티컬 포스",
    "Virtual Bowling": "버추얼 볼링",
    "Virtual Boy Wario Land": "버추얼 보이 와리오 랜드",
    "Virtual Fishing": "버추얼 피싱",
    "Virtual Lab": "버추얼 랩",
    "Virtual League Baseball": "버추얼 리그 베이스볼",
    "Virtual Pro Yakyuu '95": "버추얼 프로 야큐 '95",
    "Waterworld": "워터월드",
}

_TAG_START = re.compile(r"\s*[(\[]")


def split_title(stored: str) -> tuple[str, str]:
    """('Red Alarm (Japan).vb') -> ('Red Alarm', ' (Japan)'): clean title + the
    original tag suffix (region/proto/etc.), extension already dropped."""
    stem = stored.rsplit(".", 1)[0]
    m = _TAG_START.search(stem)
    if not m:
        return stem.strip(), ""
    return stem[:m.start()].strip(), stem[m.start():]


# 1) Persist the transliteration map for re-import/upload.
kn_dir = config.DATA_DIR / "korean_names"
kn_dir.mkdir(parents=True, exist_ok=True)
(kn_dir / "vb.json").write_text(json.dumps(KMAP, ensure_ascii=False, indent=2), encoding="utf-8")

with db.connect() as conn:
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM roms WHERE session_id=? AND system_key=? ORDER BY stored_name",
        (SID, SYSTEM))]

# 2) Rename each rom to 'Korean (English) (tags)'.
renamed = miss = 0
missing = []
for rom in rows:
    title, tags = split_title(rom["stored_name"])
    kor = KMAP.get(title)
    if not kor:
        miss += 1
        missing.append(title)
        continue
    new_base = gamelist.compose_name(kor, title) + tags     # 'Korean (English) (Japan)'
    ext = rom["stored_name"].rsplit(".", 1)[-1] if "." in rom["stored_name"] else ""
    new = f"{storage.safe_name(new_base)}.{ext}" if ext else storage.safe_name(new_base)
    if new == rom["stored_name"]:
        continue
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, system_key, stored_name, rom_path, cover_path FROM roms WHERE id=?",
            (rom["id"],)).fetchone()
        if not row:
            continue
        upd = renames.rename_rom(conn, SID, dict(row), new, suffix_on_clash=True)
        # NOTE: deliberately do NOT set the korean_name column. _enrich_rom uses
        # display_name = korean_name when present (Korean ONLY, hiding the English).
        # Keep it NULL so display_name derives from the 'Korean (English)' stored_name
        # → the English stays visible.
        try:
            name_index.store(conn, name_index.hash_file(storage.session_root(SID) / upd["rom_path"]),
                             SYSTEM, new_base, "manual")
        except Exception:
            pass
    renamed += 1

print(f"korean vb: renamed {renamed}, missing-map {miss} {missing}")
