"""Fill Korean display names for the Atari Lynx library (no Korean release exists,
so these are LLM transliterations). Renames each rom to 'Korean (English)' with
the RELEASE YEAR stripped from the title (kept in original_name + a side memo
file), matching the rest of the library (ngp/a2600 stored_names carry no year).

Writes:
  - data/korean_names/lynx.json   (english base -> Korean; reused on re-import/upload)
  - data/library/public/_data/lynx_release_years.json  (english base -> year memo)
"""
import json
import re
import sqlite3
from pathlib import Path

from app import config, db
from app.services import gamelist, name_index, renames, storage

SID = config.SHARED_SESSION_ID

# English base title (parens/brackets stripped) -> Korean transliteration.
KMAP = {
    "APB - All Points Bulletin": "APB - 올 포인츠 불러틴",
    "Awesome Golf": "어썸 골프",
    "Baseball Heroes": "베이스볼 히어로즈",
    "Basketbrawl": "바스켓브롤",
    "Batman Returns": "배트맨 리턴즈",
    "Battle Wheels": "배틀 휠즈",
    "Battlezone 2000": "배틀존 2000",
    "Bill & Ted's Excellent Adventure": "빌 & 테드의 엑설런트 어드벤처",
    "Block Out": "블록 아웃",
    "Blue Lightning": "블루 라이트닝",
    "Bubble Trouble": "버블 트러블",
    "California Games": "캘리포니아 게임즈",
    "Checkered Flag": "체커드 플래그",
    "Chip's Challenge": "칩스 챌린지",
    "Crystal Mines II": "크리스탈 마인즈 II",
    "Desert Strike - Return to the Gulf": "데저트 스트라이크 - 리턴 투 더 걸프",
    "Dinolympics": "디놀림픽스",
    "Dirty Larry - Renegade Cop": "더티 래리 - 레니게이드 캅",
    "Double Dragon": "더블 드래곤",
    "Dracula - The Undead": "드라큘라 - 디 언데드",
    "Dragnet": "드래그넷",
    "Electrocop": "일렉트로캅",
    "European Soccer Challenge": "유러피언 사커 챌린지",
    "Fat Bobby": "팻 바비",
    "Fidelity Ultimate Chess Challenge": "피델리티 얼티밋 체스 챌린지",
    "Gates of Zendocon, The": "게이츠 오브 젠도콘",
    "Gauntlet - The Third Encounter": "건틀릿 - 더 서드 인카운터",
    "Gordo 106 - The Mutated Lab Monkey": "고르도 106 - 더 뮤테이티드 랩 몽키",
    "Hard Drivin'": "하드 드라이빈",
    "Hockey": "하키",
    "Hydra": "하이드라",
    "Ishido - The Way of the Stones": "이시도 - 더 웨이 오브 더 스톤즈",
    "Jimmy Conners Tennis": "지미 코너스 테니스",
    "Joust": "조스트",
    "Klax": "클랙스",
    "Krazy Ace Minature Golf": "크레이지 에이스 미니어처 골프",
    "Kung Food": "쿵 푸드",
    "Lemmings": "레밍즈",
    "Lexis": "렉시스",
    "Lode Runner": "로드 러너",
    "Lynx Casino": "링스 카지노",
    "Malibu Bikini Volleyball": "말리부 비키니 발리볼",
    "Ms. Pac-Man": "미즈 팩맨",
    "NFL Football": "NFL 풋볼",
    "Ninja Gaiden": "닌자 가이덴",
    "Ninja Gaiden III - The Ancient Ship of Doom": "닌자 가이덴 III - 디 에인션트 십 오브 둠",
    "Pac-Land": "팩랜드",
    "Paperboy": "페이퍼보이",
    "Pinball Jam": "핀볼 잼",
    "Pit Fighter - The Ultimate Competition": "핏 파이터 - 디 얼티밋 컴페티션",
    "Power Factor": "파워 팩터",
    "Qix": "큐익스",
    "Raiden": "라이덴",
    "Rampage": "램페이지",
    "Rampart": "램파트",
    "RoadBlasters": "로드블래스터즈",
    "Robo-Squash": "로보 스쿼시",
    "Robotron 2084": "로보트론 2084",
    "Rygar - Legendary Warrior": "라이가 - 레전더리 워리어",
    "S.T.U.N. Runner": "S.T.U.N. 러너",
    "Scrapyard Dog": "스크랩야드 독",
    "Shadow of the Beast": "섀도우 오브 더 비스트",
    "Shanghai": "상하이",
    "Steel Talons": "스틸 탤론즈",
    "Super Asteroids & Missile Command": "슈퍼 아스테로이드 & 미사일 커맨드",
    "Super Off-Road": "슈퍼 오프로드",
    "Super Skweek": "슈퍼 스퀵",
    "Switchblade II": "스위치블레이드 II",
    "T-Tris by Bastian Schick": "T-트리스",
    "Todd's Adventure in Slime World": "토드의 어드벤처 인 슬라임 월드",
    "Toki": "토키",
    "Tournament Cyberball 2072": "토너먼트 사이버볼 2072",
    "Turbo Sub": "터보 서브",
    "Viking Child": "바이킹 차일드",
    "Warbirds": "워버즈",
    "World Class Soccer": "월드 클래스 사커",
    "Xenophobe": "제노포브",
    "Xybots": "자이보츠",
    "Zarlor Mercenary": "잘러 머서너리",
}

_TAGS = re.compile(r"\s*[(\[].*?[)\]]")
_YEAR = re.compile(r"\((\d{4})\)")


def base_title(stored: str) -> str:
    stem = stored.rsplit(".", 1)[0]
    return _TAGS.sub("", stem).strip()


# 1) Persist the transliteration map + a year memo.
kn_dir = config.DATA_DIR / "korean_names"
kn_dir.mkdir(parents=True, exist_ok=True)
(kn_dir / "lynx.json").write_text(json.dumps(KMAP, ensure_ascii=False, indent=2), encoding="utf-8")

with db.connect() as conn:
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM roms WHERE session_id=? AND system_key='lynx' ORDER BY stored_name", (SID,))]

years = {}
for r in rows:
    m = _YEAR.search(r["stored_name"]) or _YEAR.search(r["original_name"] or "")
    if m:
        years[base_title(r["stored_name"])] = m.group(1)
memo = config.DATA_DIR / "library" / "public" / "_data" / "lynx_release_years.json"
memo.parent.mkdir(parents=True, exist_ok=True)
memo.write_text(json.dumps(years, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

# 2) Rename each rom to 'Korean (English)' — year dropped from the title, kept in
#    original_name (untouched) + the memo above.
renamed = miss = 0
missing = []
for rom in rows:
    eng = base_title(rom["stored_name"])
    kor = KMAP.get(eng)
    if not kor:
        miss += 1
        missing.append(eng)
        continue
    new_base = gamelist.compose_name(kor, eng)          # 'Korean (English)'
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
        # The library convention keeps korean_name NULL and lets display_name derive
        # from the 'Korean (English)' stored_name → the English stays visible.
        try:
            name_index.store(conn, name_index.hash_file(storage.session_root(SID) / upd["rom_path"]),
                             "lynx", new_base, "manual")
        except Exception:
            pass
    renamed += 1

print(f"korean lynx: renamed {renamed}, missing-map {miss} {missing}")
print(f"year memo: {len(years)} entries -> {memo}")
