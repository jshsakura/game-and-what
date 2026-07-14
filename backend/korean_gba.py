"""Mark the Korean GBA games (한글패치 + 정식 한국판) in the library.

A Korean fan-patch leaves NO trace outside the picture: it keeps the original cart
header, the original 4-char game code and the original region letter, and these files
carry no 한글/K tag in their names either. `langtag.detect()` therefore finds nothing,
and the import left all 32 GBA roms unflagged — which is wrong, and hid the fact that
Pokémon FireRed/LeafGreen here are Korean patches of the US release.

The only reliable check is to RUN each rom and read the screen (scripts/idlefind/shot.c
renders a frame headless). The list below is what that showed. Mirrors korean_lynx.py.

Idempotent: re-running just re-asserts the same flags.
"""
from app import db
from app.services import events, langtag

SESSION = "public"
SYSTEM = "gba"

# stored_name (without .gba) -> what the screen showed.
KOREAN = {
    "포켓몬스터 - 루비 (Pokemon Ruby)": "정식 한국 발매판 (AXVK)",
    "포켓몬스터 - 사파이어 (Pokemon Sapphire)": "정식 한국 발매판 (AXPK)",
    "포켓몬스터 - 에메랄드 (Pokemon - Emerald Version)": "정식 한국 발매판 (BPEK)",
    # header says BPRE/BPGE — the US release. The content is a Korean patch; the "1.1"
    # in the filename is the patch version, not a rom revision.
    "포켓몬스터 파이어레드1.1": "한글패치 — 미국판 헤더(BPRE)",
    "포켓몬스터 리프그린1.1": "한글패치 — 미국판 헤더(BPGE)",
    "캐슬바니아 - 서클 오브 더 문": "한글패치 — '때는 1830년'",
    "파이널 판타지 택틱스 어드밴스 (Final Fantasy Tactics Advance)": "한글패치 — 타이틀 로고 한글",
    "리듬세상 어드밴스1.3": "한글패치 — '소리에 맞춰서 A버튼을 눌러주세요'",
    "메이드 인 와리오 (WarioWare, Inc - Minigame Mania)": "한글패치 — '뭐라도 입력해!'",
    "다운타운 열혈물어EX": "한글패치 — '쿠니오', 도구/기술/상태",
    "록맨 제로 3 (Megaman Zero 3)": "한글패치 — '네오·아르카디아의…'",
    "록맨 제로 4 (Megaman Zero 4)": "한글패치 — 메뉴 한글",
    "슈퍼마리오월드": "한글패치 — '요스타 섬에 온것을 환영해요!'",
}

# Checked and NOT Korean, so nobody re-checks them: 록맨 제로 1 is Japanese
# ('つ、ついに、見つけたぞ！'), 슈퍼마리오 브라더스3 is Japanese, and 마리오 골프 /
# 별의 커비 / F-ZERO / 그라디우스 / 메탈슬러그 / 핀볼류 / 슈퍼 퍼즐파이터 are English.


def main() -> None:
    flagged = missing = 0
    with db.connect() as conn:
        for stem, why in KOREAN.items():
            row = conn.execute(
                "SELECT id, stored_name, orig_lang, play_lang, is_korean_patched "
                "FROM roms WHERE session_id=? AND system_key=? AND stored_name=?",
                (SESSION, SYSTEM, f"{stem}.gba"),
            ).fetchone()
            if row is None:
                print(f"  [없음] {stem}")
                missing += 1
                continue

            base = langtag.LangInfo(
                orig_lang=row["orig_lang"], play_lang=row["play_lang"],
                is_korean_patched=bool(row["is_korean_patched"]),
            )
            updated = langtag.manual_patch(base, True)
            conn.execute(
                "UPDATE roms SET play_lang=?, is_korean_patched=1, lang_source='manual', "
                "cover_flag='ko' WHERE id=?",
                (updated.play_lang, row["id"]),
            )
            if not row["is_korean_patched"]:
                events.log(conn, SESSION, "lang_patch", rom_id=row["id"],
                           rom_name=row["stored_name"], system_key=SYSTEM,
                           meta={"patched": True, "evidence": why})
            print(f"  🇰🇷 {stem[:44]:<46} {why}")
            flagged += 1

    print(f"\n{flagged} marked, {missing} not found")
    print("NOTE: the baked cover .img still carries the old flag — re-bake it with "
          "PATCH /roms/{id}/cover/flag, which is what set them the first time.")


if __name__ == "__main__":
    main()
