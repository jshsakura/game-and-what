/* gpSP idle-loop entries, measured by RUNNING each rom (scripts/idlefind).
 * idle_loop_target_pc is the backward BRANCH — the PC gpSP compares against
 * in cpu.cc — not the loop's start, which is what mGBA reports.
 *
 * exec = real CPU work per frame with the skip active, out of 280,896.
 * The M7 leaves the CPU roughly 160,000 cycles at a 340MHz OC.
 */

   {
      // 도날드덕 어드밴스
      //   exec 16,664/280,896 cy/frame (94% idle) — CPU 10% of budget
      "ADKP",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8002f30,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // F-제로 맥시멈 벨로시티 (F-Zero - Maximum Velocity)
      //   exec 61,334/280,896 cy/frame (78% idle) — CPU 38% of budget
      "AFZE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000c2e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 핀볼 오브 데드 (Pinball of the Dead, The)
      //   exec 63,154/280,896 cy/frame (78% idle) — CPU 39% of budget
      "APDE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000300,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 다운타운 열혈물어EX (한글패치)
      //   exec 65,065/280,896 cy/frame (77% idle) — CPU 41% of budget
      "BDTE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x800065a,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 스크류 브레이커
      //   exec 66,296/280,896 cy/frame (76% idle) — CPU 41% of budget
      "V49J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80006c2,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 페르시아의 왕자 - 시간의 모래
      //   exec 68,058/280,896 cy/frame (76% idle) — CPU 43% of budget
      "BPYP",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80900f2,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 핀볼 챌린지 디럭스 (Pinball Challenge Deluxe)
      //   exec 68,473/280,896 cy/frame (76% idle) — CPU 43% of budget
      "APLP",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80075a6,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 마리오 테니스 어드밴스 (Mario Tennis Advance)
      //   exec 70,699/280,896 cy/frame (75% idle) — CPU 44% of budget
      "BTMJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8013888,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 별의 커비 - 꿈의 샘 디럭스 (Kirby - Nightmare in Dream Land)
      //   exec 71,428/280,896 cy/frame (75% idle) — CPU 45% of budget
      "A7KE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000fae,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 마리오 골프 어드밴스 투어 (Mario Golf - Advance Tour)
      //   exec 71,769/280,896 cy/frame (74% idle) — CPU 45% of budget
      "BMGE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8014e0a,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AXPK  포켓몬스터 사파이어 (정식 한국판)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 72,648/280,896 (74% idle) — CPU 45% of budget
    */

   /* AXVK  포켓몬스터 루비 (정식 한국판)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 73,266/280,896 (74% idle) — CPU 46% of budget
    */

   {
      // 리듬세상 (한글패치)
      //   exec 75,039/280,896 cy/frame (73% idle) — CPU 47% of budget
      "BRIJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80013d4,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 캐슬바니아 - 서클 오브 더 문 (한글패치)
      //   exec 76,293/280,896 cy/frame (73% idle) — CPU 48% of budget
      "AAMJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80003ce,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 포켓몬스터 리프그린 (한글패치, 미국판 헤더)
      //   exec 77,946/280,896 cy/frame (72% idle) — CPU 49% of budget
      "BPGE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80008c6,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 포켓몬스터 에메랄드 (정식 한국판)
      //   exec 78,796/280,896 cy/frame (72% idle) — CPU 49% of budget
      "BPEK",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80008ce,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 포켓몬스터 파이어레드 (한글패치, 미국판 헤더)
      //   exec 78,916/280,896 cy/frame (72% idle) — CPU 49% of budget
      "BPRE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80008c6,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 슈퍼마리오 브라더스3 (Super Mario Advance 4 - Super Mario 3 + Mario Brothers)
      //   exec 81,845/280,896 cy/frame (71% idle) — CPU 51% of budget
      "AX4J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000732,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 마리오 vs. 동키콩 (Mario vs. Donkey Kong)
      //   exec 87,371/280,896 cy/frame (69% idle) — CPU 55% of budget
      "BM5E",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8033eec,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 그라디우스 갤럭시즈 (Gradius Galaxies)
      //   exec 93,880/280,896 cy/frame (67% idle) — CPU 59% of budget
      "AGAE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8013844,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 록맨 제로 1 (Megaman Zero 1)
      //   exec 98,249/280,896 cy/frame (65% idle) — CPU 61% of budget
      "ARZJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80004f6,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 황금의 태양 2 - 잃어버린 시대 (Ougon no Taiyou - Ushinawareshi Toki)
      //   exec 102,002/280,896 cy/frame (64% idle) — CPU 64% of budget
      "AGFJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8013542,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 록맨 에그제
      //   exec 106,477/280,896 cy/frame (62% idle) — CPU 67% of budget
      "AREJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000338,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 메탈슬러그 어드밴스 (Metal Slug Advance)
      //   exec 111,771/280,896 cy/frame (60% idle) — CPU 70% of budget
      "BSME",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000298,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 록맨 제로 4 (한글패치)
      //   exec 115,793/280,896 cy/frame (59% idle) — CPU 72% of budget
      "B4ZJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000914,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 파이널 판타지 택틱스 어드밴스 (한글패치)
      //   exec 117,713/280,896 cy/frame (58% idle) — CPU 74% of budget
      "AFXJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000428,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 록맨 제로 2 (Megaman Zero 2)
      //   exec 121,001/280,896 cy/frame (57% idle) — CPU 76% of budget
      "A62J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x800066c,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 슈퍼마리오월드 (한글패치)
      //   exec 137,673/280,896 cy/frame (51% idle) — CPU 86% of budget
      "AA2C",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80005ec,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 록맨 제로 3 (한글패치)
      //   exec 137,998/280,896 cy/frame (51% idle) — CPU 86% of budget
      "BZ3J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80019c4,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 메이드 인 와리오 (한글패치)
      //   exec 142,521/280,896 cy/frame (49% idle) — CPU 89% of budget
      "AZWJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000f5e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 슈퍼 퍼즐파이터II Turbo터보
      //   exec 152,070/280,896 cy/frame (46% idle) — CPU 95% of budget
      "AZ8E",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8002b5e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 슈퍼마리오 요시아일랜드 (Super Mario Advance 3 - Yoshi's Island + Mario Brothers)
      //   exec 175,310/280,896 cy/frame (38% idle) — CPU 110% of budget
      "A3AJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8002ba4,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

