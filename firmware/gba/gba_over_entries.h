/* gpSP idle-loop entries, measured by RUNNING each rom (scripts/idlefind).
 * idle_loop_target_pc is the PC gpSP ends the frame slice at: the backward
 * branch that closes the wait loop, or — where the loop hops rather than
 * branching straight back — a landing point inside it. cpu.cc:3063 compares
 * reg[REG_PC] after every instruction, so either does the job, and so does an
 * address in IWRAM/EWRAM (an emulator-cart runs its wait from RAM).
 *
 * exec = real CPU work per frame with the skip active, out of 280,896.
 * The M7 leaves the CPU roughly 90,000 cycles at a 340MHz OC.
 */

   /* MPCE  포켓몬스터 - 볼륨 3
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 531/280,896 (100% idle) — CPU 1% of budget
    */

   /* MPAE  포켓몬스터 - 볼륨 1
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 545/280,896 (100% idle) — CPU 1% of budget
    */

   /* MPBE  포켓몬스터 - 볼륨 2
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 545/280,896 (100% idle) — CPU 1% of budget
    */

   /* MPDE  포켓몬스터 - 볼륨 4
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 545/280,896 (100% idle) — CPU 1% of budget
    */

   /* B5NE  남코 박물관 50주년 기념 (Namco Museum - 50th Anniversary)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 729/280,896 (100% idle) — CPU 1% of budget
    */

   /* MTMF  틴에이지 뮤턴트 닌자 터틀즈 - 이사하기 - 1편
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 1,085/280,896 (100% idle) — CPU 1% of budget
    */

   /* MSHE  소닉 X - 볼륨 1
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 1,465/280,896 (99% idle) — CPU 2% of budget
    */

   /* MTME  틴에이지 뮤턴트 닌자 터틀즈 - 1편
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 1,465/280,896 (99% idle) — CPU 2% of budget
    */

   /* MDBE  드래곤볼 GT - 볼륨 1
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 1,648/280,896 (99% idle) — CPU 2% of budget
    */

   /* BPZJ  파즈닌 (Pazuninn - Umininn no Puzzle de Nimu)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 2,958/280,896 (99% idle) — CPU 3% of budget
    */

   /* ABME  슈퍼 버스트 어 무브 (Super Bust-A-Move)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 3,855/280,896 (99% idle) — CPU 4% of budget
    */

   /* A9HJ  드래곤퀘스트 - 캐러반하트 (Dragon Quest Monsters - Caravan Heart)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 4,843/280,896 (98% idle) — CPU 5% of budget
    */

   {
      // 세가 아케이드 갤러리
      //   exec 5,679/280,896 cy/frame (98% idle) — CPU 6% of budget
      "AYPP",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x3005d18,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 도날드덕 어드밴스
      //   exec 5,985/280,896 cy/frame (98% idle) — CPU 7% of budget
      "ADKP",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8002f30,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* ZMPJ  켐코 MP3 플레이어
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 6,011/280,896 (98% idle) — CPU 7% of budget
    */

   /* A3ZE  스트리트 잼
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 8,035/280,896 (97% idle) — CPU 9% of budget
    */

   /* BGHJ  학교의 괴담 - 백요상의 봉인 (Gakkou no Kaidan - Hyakuyoubako no Fuuin)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 8,266/280,896 (97% idle) — CPU 9% of budget
    */

   /* BGTE  그랜드 테프트 오토 어드밴스 (Grand Theft Auto)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 8,491/280,896 (97% idle) — CPU 9% of budget
    */

   /* BGTP  그랜드 테프트 오토 어드밴스 샘플
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 8,491/280,896 (97% idle) — CPU 9% of budget
    */

   {
      // 스타워즈 트릴로지 - 어프렌티스 오브 더 포스 (Star Wars Trilogy - Apprentice of the Force)
      //   exec 8,793/280,896 cy/frame (97% idle) — CPU 10% of budget
      "BCKE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80a0922,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BC6E  캡콤 클래식스 - 미니 믹스 (Capcom Classics Mini Mix)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 8,943/280,896 (97% idle) — CPU 10% of budget
    */

   /* ADME  둠
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 8,981/280,896 (97% idle) — CPU 10% of budget
    */

   {
      // 엑스맨 - Reign of Apocalypse
      //   exec 9,734/280,896 cy/frame (97% idle) — CPU 11% of budget
      "AXME",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8007f74,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 이니셜D 어나더 스테이지 (Initial D - Another Stage)
      //   exec 10,095/280,896 cy/frame (96% idle) — CPU 11% of budget
      "AINJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000400,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 사일런트힐 플레이노벨 (Play Novel - Silent Hill)
      //   exec 10,269/280,896 cy/frame (96% idle) — CPU 11% of budget
      "ASHJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80130a8,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BNSE  니드 포 스피드 언더그라운드 (Need for Speed - Underground)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 10,517/280,896 (96% idle) — CPU 12% of budget
    */

   /* A9CE  CT 스페셜 포스 2 - 백 인 더 트렌치스 (CT Special Forces 2 - Back in the Trenches)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 10,690/280,896 (96% idle) — CPU 12% of budget
    */

   {
      // 환상수호전 카드 스토리즈 (Gensou Suikoden - Card Stories)
      //   exec 10,703/280,896 cy/frame (96% idle) — CPU 12% of budget
      "AGKJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8072f52,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BL7E  레고 스타워즈2 (LEGO Star Wars II - The Original Trilogy)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 12,624/280,896 (96% idle) — CPU 14% of budget
    */

   /* ABFE  브레스 오브 파이어
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 12,931/280,896 (95% idle) — CPU 14% of budget
    */

   /* ANME  남코 뮤지엄 (Namco Museum)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 13,096/280,896 (95% idle) — CPU 15% of budget
    */

   /* A2GE  GT 어드밴스 3 - 프로 콘셉트 레이싱 (GT Advance 3 - Pro Concept Racing)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 14,289/280,896 (95% idle) — CPU 16% of budget
    */

   /* AKIJ  기기괴계 어드밴스
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 14,464/280,896 (95% idle) — CPU 16% of budget
    */

   /* AKOE  킹 오브 파이터즈 EX 네오 블러드 (King of Fighters EX, The - NeoBlood)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 14,612/280,896 (95% idle) — CPU 16% of budget
    */

   /* DEMO  퍼즐보블
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 15,428/280,896 (95% idle) — CPU 17% of budget
    */

   {
      // 길티 기어 X 어드밴스 에디션 (Guilty Gear X - Advance Edition)
      //   exec 15,743/280,896 cy/frame (94% idle) — CPU 17% of budget
      "AGXE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000332,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BPWP  파워레인저 - 닌자스톰
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 15,966/280,896 (94% idle) — CPU 18% of budget
    */

   {
      // 도쿄뮤뮤 (Hamepane - Tokyo Mew Mew)
      //   exec 16,135/280,896 cy/frame (94% idle) — CPU 18% of budget
      "AM7J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000598,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 닌텐도 MP3 플레이어
      //   exec 16,155/280,896 cy/frame (94% idle) — CPU 18% of budget
      "ZMDE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x20314a6,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AGVJ  고스트트랩
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 16,384/280,896 (94% idle) — CPU 18% of budget
    */

   {
      // 크레이지택시 (Crazy Taxi - Catch a Ride)
      //   exec 17,119/280,896 cy/frame (94% idle) — CPU 19% of budget
      "A3CE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8016234,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 길티기어X - 어드밴스 에디션t1]
      //   exec 17,480/280,896 cy/frame (94% idle) — CPU 19% of budget
      "AGXJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000332,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AB2E  브레스 오브 파이어2
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 17,684/280,896 (94% idle) — CPU 20% of budget
    */

   /* BRGE  유유백서 - 토너먼트 택틱스 (Yu Yu Hakusho - Ghostfiles - Tournament Tactics)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 18,006/280,896 (94% idle) — CPU 20% of budget
    */

   /* AN6E  클로노아 2 드림 챔피언 토너먼트 (Klonoa 2 - Dream Champ Tournament)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 18,062/280,896 (94% idle) — CPU 20% of budget
    */

   /* BC3P  CT 스페셜 포스 3 - 바이오테러 (CT Special Forces 3 - Bioterror)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 19,116/280,896 (93% idle) — CPU 21% of budget
    */

   {
      // 세가 아케이드 갤러리 (SEGA Arcade Gallery)
      //   exec 19,150/280,896 cy/frame (93% idle) — CPU 21% of budget
      "AYPE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x3005d18,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AN6J  바람의 크로노아G2 (Kaze no Klonoa G2 - Dream Champ Tournament)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 19,270/280,896 (93% idle) — CPU 21% of budget
    */

   /* A2BJ  Bubble Bobble - Old & New (Korea-patch J-K v20120421)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 19,332/280,896 (93% idle) — CPU 21% of budget
    */

   /* BZIE  니모를 찾아서 - 계속되는 모험
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 19,479/280,896 (93% idle) — CPU 22% of budget
    */

   {
      // Daisenryaku for Game Boy Advance (Korea-patch J-K v20141222 v.01)
      //   exec 19,697/280,896 cy/frame (93% idle) — CPU 22% of budget
      "ADSJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80006c4,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* B2CE  팩맨 월드 2 (Pac-Man World 2)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 20,647/280,896 (93% idle) — CPU 23% of budget
    */

   {
      // 다리우스 R
      //   exec 21,149/280,896 cy/frame (92% idle) — CPU 23% of budget
      "A2DJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8001b0e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AKCE  코나미 아케이드게임 컬렉션
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 21,153/280,896 (92% idle) — CPU 24% of budget
    */

   /* AGEE  Gekido Advance - Kintaro's Revenge (U)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 21,569/280,896 (92% idle) — CPU 24% of budget
    */

   /* AGEP  격기도 어드밴스 킨타로의 복수 (Gekido Advance - Kintaro's Revenge)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 21,569/280,896 (92% idle) — CPU 24% of budget
    */

   /* AYLE  Sega Rally Championship (U)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 22,019/280,896 (92% idle) — CPU 24% of budget
    */

   /* AYLJ  세가 랠리 챔피언십 (SEGA Rally Championship)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 22,019/280,896 (92% idle) — CPU 24% of budget
    */

   /* AVTE  버추어 테니스 (Virtua Tennis)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 22,155/280,896 (92% idle) — CPU 25% of budget
    */

   /* BRDE  파워레인저 - SPD (Power Rangers S.P.D.)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 22,976/280,896 (92% idle) — CPU 26% of budget
    */

   /* A5UE  스페이스채널5 (Space Channel 5 - Ulala's Cosmic Attack)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 23,789/280,896 (92% idle) — CPU 26% of budget
    */

   {
      // 역전재판
      //   exec 23,995/280,896 cy/frame (91% idle) — CPU 27% of budget
      "ASBJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000252,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BAHP  에일리언 호미니드
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 26,499/280,896 (91% idle) — CPU 29% of budget
    */

   {
      // 짱구는 못말려 - 시네랜드의 모험 (Shin chan - Aventuras en Cineland)
      //   exec 26,692/280,896 cy/frame (90% idle) — CPU 30% of budget
      "BKCS",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80006b8,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 마리오 테니스 파워 투어 (Mario Tennis - Power Tour)
      //   exec 26,988/280,896 cy/frame (90% idle) — CPU 30% of budget
      "BTME",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80138a0,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 배트맨 - 벤전스 (Batman - Vengeance)
      //   exec 27,068/280,896 cy/frame (90% idle) — CPU 30% of budget
      "ABTE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80596ce,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BPOE  파워레인저 - 다이노썬더
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 27,925/280,896 (90% idle) — CPU 31% of budget
    */

   /* AXYE  SSX 트리키 (SSX Tricky)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 27,945/280,896 (90% idle) — CPU 31% of budget
    */

   {
      // Gyakuten Saiban 3 (Korea-patch J-K v0.5)
      //   exec 28,089/280,896 cy/frame (90% idle) — CPU 31% of budget
      "A3JJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80003f0,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* ADZE  드래곤볼 Z - 컬렉티블 카드 게임 (Dragon Ball Z - Collectible Card Game)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 28,165/280,896 (90% idle) — CPU 31% of budget
    */

   /* AONE  버블 보블 - 올드 앤 뉴 (Bubble Bobble - Old & New)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 28,491/280,896 (90% idle) — CPU 32% of budget
    */

   /* AD5J  미스터 드릴러 에이스
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 28,840/280,896 (90% idle) — CPU 32% of budget
    */

   /* BNFE  니드 포 스피드 언더그라운드 2 (Need for Speed - Underground 2)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 29,331/280,896 (90% idle) — CPU 33% of budget
    */

   /* AB9E  듀얼 블레이즈
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 29,518/280,896 (89% idle) — CPU 33% of budget
    */

   /* BPBJ  삐리리 불어봐 재규어!
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 29,728/280,896 (89% idle) — CPU 33% of budget
    */

   /* AKUJ  흑수염의 쿠룻또 진토리 (Kurohige no Kurutto Jintori)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 30,241/280,896 (89% idle) — CPU 34% of budget
    */

   /* AD2J  미스터 드릴러 2 (Mr. Driller 2)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 30,950/280,896 (89% idle) — CPU 34% of budget
    */

   {
      // 고인돌
      //   exec 30,968/280,896 cy/frame (89% idle) — CPU 34% of budget
      "APHE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x801e40e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BPFJ  뿌요뿌요 피버 (Puyo Puyo Fever)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 31,018/280,896 (89% idle) — CPU 34% of budget
    */

   /* BOJJ  오자루마루 - 달빛 마을 투어 드 오자루 (Ojarumaru - Gekkouchou Sanpo de Ojaru)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 31,426/280,896 (89% idle) — CPU 35% of budget
    */

   /* AGGE  그레믈린 스트라이프 대 기즈모 (Gremlins - Stripe vs Gizmo)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 31,583/280,896 (89% idle) — CPU 35% of budget
    */

   /* AP9P  포켓 뮤직 (Pocket Music)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 31,672/280,896 (89% idle) — CPU 35% of budget
    */

   /* BIXJ  칼쵸비트 (Calciobit)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 31,936/280,896 (89% idle) — CPU 35% of budget
    */

   /* BN4J  강의 낚시3,4 (Kawa no Nushi Tsuri 3 & 4)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 31,994/280,896 (89% idle) — CPU 36% of budget
    */

   /* A8ZJ  진 여신전생 - 퍼즐데콜 (Shin Megami Tensei - Devil Children - Puzzle de Call!)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 32,699/280,896 (88% idle) — CPU 36% of budget
    */

   /* AMBJ  모바일 프로야구 (Mobile Pro Yakyuu - Kantoku no Saihai)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 32,713/280,896 (88% idle) — CPU 36% of budget
    */

   /* BVGJ  비트 제너레이션즈 사운드 보이저 (bit Generations - Soundvoyager)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 33,020/280,896 (88% idle) — CPU 37% of budget
    */

   /* BAMJ  내일의 죠 - 새빨갛게 불타올라라
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 33,026/280,896 (88% idle) — CPU 37% of budget
    */

   /* AKLJ  바람의 크로노아
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 34,537/280,896 (88% idle) — CPU 38% of budget
    */

   /* AD4E  던전 앤 드래곤 - 비홀더의 눈 (Dungeons & Dragons - Eye of the Beholder)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 35,278/280,896 (87% idle) — CPU 39% of budget
    */

   /* A9DE  둠II (Doom II)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 35,456/280,896 (87% idle) — CPU 39% of budget
    */

   {
      // 타이니 툰 어드벤처 - 와키 스태커즈 (Tiny Toon Adventures - Wacky Stackers)
      //   exec 35,606/280,896 cy/frame (87% idle) — CPU 40% of budget
      "AWSE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80027f4,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AKLE  클로노아 제국의 환상 (Klonoa - Empire of Dreams)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 35,702/280,896 (87% idle) — CPU 40% of budget
    */

   {
      // 스타워즈 - 제다이 파워 배틀 (Star Wars - Jedi Power Battles)
      //   exec 36,014/280,896 cy/frame (87% idle) — CPU 40% of budget
      "ASWE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80001da,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* ACRJ  츄츄로켓
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 36,258/280,896 (87% idle) — CPU 40% of budget
    */

   /* ALRE  레고 레이서 2 (LEGO Racers 2)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 36,894/280,896 (87% idle) — CPU 41% of budget
    */

   {
      // 쵸로Q어드밴스2 (Choro Q Advance 2)
      //   exec 37,276/280,896 cy/frame (87% idle) — CPU 41% of budget
      "AQ2J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000c14,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AZKJ  심플 2960 토모다치 시리즈 Vol. 1 - 테이블 게임 콜렉션 (Simple 2960 Tomodachi Series Vol. 1 - The Table Game Collection - Mahjong, Shougi, Hanafuda, Reversi)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 37,449/280,896 (87% idle) — CPU 42% of budget
    */

   /* BIJE  소닉 더 헤지혹
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 38,536/280,896 (86% idle) — CPU 43% of budget
    */

   /* BDGE  디지몬 레이싱 (Digimon Racing)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 39,279/280,896 (86% idle) — CPU 44% of budget
    */

   /* AISJ  월희
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 40,438/280,896 (86% idle) — CPU 45% of budget
    */

   {
      // TMNT (TMNT)
      //   exec 41,238/280,896 cy/frame (85% idle) — CPU 46% of budget
      "BEXE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x803b188,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* A2UJ  마더 1+2 (Mother 1+2)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 41,441/280,896 (85% idle) — CPU 46% of budget
    */

   /* ABMJ  슈퍼 퍼즐보블 어드밴스 (Super Puzzle Bobble Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 41,512/280,896 (85% idle) — CPU 46% of budget
    */

   /* HGRS  히구라시의 울음소리
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 41,631/280,896 (85% idle) — CPU 46% of budget
    */

   {
      // 라라 크로프트 툼레이더 - The Prophecy
      //   exec 42,011/280,896 cy/frame (85% idle) — CPU 47% of budget
      "AUTJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x800f272,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* A4RE  록 앤 롤 레이싱 (Rock 'N Roll Racing)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 42,503/280,896 (85% idle) — CPU 47% of budget
    */

   /* BTRJ  Tower SP, The (Korea-patch J-K v20140218)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 42,870/280,896 (85% idle) — CPU 48% of budget
    */

   /* ACAE  GT 챔피언십 레이싱 (GT Advance - Championship Racing)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 43,058/280,896 (85% idle) — CPU 48% of budget
    */

   /* AMKJ  마리오 카트 어드밴스 + 49 NES
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 43,463/280,896 (85% idle) — CPU 48% of budget
    */

   /* A3KE  인터내셔널 가라테 플러스 (IK+)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 43,965/280,896 (84% idle) — CPU 49% of budget
    */

   /* BH6J  건담 하로 뿌요뿌요 (Kidou Gekidan Haro Ichiza - Haro no Puyo Puyo)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 44,269/280,896 (84% idle) — CPU 49% of budget
    */

   /* AARE  수왕기 (Altered Beast - Guardian of the Realms)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 44,684/280,896 (84% idle) — CPU 50% of budget
    */

   /* ATIJ  테니스의 왕자 - 천재소년 아카데미
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 45,410/280,896 (84% idle) — CPU 50% of budget
    */

   /* AWIJ  하이퍼스포츠 2002 동계 (Hyper Sports 2002 Winter)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 45,611/280,896 (84% idle) — CPU 51% of budget
    */

   /* AC7E  CT 스페셜 포스 (CT Special Forces)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 46,017/280,896 (84% idle) — CPU 51% of budget
    */

   {
      // 역전재판 2 (Gyakuten Saiban 2)
      //   exec 47,188/280,896 cy/frame (83% idle) — CPU 52% of budget
      "A3GJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000262,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BSGJ  모두의 소프트 시리즈 - 모두의 쇼기
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 47,711/280,896 (83% idle) — CPU 53% of budget
    */

   /* 2SME  심볼머지드
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 48,433/280,896 (83% idle) — CPU 54% of budget
    */

   /* BKTJ  강철제국 (Koutetsu Teikoku)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 48,738/280,896 (83% idle) — CPU 54% of budget
    */

   /* BQXE  슈퍼맨 리턴즈 - 고독의 요새 (Superman Returns - Fortress of Solitude)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 48,794/280,896 (83% idle) — CPU 54% of budget
    */

   /* A3MJ  미키와 미니의 매지컬퀘스트
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 49,154/280,896 (83% idle) — CPU 55% of budget
    */

   /* BO8K  원피스 - 고잉 베이스볼 (One Piece - Going Baseball - Haejeok Yaku)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 49,228/280,896 (82% idle) — CPU 55% of budget
    */

   /* BITJ  음양대전기 제로식 (Onmyou Taisenki - Zeroshiki)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 49,290/280,896 (82% idle) — CPU 55% of budget
    */

   /* BHVE  스쿼지 하이브
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 49,346/280,896 (82% idle) — CPU 55% of budget
    */

   /* BUFE  2-in-1 드래곤볼 Z 게임팩 - 부우의 분노 & GT 트랜스포메이션
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 49,705/280,896 (82% idle) — CPU 55% of budget
    */

   {
      // 다운타운 열혈물어EX (한글패치)
      //   exec 49,801/280,896 cy/frame (82% idle) — CPU 55% of budget
      "BDTE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x800065a,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AQAE  가제트 레이서스 (Gadget Racers)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 50,826/280,896 (82% idle) — CPU 56% of budget
    */

   /* A9CP  CT 스페셜 포스 2 - 백 투 헬 (CT Special Forces - Back to Hell)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 50,836/280,896 (82% idle) — CPU 56% of budget
    */

   /* AGSJ  황금의 태양
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 50,863/280,896 (82% idle) — CPU 57% of budget
    */

   /* BKTP  스틸 엠파이어 (Steel Empire)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 51,173/280,896 (82% idle) — CPU 57% of budget
    */

   /* BT2E  틴에이지 뮤턴트 닌자 터틀즈 2 - 배틀 넥서스 (Teenage Mutant Ninja Turtles 2 - Battle Nexus)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 51,382/280,896 (82% idle) — CPU 57% of budget
    */

   /* AIDE  스페이스 인베이더 (Space Invaders)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 51,652/280,896 (82% idle) — CPU 57% of budget
    */

   /* AQAP  페니 레이서스 (Penny Racers)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 51,760/280,896 (82% idle) — CPU 58% of budget
    */

   /* AE7K  Fire Emblem - Rekka no Ken (Korea-patch J-K v20221231 v0.1)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 52,231/280,896 (81% idle) — CPU 58% of budget
    */

   /* AUYJ  유령저택의 24시간 (Yuureiyashiki no Nijuuyojikan)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 52,425/280,896 (81% idle) — CPU 58% of budget
    */

   /* BBKJ  부라부라동키 (Bura Bura Donkey)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 52,571/280,896 (81% idle) — CPU 58% of budget
    */

   /* AHKJ  히카루의 바둑
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 53,043/280,896 (81% idle) — CPU 59% of budget
    */

   {
      // 배트맨 - 라이즈 오브 신 츠
      //   exec 53,159/280,896 cy/frame (81% idle) — CPU 59% of budget
      "BATE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80879f8,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* ASYE  스파이로 - 시즌 오브 아이스
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 53,336/280,896 (81% idle) — CPU 59% of budget
    */

   /* U3IJ  우리들의 태양
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 53,497/280,896 (81% idle) — CPU 59% of budget
    */

   {
      // 록맨 제로 4 (한글패치)
      //   exec 53,533/280,896 cy/frame (81% idle) — CPU 59% of budget
      "B4ZJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000914,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AEGE  익스트림 고스트 버스터즈 - 코드 에크토-1 (Extreme Ghostbusters - Code Ecto-1)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 54,193/280,896 (81% idle) — CPU 60% of budget
    */

   {
      // 쿠루쿠루쿠루링
      //   exec 54,364/280,896 cy/frame (81% idle) — CPU 60% of budget
      "AKRJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000422,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 쿠루 쿠루 쿠루린 (Kurukuru Kururin)
      //   exec 54,570/280,896 cy/frame (81% idle) — CPU 61% of budget
      "AKRP",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000422,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BADE  알라딘 (Aladdin)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 54,835/280,896 (80% idle) — CPU 61% of budget
    */

   {
      // Yu-Gi-Oh! Duel Monsters International - Worldwide Edition (Korea-patch J-K v0.76)
      //   exec 55,395/280,896 cy/frame (80% idle) — CPU 62% of budget
      "AYWJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80896f2,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BR8E  고스트라이더 (Ghost Rider)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 55,497/280,896 (80% idle) — CPU 62% of budget
    */

   /* A8VJ  보보보보 보보보 - 오우기 87.5 바쿠레츠 하나게 신켄 (Boboboubo Boubobo - Ougi 87.5 Bakuretsu Hanage Shinken)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 55,503/280,896 (80% idle) — CPU 62% of budget
    */

   /* AGWP  GT 어드밴스 2 - 랠리 레이싱 (GT Advance 2 - Rally Racing)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 55,763/280,896 (80% idle) — CPU 62% of budget
    */

   /* AGWE  GT 어드밴스 2 - 랠리 레이싱 + 98 NES
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 55,867/280,896 (80% idle) — CPU 62% of budget
    */

   /* AWNJ  마법의 펌프킨
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 55,939/280,896 (80% idle) — CPU 62% of budget
    */

   /* BG8J  간바레! 도지 파이터즈 (Ganbare! Dodge Fighters)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 55,959/280,896 (80% idle) — CPU 62% of budget
    */

   /* AK4J  근육랭킹4 (Kinniku Banzuke - Kongou-kun no Daibouken!)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 56,204/280,896 (80% idle) — CPU 62% of budget
    */

   {
      // Yu-Gi-Oh! Duel Monsters 6 Expert 2 (Korea-patch J-K v0.65)
      //   exec 56,353/280,896 cy/frame (80% idle) — CPU 63% of budget
      "AY6J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x807928e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AQAJ  쵸로Q 어드밴스 (Choro Q Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 57,269/280,896 (80% idle) — CPU 64% of budget
    */

   /* ALFE  드래곤볼 Z - 오공의 유산 II (Dragon Ball Z - The Legacy of Goku II)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 57,393/280,896 (80% idle) — CPU 64% of budget
    */

   /* BLFE  2-in-1 드래곤볼 Z 게임팩 - 오공의 유산 1 & 2
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 57,483/280,896 (80% idle) — CPU 64% of budget
    */

   /* AN8J  Tales of Phantasia (Korea-patch J-K v20120905)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 57,514/280,896 (80% idle) — CPU 64% of budget
    */

   /* ABDJ  볼더 대쉬 EX (Boulder Dash EX)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 57,649/280,896 (79% idle) — CPU 64% of budget
    */

   /* AJFE  정글북 (Jungle Book, The)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 57,694/280,896 (79% idle) — CPU 64% of budget
    */

   /* BOSJ  보보보보 보보보 - 바쿠텐 하지케 타이센 (Boboboubo Boubobo - Bakutou Hajike Taisen)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 57,762/280,896 (79% idle) — CPU 64% of budget
    */

   /* AJFP  디즈니 정글북 2 (Jungle Book 2, The)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 58,389/280,896 (79% idle) — CPU 65% of budget
    */

   /* A4NJ  목장이야기 - 미네랄타운의 친구들
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 58,613/280,896 (79% idle) — CPU 65% of budget
    */

   /* AHZJ  피안화 (Higanbana)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 58,614/280,896 (79% idle) — CPU 65% of budget
    */

   {
      // 데어데블
      //   exec 58,617/280,896 cy/frame (79% idle) — CPU 65% of budget
      "AVLE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80065a8,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* ABDE  Boulder Dash EX (U)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 58,931/280,896 (79% idle) — CPU 65% of budget
    */

   /* BBGE  배트맨 비긴즈 (Batman Begins)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 59,447/280,896 (79% idle) — CPU 66% of budget
    */

   /* 2GBP  GoodBoy Galaxy
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 59,496/280,896 (79% idle) — CPU 66% of budget
    */

   /* BDDJ  더블 드래곤 어드밴스 (Double Dragon Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 59,584/280,896 (79% idle) — CPU 66% of budget
    */

   /* ATCE  탑 기어 GT 챔피언십 (Top Gear GT Championship)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 59,678/280,896 (79% idle) — CPU 66% of budget
    */

   /* ATCX  GT 챔피언십 (GT Championship)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 59,678/280,896 (79% idle) — CPU 66% of budget
    */

   {
      // 에프제로 (F-Zero for Game Boy Advance)
      //   exec 59,709/280,896 cy/frame (79% idle) — CPU 66% of budget
      "AFZJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000c2e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 강철의 연금술사 - 미주의 윤무곡 (Hagane no Renkinjutsushi - Meisou no Rondo)
      //   exec 59,735/280,896 cy/frame (79% idle) — CPU 66% of budget
      "BHRJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8013f60,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 미드나이트 클럽 스트리트 레이싱 (Midnight Club - Street Racing)
      //   exec 59,925/280,896 cy/frame (79% idle) — CPU 67% of budget
      "AMQE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80052a2,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* APRE  파워레인저 - 타임포스 (Power Rangers - Time Force)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 60,090/280,896 (79% idle) — CPU 67% of budget
    */

   /* AM4P  모토GP
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 60,347/280,896 (79% idle) — CPU 67% of budget
    */

   /* AMXD  몬스터 주식회사 (Monster AG, Die)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 60,393/280,896 (78% idle) — CPU 67% of budget
    */

   /* BSPE  스파이더맨2
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 60,603/280,896 (78% idle) — CPU 67% of budget
    */

   {
      // 실황 월드사커 포켓2 (Jikkyou World Soccer Pocket 2)
      //   exec 60,688/280,896 cy/frame (78% idle) — CPU 67% of budget
      "AJKJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80003d8,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* ANXP  닌자 캅 (Ninja Cop)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 60,749/280,896 (78% idle) — CPU 67% of budget
    */

   /* ANXE  닌자파이브-O (Ninja Five-O)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 60,753/280,896 (78% idle) — CPU 68% of budget
    */

   {
      // 택틱스 오우거 외전 - 로디스의 기사
      //   exec 61,394/280,896 cy/frame (78% idle) — CPU 68% of budget
      "ATOJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000590,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AMXE  몬스터 주식회사 (Monsters, Inc.)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 61,550/280,896 (78% idle) — CPU 68% of budget
    */

   {
      // 초마계촌R
      //   exec 61,618/280,896 cy/frame (78% idle) — CPU 68% of budget
      "ACJJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000522,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AZJK  드래곤볼Z - 무공투극 (Dragon Ball Z - Moogongtoogeuk)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 61,863/280,896 (78% idle) — CPU 69% of budget
    */

   /* AT2J  톨네코의 대모험2 어드밴스
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 61,886/280,896 (78% idle) — CPU 69% of budget
    */

   /* AMRP  매니악 레이서즈 어드밴스 (Maniac Racers Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 61,959/280,896 (78% idle) — CPU 69% of budget
    */

   /* AMRE  Motocross Maniacs Advance (U) [!]
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 62,170/280,896 (78% idle) — CPU 69% of budget
    */

   /* AZBJ  배스츠리 시요우제 (Bass Tsuri Shiyouze! - Tournament wa Senryaku da!)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 62,200/280,896 (78% idle) — CPU 69% of budget
    */

   /* AMTJ  메트로이드 - 퓨전 (Metroid Fusion)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 62,335/280,896 (78% idle) — CPU 69% of budget
    */

   /* AWAE  와리오 랜드 4 (Wario Land 4)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 62,403/280,896 (78% idle) — CPU 69% of budget
    */

   {
      // 베이스볼 어드밴스 (Baseball Advance)
      //   exec 62,420/280,896 cy/frame (78% idle) — CPU 69% of budget
      "ABPE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8047038,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AWAJ  와리오랜드 어드밴스
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 62,602/280,896 (78% idle) — CPU 70% of budget
    */

   /* BAGJ  어드밴스 가디언 히어로즈 (Advance Guardian Heroes)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 62,743/280,896 (78% idle) — CPU 70% of budget
    */

   /* AXPK  포켓몬스터 사파이어 (정식 한국판)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 62,828/280,896 (78% idle) — CPU 70% of budget
    */

   /* AXVK  포켓몬스터 루비 (정식 한국판)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 62,828/280,896 (78% idle) — CPU 70% of budget
    */

   /* BMOJ  미나노 오지사마 (Minna no Ouji-sama)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 63,275/280,896 (77% idle) — CPU 70% of budget
    */

   /* A5NE  동키콩 컨트리 (Donkey Kong Country)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 63,907/280,896 (77% idle) — CPU 71% of budget
    */

   /* A5NJ  슈퍼 동키콩 1 (Super Donkey Kong)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 63,989/280,896 (77% idle) — CPU 71% of budget
    */

   {
      // 에프제로 - 팔콘 전설 (F-Zero - Falcon Densetsu)
      //   exec 64,359/280,896 cy/frame (77% idle) — CPU 72% of budget
      "BFZJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000c32,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AOMJ  디즈니스포츠 모토크로스 (Disney Sports - Motocross)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 64,410/280,896 (77% idle) — CPU 72% of budget
    */

   {
      // 에프제로 GP 레전드 (F-Zero - GP Legend)
      //   exec 64,480/280,896 cy/frame (77% idle) — CPU 72% of budget
      "BFZE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000c32,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 핀볼 오브 데드 (Pinball of the Dead, The)
      //   exec 64,535/280,896 cy/frame (77% idle) — CPU 72% of budget
      "APDE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000300,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 스페이스 인베이더EX
      //   exec 64,578/280,896 cy/frame (77% idle) — CPU 72% of budget
      "AIDJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x802cea4,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BABJ  알렉보던 어드밴쳐 - 타워&샤프트 어드밴스
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 64,904/280,896 (77% idle) — CPU 72% of budget
    */

   /* AMRJ  모토크로스 매니악스 어드밴스 (Motocross Maniacs Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 65,241/280,896 (77% idle) — CPU 72% of budget
    */

   {
      // 마리오 골프 어드밴스 투어 (Mario Golf - Advance Tour)
      //   exec 65,567/280,896 cy/frame (77% idle) — CPU 73% of budget
      "BMGE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8014e0a,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 레인보우 식스 - 로그 스피어 (Tom Clancy's Rainbow Six - Rogue Spear)
      //   exec 65,659/280,896 cy/frame (77% idle) — CPU 73% of budget
      "AR6E",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8005b36,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BKDJ  크래쉬밴디쿳 어드밴스 - 두근두근 친구대작전 (Crash Bandicoot Advance - Wakuwaku Tomodachi Daisakusen!)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 66,442/280,896 (76% idle) — CPU 74% of budget
    */

   {
      // 댄싱스워드 - 섬광
      //   exec 66,746/280,896 cy/frame (76% idle) — CPU 74% of budget
      "A9SJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000234,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 짱구는 못말려 - 쇼크 가언의 인형들에 대항하여 (Shin chan contra los Munecos de Shock Gahn)
      //   exec 67,175/280,896 cy/frame (76% idle) — CPU 75% of budget
      "BC2S",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000934,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* ADFE  슈퍼 닷지볼 어드밴스 (Super Dodge Ball Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 67,239/280,896 (76% idle) — CPU 75% of budget
    */

   {
      // 미키와 미니의 매지컬퀘스트2
      //   exec 67,254/280,896 cy/frame (76% idle) — CPU 75% of budget
      "A29J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8006a9e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* ADFJ  폭렬 돗지볼 파이터즈 (Bakunetsu Dodge Ball Fighters)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 67,415/280,896 (76% idle) — CPU 75% of budget
    */

   /* B4RJ  네모난 머리를 둥글게 어드밴스 - 국어 산수 이과 사회 (Shikakui Atama o Maruku Suru. Advance - Kokugo, Sansuu, Shakai, Rika)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 67,733/280,896 (76% idle) — CPU 75% of budget
    */

   /* ARHJ  열화의 불꽃
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 67,824/280,896 (76% idle) — CPU 75% of budget
    */

   /* BPPP  Pokemon Pinball - Ruby & Sapphire (E) (M5)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 67,968/280,896 (76% idle) — CPU 76% of budget
    */

   /* AF3J  제로 원 (Zero One)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 67,973/280,896 (76% idle) — CPU 76% of budget
    */

   /* B4KJ  네모난 머리를 둥글게 어드밴스 - 한자 계산 (Shikakui Atama o Maruku Suru. Advance - Kanji, Keisan)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 67,988/280,896 (76% idle) — CPU 76% of budget
    */

   {
      // 별의 커비 - 꿈의 샘 디럭스 (Kirby - Nightmare in Dream Land)
      //   exec 68,175/280,896 cy/frame (76% idle) — CPU 76% of budget
      "A7KE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000fae,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* ALFJ  드래곤볼 Z - 오공의 유산 II 인터내셔널 (Dragon Ball Z - The Legacy of Goku II International)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 68,286/280,896 (76% idle) — CPU 76% of budget
    */

   {
      // 핀볼 챌린지 디럭스 (Pinball Challenge Deluxe)
      //   exec 68,413/280,896 cy/frame (76% idle) — CPU 76% of budget
      "APLP",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80075a6,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BYYE  유유백서 - 영계 탐정 (Yu Yu Hakusho - Ghostfiles - Spirit Detective)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 68,540/280,896 (76% idle) — CPU 76% of budget
    */

   {
      // 캡틴 츠바사 - 영광의 기적 (Captain Tsubasa - Eikou no Kiseki)
      //   exec 69,325/280,896 cy/frame (75% idle) — CPU 77% of budget
      "AKYJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80042dc,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 슈퍼 동키콩2 (Super Donkey Kong 2)
      //   exec 69,569/280,896 cy/frame (75% idle) — CPU 77% of budget
      "B2DJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80003d4,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BMVJ  슈퍼마리오볼
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 69,584/280,896 (75% idle) — CPU 77% of budget
    */

   {
      // 동키콩 컨트리 2 (Donkey Kong Country 2)
      //   exec 69,587/280,896 cy/frame (75% idle) — CPU 77% of budget
      "B2DE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80003d4,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AM4E  모토GP (MotoGP)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 69,764/280,896 (75% idle) — CPU 78% of budget
    */

   /* BTAJ  아스트로보이 철완아톰
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 69,781/280,896 (75% idle) — CPU 78% of budget
    */

   /* AD9E  듀크 뉴켐 어드밴스 (Duke Nukem Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 70,082/280,896 (75% idle) — CPU 78% of budget
    */

   {
      // 스크류 브레이커
      //   exec 70,225/280,896 cy/frame (75% idle) — CPU 78% of budget
      "V49J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80006c2,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AOGJ  슈퍼로봇대전 OG (Super Robot Taisen - Original Generation) (5)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 70,434/280,896 (75% idle) — CPU 78% of budget
    */

   /* BPPJ  포켓몬스터 핀볼 - 루비 & 사파이어 (Pokemon Pinball - Ruby & Sapphire)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 70,513/280,896 (75% idle) — CPU 78% of budget
    */

   /* MB2G  파이널 판타지 크리스탈 크로니클즈 - 로더
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 71,162/280,896 (75% idle) — CPU 79% of budget
    */

   /* AAWE  혼두라 하드 스피릿츠
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 71,391/280,896 (75% idle) — CPU 79% of budget
    */

   {
      // 마리오 테니스 어드밴스 (Mario Tennis Advance)
      //   exec 71,646/280,896 cy/frame (74% idle) — CPU 80% of budget
      "BTMJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8013888,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 포켓몬스터 리프그린 (한글패치, 미국판 헤더)
      //   exec 71,770/280,896 cy/frame (74% idle) — CPU 80% of budget
      "BPGE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80008c6,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AR8E  로키 (Rocky)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 72,217/280,896 (74% idle) — CPU 80% of budget
    */

   {
      // 봄버맨 제터즈
      //   exec 72,267/280,896 cy/frame (74% idle) — CPU 80% of budget
      "AJZJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8002226,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 포켓몬스터 파이어레드 (한글패치, 미국판 헤더)
      //   exec 72,651/280,896 cy/frame (74% idle) — CPU 81% of budget
      "BPRE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80008c6,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BT8E  틴에이지 뮤턴트 닌자 터틀즈 더블 팩 (Teenage Mutant Ninja Turtles Double Pack)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 72,753/280,896 (74% idle) — CPU 81% of budget
    */

   /* BT8P  2-in-1 닌자 거북이 게임팩
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 72,753/280,896 (74% idle) — CPU 81% of budget
    */

   /* AEXJ  더 킹 오브 파이터즈 EX2 - 하울링 블러드 (The King of Fighters EX2 - Howling Blood)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 72,868/280,896 (74% idle) — CPU 81% of budget
    */

   /* ACZP  코믹스 존 (Comix Zone)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 72,930/280,896 (74% idle) — CPU 81% of budget
    */

   /* AKZJ  카마이타치의 밤 어드밴스 (Kamaitachi no Yoru Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 73,098/280,896 (74% idle) — CPU 81% of budget
    */

   {
      // 지쑤 F-ZERO 웨이라이 사이체 (Jisu F-Zero Weilai Saiche)
      //   exec 73,351/280,896 cy/frame (74% idle) — CPU 82% of budget
      "AFZC",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000c82,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AIFE  톰과 제리 - 인퍼널 이스케이프 (Tom and Jerry in Infurnal Escape)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 73,493/280,896 (74% idle) — CPU 82% of budget
    */

   /* BRWP  레이싱 피버 (Racing Fever)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 73,736/280,896 (74% idle) — CPU 82% of budget
    */

   /* AAWP  콘트라 어드밴스 - 더 에일리언 워즈 EX (Contra Advance - The Alien Wars EX)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 73,846/280,896 (74% idle) — CPU 82% of budget
    */

   {
      // F-제로 맥시멈 벨로시티 (F-Zero - Maximum Velocity)
      //   exec 74,001/280,896 cy/frame (74% idle) — CPU 82% of budget
      "AFZE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000c2e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BOBJ  보보보보 보보보 2 (Boboboubo Boubobo - Maji de!! Shinken Battle)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 74,123/280,896 (74% idle) — CPU 82% of budget
    */

   {
      // 마리오 vs. 동키콩 (Mario vs. Donkey Kong)
      //   exec 74,248/280,896 cy/frame (74% idle) — CPU 82% of budget
      "BM5J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80355b8,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* ACHJ  캐슬바니아 - 백야의 협주곡
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 74,439/280,896 (73% idle) — CPU 83% of budget
    */

   /* BIIJ  통근일필 (Tsuukin Hitofude)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 74,621/280,896 (73% idle) — CPU 83% of budget
    */

   /* A6OJ  귀무자 택틱스 (Onimusha Tactics)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 74,782/280,896 (73% idle) — CPU 83% of budget
    */

   /* BNTE  돌연변이 특공대 닌자거북이 (Teenage Mutant Ninja Turtles)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 75,413/280,896 (73% idle) — CPU 84% of budget
    */

   /* ANSJ  마리, 에리 &amp; 아니스의 아틀리에 - 산들 바람의 전언 (Marie, Elie &amp; Anis no Atelier - Soyokaze kara no Dengon)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 75,434/280,896 (73% idle) — CPU 84% of budget
    */

   /* BGKJ  게게게의 귀태랑 - 위기일발! 요괴열도 (Gegege no Kitarou - Kikiippatsu! Youkai Rettou)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 75,498/280,896 (73% idle) — CPU 84% of budget
    */

   /* BMVE  마리오 핀볼 랜드 (Mario Pinball Land)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 75,666/280,896 (73% idle) — CPU 84% of budget
    */

   /* BE8K  Fire Emblem - Seima no Kouseki (Korea-patch J-K v20210905 v0.5)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 75,707/280,896 (73% idle) — CPU 84% of budget
    */

   {
      // 포켓몬스터 에메랄드 (정식 한국판)
      //   exec 75,909/280,896 cy/frame (73% idle) — CPU 84% of budget
      "BPEK",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80008ce,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AEXE  킹 오브 파이터즈 EX2 하울링 블러드 (King of Fighters EX 2, The - Howling Blood)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 76,516/280,896 (73% idle) — CPU 85% of budget
    */

   {
      // Digimon - Battle Spirit 2 (Korea-patch J-K v20090901 v0.92)
      //   exec 76,765/280,896 cy/frame (73% idle) — CPU 85% of budget
      "BDSE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8010eb0,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AHUE  샤이닝소울
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 77,225/280,896 (73% idle) — CPU 86% of budget
    */

   /* A7AJ  나루토
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 77,295/280,896 (72% idle) — CPU 86% of budget
    */

   {
      // 대결! 울트라 히어로 (Taiketsu! Ultra Hero)
      //   exec 77,377/280,896 cy/frame (72% idle) — CPU 86% of budget
      "BU6J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x801da38,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BG2J  고에몽1,2 (Kessaku Sen! - Ganbare Goemon 1, 2 - Yuki Hime to Magginesu)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 77,415/280,896 (72% idle) — CPU 86% of budget
    */

   /* BMVP  슈퍼 마리오 볼 (Super Mario Ball)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 77,689/280,896 (72% idle) — CPU 86% of budget
    */

   /* BUOJ  모두의 소프트 시리즈 - 난프레 어드밴스 (Minna no Soft Series - Numpla Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 77,829/280,896 (72% idle) — CPU 86% of budget
    */

   /* ARVJ  레이브 - 빛과 그림자의 대결전 (Groove Adventure Rave - Hikari to Yami no Daikessen)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 77,950/280,896 (72% idle) — CPU 87% of budget
    */

   {
      // 리듬세상 (한글패치)
      //   exec 78,061/280,896 cy/frame (72% idle) — CPU 87% of budget
      "BRIJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80013d4,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AWVF  X-Men 2 - La Vengeance de Wolverine (F)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 78,274/280,896 (72% idle) — CPU 87% of budget
    */

   /* AWVE  엑스맨 2 - 울버린의 복수 (X2 - Wolverine's Revenge)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 78,277/280,896 (72% idle) — CPU 87% of budget
    */

   /* BMXJ  메트로이드 - 제로 미션 (Metroid Zero Mission)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 78,324/280,896 (72% idle) — CPU 87% of budget
    */

   {
      // 스타워즈 - 디 뉴 드로이드 아미 (Star Wars - The New Droid Army)
      //   exec 78,358/280,896 cy/frame (72% idle) — CPU 87% of budget
      "A2WE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x801601e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AN5J  강의 낚시5 (Kawa no Nushi Tsuri 5 - Fushigi no Mori kara)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 78,684/280,896 (72% idle) — CPU 87% of budget
    */

   /* AODJ  Minami no Umi no Odyssey (Korea-patch J-K ver.Proto)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 78,856/280,896 (72% idle) — CPU 88% of budget
    */

   /* A3VJ  소닉 핀볼파티
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 78,939/280,896 (72% idle) — CPU 88% of budget
    */

   /* ALGE  드래곤볼 Z - 손오공의 유산 (Dragon Ball Z - The Legacy of Goku)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 79,223/280,896 (72% idle) — CPU 88% of budget
    */

   {
      // Rhythm Tengoku (Korea-patch J-K v20200417 v1.32)
      //   exec 79,335/280,896 cy/frame (72% idle) — CPU 88% of budget
      "BRIK",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8001964,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* A9LJ  테니스의 왕자 2003 - 쿨 블루 (Tennis no Ouji-sama 2003 - Cool Blue)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 79,614/280,896 (72% idle) — CPU 88% of budget
    */

   {
      // 드래곤볼 Z - 무공투극 (Dragon Ball Z - Taiketsu)
      //   exec 79,640/280,896 cy/frame (72% idle) — CPU 88% of budget
      "BDBE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x814cf8e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BGMJ  환상마전 최유기 (Gensou Maden Saiyuuki - Hangyaku no Toushin-taishi)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 79,928/280,896 (72% idle) — CPU 89% of budget
    */

   /* AN7J  패미스타 어드밴스 (Famista Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 80,200/280,896 (71% idle) — CPU 89% of budget
    */

   /* A3UJ  마더 3 (Mother 3)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 80,290/280,896 (71% idle) — CPU 89% of budget
    */

   {
      // 파이널 파이트 원 (Final Fight One)
      //   exec 80,693/280,896 cy/frame (71% idle) — CPU 90% of budget
      "AFFJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8005e08,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AG4J  고지라 괴수대단투 어드밴스 (Gojira - Kaijuu Dairantou Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 80,771/280,896 (71% idle) — CPU 90% of budget
    */

   /* A2OJ  K-1 포켓 그랑프리2 (K-1 Pocket Grand Prix 2)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 80,809/280,896 (71% idle) — CPU 90% of budget
    */

   /* AAWJ  콘트라 하드 스피리츠 (Contra Hard Spirits)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 80,902/280,896 (71% idle) — CPU 90% of budget
    */

   {
      // 조이드 사가 2 (Zoids Saga II)
      //   exec 80,974/280,896 cy/frame (71% idle) — CPU 90% of budget
      "AZ2J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8060834,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* B8PJ  Power Pro Kun Pocket 1, 2 (Korea-patch J-K v20150802 v0.4.4beta)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 81,041/280,896 (71% idle) — CPU 90% of budget
    */

   /* BO2J  오차이누의 모험섬 (Ochaken no Bouken-jima - Honwaka Yume no Island)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 81,421/280,896 (71% idle) — CPU 90% of budget
    */

   /* ALNE  루나 레전드 (Lunar Legend)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 81,621/280,896 (71% idle) — CPU 91% of budget
    */

   /* AU2J  샤이닝 소울 2 (Shining Soul II)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 82,008/280,896 (71% idle) — CPU 91% of budget
    */

   {
      // 짱구는 못말려 - 폭풍을 부르는 시네마랜드의 대모험 (Crayon Shin-chan - Arashi o Yobu Cinemaland no Daibouken!)
      //   exec 82,102/280,896 cy/frame (71% idle) — CPU 91% of budget
      "BKCJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80006b8,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* FSME  슈퍼 마리오 브라더스 클래식 (Classic NES Series - Super Mario Bros.)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 82,365/280,896 (71% idle) — CPU 92% of budget
    */

   /* BBSJ  보우캬쿠노 센리츠 (Boukyaku no Senritsu)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 82,534/280,896 (71% idle) — CPU 92% of budget
    */

   /* ADEJ  도쿄 디즈니 씨 모험 (Adventure of Tokyo Disney Sea)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 82,737/280,896 (71% idle) — CPU 92% of budget
    */

   /* AE7J  파이어 엠블렘 - 열화의 검 (Fire Emblem - Rekka no Ken)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 82,919/280,896 (70% idle) — CPU 92% of budget
    */

   {
      // 그레이티스트 나인 (Greatest Nine)
      //   exec 83,073/280,896 cy/frame (70% idle) — CPU 92% of budget
      "AG9J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8064694,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BFTJ  에프제로 클라이맥스 (F-Zero - Climax)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 83,202/280,896 (70% idle) — CPU 92% of budget
    */

   /* BKSJ  카드캡터 체리 - 사쿠라 카드 프렌즈 (Cardcaptor Sakura - Sakura Card Hen - Sakura to Card to Otomodachi)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 83,248/280,896 (70% idle) — CPU 92% of budget
    */

   /* B3IJ  미라클 팬더 - 7개별의 우주해적 (Mirakuru! Panzou - 7-tsu no Hoshi no Uchuu Kaizoku)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 83,376/280,896 (70% idle) — CPU 93% of budget
    */

   /* AR7J  어드밴스랠리 (Advance Rally)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 83,425/280,896 (70% idle) — CPU 93% of budget
    */

   {
      // 록맨 제로 1 (Megaman Zero 1)
      //   exec 83,684/280,896 cy/frame (70% idle) — CPU 93% of budget
      "ARZJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80004f6,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AZAJ  아즈망가대왕 어드밴스
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 83,786/280,896 (70% idle) — CPU 93% of budget
    */

   /* BG3E  드래곤볼 Z - 부우의 분노 (Dragon Ball Z - Buu's Fury)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 84,145/280,896 (70% idle) — CPU 93% of budget
    */

   /* BRAE  레이싱 기어즈 어드밴스 (Racing Gears Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 84,612/280,896 (70% idle) — CPU 94% of budget
    */

   /* A8RJ  Tennis no Ouji-sama 2003 - Passion Red (Korea-patch J-K v20071031 v.Beta)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 84,859/280,896 (70% idle) — CPU 94% of budget
    */

   /* AKVJ  K-1 포켓 그랑프리 (K-1 Pocket Grand Prix)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 85,005/280,896 (70% idle) — CPU 94% of budget
    */

   {
      // 쥬라기공원III - 잃어버린 유전자
      //   exec 85,016/280,896 cy/frame (70% idle) — CPU 94% of budget
      "ADNE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000470,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BT4E  드래곤볼 GT - 트랜스포메이션 (Dragon Ball GT - Transformation)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 85,133/280,896 (70% idle) — CPU 95% of budget
    */

   /* A8TJ  RPG 츠쿠르 어드밴스 (RPG Tsukuru Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 85,562/280,896 (70% idle) — CPU 95% of budget
    */

   {
      // 마리오 vs. 동키콩 (Mario vs. Donkey Kong)
      //   exec 85,587/280,896 cy/frame (70% idle) — CPU 95% of budget
      "BM5E",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8033eec,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* B2RJ  슈퍼로봇대전 OG2 (Super Robot Taisen - Original Generation 2)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 85,687/280,896 (69% idle) — CPU 95% of budget
    */

   {
      // 다이나믹 전설 호성전 붕괴의 론도 (Legend of Dynamic - Goushouden - Houkai no Rondo)
      //   exec 86,052/280,896 cy/frame (69% idle) — CPU 96% of budget
      "AVDJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x800097e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 크레용신짱 - 전설을 부르는 부록의 고향 쇼크건
      //   exec 86,072/280,896 cy/frame (69% idle) — CPU 96% of budget
      "BC2J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000934,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AJ6J  알라딘
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 86,382/280,896 (69% idle) — CPU 96% of budget
    */

   /* BK6J  갑충왕자 무시킹 (Kouchuu Ouja Mushiking - Greatest Champion e no Michi)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 86,942/280,896 (69% idle) — CPU 97% of budget
    */

   /* BP7J  파워프로군포켓7 (Power Pro Kun Pocket 7)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 87,460/280,896 (69% idle) — CPU 97% of budget
    */

   /* SBFP  부타노파이터 (Butano Fighter)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 87,737/280,896 (69% idle) — CPU 97% of budget
    */

   /* BULP  얼티메이트 스파이더맨
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 87,759/280,896 (69% idle) — CPU 98% of budget
    */

   /* ASOJ  소닉 어드밴스 1 (Sonic Advance)
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 87,917/280,896 (69% idle) — CPU 98% of budget
    */

   {
      // 미키와 도날드의 매지컬 퀘스트3
      //   exec 87,977/280,896 cy/frame (69% idle) — CPU 98% of budget
      "BM3J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80028fc,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 우리들의 태양2 - 속 우리들의 태양
      //   exec 88,118/280,896 cy/frame (69% idle) — CPU 98% of budget
      "U32J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8229e94,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* ASXJ  삼국지0.75
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 88,824/280,896 (68% idle) — CPU 99% of budget
    */

   /* BD3J  드래곤 퀘스트 캐릭터즈 - 토네코의 대모험 3 어드밴스
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 89,236/280,896 (68% idle) — CPU 99% of budget
    */

   {
      // 쟈쟈마루 쥬니어 전승기
      //   exec 89,634/280,896 cy/frame (68% idle) — CPU 100% of budget
      "BNJJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x803622c,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BC9E  스파이더맨
    * No busy-wait loop — it waits via the BIOS (SWI IntrWait/Halt), which gpSP
    * already fast-forwards (cpu.cc:1499). No entry needed; not slow.
    * exec 89,671/280,896 (68% idle) — CPU 100% of budget
    */

   {
      // 슈퍼마리오USA
      //   exec 89,857/280,896 cy/frame (68% idle) — CPU 100% of budget
      "AMZE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8001cfc,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 판타직 칠드런
      //   exec 89,912/280,896 cy/frame (68% idle) — CPU 100% of budget
      "BFCJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80006b4,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 황금의 태양 2 - 잃어버린 시대 (Ougon no Taiyou - Ushinawareshi Toki)
      //   exec 90,148/280,896 cy/frame (68% idle) — CPU 100% of budget
      "AGFJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8013542,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BULE  얼티밋 스파이더맨 (Ultimate Spider-Man)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 90,283/280,896 (68% idle) — CPU 100% of budget
    */

   /* BLWE  LEGO Star Wars - The Video Game (UE) (M7)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 90,766/280,896 (68% idle) — CPU 101% of budget
    */

   {
      // V랠리3 (V-Rally 3)
      //   exec 90,801/280,896 cy/frame (68% idle) — CPU 101% of budget
      "AVRJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80abc64,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AABJ  슈퍼블랙배스 (Super Black Bass Advance)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 91,625/280,896 (67% idle) — CPU 102% of budget
    */

   /* BKKJ  모두의 사육 시리즈3 - 나의 장수풍뎅이 사슴벌레
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 92,241/280,896 (67% idle) — CPU 102% of budget
    */

   {
      // 메탈슬러그 어드밴스 (Metal Slug Advance)
      //   exec 92,782/280,896 cy/frame (67% idle) — CPU 103% of budget
      "BSME",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000298,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* A2HJ  시작의 일보 - 더 파이팅 (Hajime no Ippo - The Fighting!)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 92,811/280,896 (67% idle) — CPU 103% of budget
    */

   /* APXJ  파랑스 - The Enforce Fighter A-144
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 92,813/280,896 (67% idle) — CPU 103% of budget
    */

   /* APXE  팔랑크스 - 인포스 파이터 A-144 (Phalanx)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 93,112/280,896 (67% idle) — CPU 103% of budget
    */

   {
      // 얼티밋 브레인 게임즈 (Ultimate Brain Games)
      //   exec 93,471/280,896 cy/frame (67% idle) — CPU 104% of budget
      "ABUE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8004cbe,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* B72J  허드슨 베스트 콜렉션 Vol.2 (Hudson Best Collection Vol. 2 - Lode Runner Collection)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 94,336/280,896 (66% idle) — CPU 105% of budget
    */

   /* AVSJ  신약 성검전설 (Shinyaku Seiken Densetsu)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 94,542/280,896 (66% idle) — CPU 105% of budget
    */

   /* BANE  반 헬싱 (Van Helsing)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 94,613/280,896 (66% idle) — CPU 105% of budget
    */

   /* A2NP  소닉 어드밴스 2 (Sonic Advance 2)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 94,828/280,896 (66% idle) — CPU 105% of budget
    */

   /* A5PJ  Power Pro Kun Pocket 5 (Korea-patch J-K ver.Proto)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 94,981/280,896 (66% idle) — CPU 106% of budget
    */

   /* AJCE  성룡의 모험 다크 핸드의 전설 (Jackie Chan Adventures - Legend of the Dark Hand)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 96,227/280,896 (66% idle) — CPU 107% of budget
    */

   /* AJCF  재키 찬의 모험 (Aventures de Jackie Chan, Les - La Legende de la Main Noire)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 96,278/280,896 (66% idle) — CPU 107% of budget
    */

   /* AF8E  F1 2002 (F1 2002)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 96,828/280,896 (66% idle) — CPU 108% of budget
    */

   {
      // 블랙 매트리스 제로
      //   exec 97,778/280,896 cy/frame (65% idle) — CPU 109% of budget
      "AXBJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000372,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BVEJ  비트 제너레이션즈 오비탈 (bit Generations - Orbital)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 98,159/280,896 (65% idle) — CPU 109% of budget
    */

   /* ANYJ  가친코 프로야구 (Gachinko Pro Yakyuu)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 98,414/280,896 (65% idle) — CPU 109% of budget
    */

   /* BK3J  카드캡터사쿠라 - 사쿠라카드로 미니게임 (Cardcaptor Sakura - Sakura Card de Mini Game)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 99,022/280,896 (65% idle) — CPU 110% of budget
    */

   /* AYCE  판타지 스타 컬렉션 (Phantasy Star Collection)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 99,215/280,896 (65% idle) — CPU 110% of budget
    */

   /* BMZP  주키퍼
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 99,277/280,896 (65% idle) — CPU 110% of budget
    */

   {
      // 페르시아의 왕자 - 시간의 모래
      //   exec 99,351/280,896 cy/frame (65% idle) — CPU 110% of budget
      "BPYP",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80900f2,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AJ9J  슈퍼로봇대전 OG (Super Robot Taisen - Original Generation) (2)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 99,448/280,896 (65% idle) — CPU 110% of budget
    */

   /* BR9J  리락쿠마한 매일 (Relaxuma na Mainichi)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 99,739/280,896 (64% idle) — CPU 111% of budget
    */

   /* AIOE  아이언맨 (Invincible Iron Man, The)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 99,755/280,896 (64% idle) — CPU 111% of budget
    */

   /* AGNJ  고에몽 - 뉴에이지출동! (Goemon - New Age Shutsudou!)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 99,758/280,896 (64% idle) — CPU 111% of budget
    */

   /* BI3E  스파이더맨 3 (Spider-Man 3)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 99,833/280,896 (64% idle) — CPU 111% of budget
    */

   /* AG4E  고질라 도미네이션 (Godzilla - Domination!)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 99,845/280,896 (64% idle) — CPU 111% of budget
    */

   /* B3SJ  소닉 어드밴스 3 (Sonic Advance 3)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 100,219/280,896 (64% idle) — CPU 111% of budget
    */

   /* BLWJ  레고 스타 워즈 더 비디오 게임 (LEGO Star Wars - The Video Game)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 100,444/280,896 (64% idle) — CPU 112% of budget
    */

   /* ATTP  타이니툰 어드밴쳐 - Buster's Bad Dream
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 100,609/280,896 (64% idle) — CPU 112% of budget
    */

   /* ALEE  브루스 리 - 전설의 귀환 (Bruce Lee - Return of the Legend)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 100,995/280,896 (64% idle) — CPU 112% of budget
    */

   /* BE4J  아이실드 21 - 데빌배츠 데빌데이즈 (Eyeshield 21 - DevilBats DevilDays)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 101,322/280,896 (64% idle) — CPU 113% of budget
    */

   /* B4ME  마블 얼티밋 얼라이언스 (Marvel - Ultimate Alliance)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 101,903/280,896 (64% idle) — CPU 113% of budget
    */

   /* A2CJ  캐슬바니아 - 효월의 원무곡
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 101,945/280,896 (64% idle) — CPU 113% of budget
    */

   /* 2G0P  굿보이 갤럭시 데모
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 101,959/280,896 (64% idle) — CPU 113% of budget
    */

   /* A9KJ  슬라임 모리모리 드래곤 퀘스트 - 충격의 꼬리단 (Slime Morimori Dragon Quest - Shougeki no Shippo Dan)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 102,077/280,896 (64% idle) — CPU 113% of budget
    */

   /* BZMJ  젤다의 전설 - 이상한 모자0.3(종료방지)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 102,196/280,896 (64% idle) — CPU 114% of budget
    */

   /* BONE  원피스 소년점프 (One Piece)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 103,046/280,896 (63% idle) — CPU 114% of budget
    */

   {
      // 디즈니 스포츠 - 스노보딩 (Disney Sports - Snowboarding)
      //   exec 103,765/280,896 cy/frame (63% idle) — CPU 115% of budget
      "A5DE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000434,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AC8E  크래쉬밴디쿳 어드밴스2
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 104,532/280,896 (63% idle) — CPU 116% of budget
    */

   /* BLEJ  블리치 어드밴스
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 104,773/280,896 (63% idle) — CPU 116% of budget
    */

   /* AAPJ  메탈건 슬링거
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 104,777/280,896 (63% idle) — CPU 116% of budget
    */

   /* AZLJ  젤다의 전설 신들의 트라이포스 & 포 소드 (Zelda no Densetsu - Kamigami no Triforce & 4tsu no Tsurugi)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 104,861/280,896 (63% idle) — CPU 117% of budget
    */

   /* ARNJ  머나먼 시공속에서 (Neoromance Game - Harukanaru Toki no Naka de)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 106,036/280,896 (62% idle) — CPU 118% of budget
    */

   {
      // 록맨 에그제
      //   exec 106,237/280,896 cy/frame (62% idle) — CPU 118% of budget
      "AREJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000338,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BYUJ  유그드라 유니온 (Yggdra Union)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 106,431/280,896 (62% idle) — CPU 118% of budget
    */

   /* AZLE  Legend of Zelda, The - A Link To The Past Four Swords (U) [!]
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 106,491/280,896 (62% idle) — CPU 118% of budget
    */

   {
      // Yu-Gi-Oh! Duel Monsters Expert 2006 (Korea-patch J-K v20110731 v0.93)
      //   exec 106,537/280,896 cy/frame (62% idle) — CPU 118% of budget
      "BY6J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80f4c4e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 유희왕! 듀얼 몬스터즈 익스퍼트 3 (Yu-Gi-Oh! Duel Monsters Expert 3)
      //   exec 106,583/280,896 cy/frame (62% idle) — CPU 118% of budget
      "BY3J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80831da,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AJ4E  어스웜짐2
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 106,854/280,896 (62% idle) — CPU 119% of budget
    */

   {
      // 주큐브 (ZooCube)
      //   exec 106,976/280,896 cy/frame (62% idle) — CPU 119% of budget
      "ANCJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8007ee8,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BDAJ  꽃놀이 퍼즐 어드밴스 (Don-chan Puzzle - Hanabi de Doon! Advance)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 108,163/280,896 (61% idle) — CPU 120% of budget
    */

   /* AN9J  테일즈 오브 월드 - 나리키리던젼2
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 108,554/280,896 (61% idle) — CPU 121% of budget
    */

   /* FM2J  패미콤 미니 - Vol. 21 - 슈퍼 마리오 브라더스 2 (Famicom Mini 21 - Super Mario Bros. 2)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 108,655/280,896 (61% idle) — CPU 121% of budget
    */

   /* AVPP  V.I.P. (V.I.P.)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 108,704/280,896 (61% idle) — CPU 121% of budget
    */

   /* BDVK  드래곤볼 어드밴스 어드밴쳐 (Dragon Ball - Advance Adventure)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 108,803/280,896 (61% idle) — CPU 121% of budget
    */

   {
      // 파이널 판타지 택틱스 어드밴스 (한글패치)
      //   exec 109,273/280,896 cy/frame (61% idle) — CPU 121% of budget
      "AFXJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000428,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AXRE  슈퍼 스트리트 파이터 2X 리바이벌 (Super Street Fighter II Turbo - Revival)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 109,336/280,896 (61% idle) — CPU 121% of budget
    */

   /* AHWJ  핫휠 어드밴스 (Hot Wheels Advance)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 110,098/280,896 (61% idle) — CPU 122% of budget
    */

   {
      // 크레이지 레이서즈 (Konami Krazy Racers)
      //   exec 110,630/280,896 cy/frame (61% idle) — CPU 123% of budget
      "AKWE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000422,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BUHJ  우에키의 법칙 - 신기작렬! 능력자 배틀 (Ueki no Housoku - Jingi Sakuretsu! Nouryokusha Battle)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 111,197/280,896 (60% idle) — CPU 124% of budget
    */

   {
      // 코나미 와이와이 레이싱 (Konami Wai Wai Racing Advance)
      //   exec 112,635/280,896 cy/frame (60% idle) — CPU 125% of budget
      "AKWJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000422,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BGEE  SD건담포스 (SD Gundam Force)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 112,853/280,896 (60% idle) — CPU 125% of budget
    */

   /* BGJJ  환성신 저스티라이더 - 지구의 전사들 (Genseishin Justirisers - Souchaku! Hoshi no Senshi-tachi)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 113,628/280,896 (60% idle) — CPU 126% of budget
    */

   /* BREJ  리비에라 - 약속의 땅 리비에라
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 114,145/280,896 (59% idle) — CPU 127% of budget
    */

   /* AMKE  마리오 카트 어드밴스 (Mario Kart - Super Circuit)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 114,147/280,896 (59% idle) — CPU 127% of budget
    */

   {
      // 건스타 슈퍼 히어로즈 (Gunstar Super Heroes)
      //   exec 114,608/280,896 cy/frame (59% idle) — CPU 127% of budget
      "BGXJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000852,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 유희왕! - 듀얼 몬스터즈 인터네셔널2
      //   exec 115,052/280,896 cy/frame (59% idle) — CPU 128% of budget
      "BYIJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8118882,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* ACQE  크래쉬밴디쿳 어드밴스
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 115,134/280,896 (59% idle) — CPU 128% of budget
    */

   /* AHQJ  하로봇츠 로보히어로 배틀링 (Harobots - Robo Hero Battling!!)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 115,740/280,896 (59% idle) — CPU 129% of budget
    */

   /* AVEE  얼티밋 비치 사커 (Ultimate Beach Soccer)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 115,999/280,896 (59% idle) — CPU 129% of budget
    */

   /* AVEP  프로 비치 사커 (Pro Beach Soccer)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 117,238/280,896 (58% idle) — CPU 130% of budget
    */

   {
      // 강철의 연금술사 - 추억의 주명곡 (Hagane no Renkinjutsushi - Omoide no Sonata)
      //   exec 119,100/280,896 cy/frame (58% idle) — CPU 132% of budget
      "BH2J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x801d84c,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 검은수염의 골프합시다 (Kurohige no Golf Shiyouyo)
      //   exec 120,415/280,896 cy/frame (57% idle) — CPU 134% of budget
      "AGOJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x802a7da,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BM8J  인어멜로디 - 피치피치피치 - 피치피치파티 (Mermaid Melody - Pichi Pichi Pitch - Pichi Pichi Party)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 120,601/280,896 (57% idle) — CPU 134% of budget
    */

   /* AXHJ  단도시 (Dan Doh!! Xi)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 121,017/280,896 (57% idle) — CPU 134% of budget
    */

   /* BHAJ  꽃놀이 어드밴스 (Hanabi Hyakkei Advance)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 121,361/280,896 (57% idle) — CPU 135% of budget
    */

   {
      // 디즈니 스포츠 - 풋볼 (Disney Sports - Football)
      //   exec 121,504/280,896 cy/frame (57% idle) — CPU 135% of budget
      "A6DP",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000424,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* A2GJ  어드밴스 GT 2
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 121,644/280,896 (57% idle) — CPU 135% of budget
    */

   {
      // 디즈니 스포츠 - 축구 (Disney Sports - Soccer)
      //   exec 122,019/280,896 cy/frame (57% idle) — CPU 136% of budget
      "A6DE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000424,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* FSMJ  패미콤 미니 - Vol. 01 - 슈퍼 마리오 브라더스 (Famicom Mini 01 - Super Mario Bros.)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 122,514/280,896 (56% idle) — CPU 136% of budget
    */

   {
      // 캐슬바니아 - 서클 오브 더 문 (한글패치)
      //   exec 122,757/280,896 cy/frame (56% idle) — CPU 136% of budget
      "AAMJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80003ce,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AZUJ  스트리트 파이터 제로3 어퍼 (Street Fighter Zero 3 Upper)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 123,194/280,896 (56% idle) — CPU 137% of budget
    */

   /* AAUJ  진 여신전생
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 123,457/280,896 (56% idle) — CPU 137% of budget
    */

   /* B3QJ  삼국지 공명전 (Sangokushi - Koumeiden)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 123,467/280,896 (56% idle) — CPU 137% of budget
    */

   /* AFEK  파이어 엠블렘 - 봉인의 검 (Fire Emblem Sealed Sword)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 123,869/280,896 (56% idle) — CPU 138% of budget
    */

   /* A5BJ  초코보 랜드 - 게임데 다이스
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 124,500/280,896 (56% idle) — CPU 138% of budget
    */

   /* AZUE  스트리트 파이터 알파 3 (Street Fighter Alpha 3)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 124,508/280,896 (56% idle) — CPU 138% of budget
    */

   /* A88J  마리오와 루이지RPG
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 124,915/280,896 (56% idle) — CPU 139% of budget
    */

   {
      // 철권 어드밴스
      //   exec 126,045/280,896 cy/frame (55% idle) — CPU 140% of budget
      "ATKJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x800074a,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BSXE  SSX 3
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 126,579/280,896 (55% idle) — CPU 141% of budget
    */

   /* AGTJ  전일본GT선수권 (Zen-Nihon GT Senshuken)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 127,148/280,896 (55% idle) — CPU 141% of budget
    */

   /* BT3J  탐정 진구지 사부로 - 하얀 그림자의 소녀 (Tantei Jinguuji Saburou - Shiroi Kage no Shoujo)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 128,200/280,896 (54% idle) — CPU 142% of budget
    */

   {
      // 슈퍼로봇대전 OG (Super Robot Taisen - Original Generation)
      //   exec 128,676/280,896 cy/frame (54% idle) — CPU 143% of budget
      "ASRJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80003ec,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BAPE  디즈니 아메리칸 드래곤 제이크 롱 - 라이즈 오브 더 헌츠클랜! (American Dragon - Jake Long - Rise of the Huntsclan)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 128,680/280,896 (54% idle) — CPU 143% of budget
    */

   /* AIPE  Silent Scope (U)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 129,370/280,896 (54% idle) — CPU 144% of budget
    */

   /* BR3E  알타입 III (R-Type III - The Third Lightning)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 129,801/280,896 (54% idle) — CPU 144% of budget
    */

   {
      // 메탈맥스 2 카이 (Metal Max 2 Kai)
      //   exec 130,041/280,896 cy/frame (54% idle) — CPU 144% of budget
      "A9TJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80671e0,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AK7J  바람의 크로노아 히어로즈 - 전설의 스타메달
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 130,248/280,896 (54% idle) — CPU 145% of budget
    */

   /* AFUJ  요괴도 (Youkaidou)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 131,130/280,896 (53% idle) — CPU 146% of budget
    */

   /* BE8J  파이어 엠블렘 - 성마의 광석 (Fire Emblem The Sacred Stones)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 131,508/280,896 (53% idle) — CPU 146% of budget
    */

   /* BFFJ  파이널판타지I&II어드밴스0.5
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 131,812/280,896 (53% idle) — CPU 146% of budget
    */

   {
      // 에그 매니아 (Egg Mania - Tsukande! Mawashite! Dossun Puzzle!!)
      //   exec 131,969/280,896 cy/frame (53% idle) — CPU 147% of budget
      "AEMJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8002df2,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 에고 매니아 (Eggomania)
      //   exec 132,729/280,896 cy/frame (53% idle) — CPU 147% of budget
      "AEMP",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80031b6,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 메탈슬러그 어드밴스 (Metal Slug Advance) (2)
      //   exec 133,714/280,896 cy/frame (52% idle) — CPU 149% of budget
      "BSMJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000298,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BN2J  나루토 - 최강닌자 대결집!2
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 134,027/280,896 (52% idle) — CPU 149% of budget
    */

   {
      // 인어공주 멜로디 피치피치피치 피치피칫 라이브 스타트 (Mermaid Melody - Pichi Pichi Pitch - Pichi Pichitto Live Start!)
      //   exec 135,133/280,896 cy/frame (52% idle) — CPU 150% of budget
      "B3MJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000a20,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AK2J  근육맨2세 - 정의초인으로의 길 (Kinnikuman II-Sei - Seigi Choujin e no Michi)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 135,258/280,896 (52% idle) — CPU 150% of budget
    */

   /* BUVJ  우주의 스텔비아 (Uchuu no Stellvia)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 135,923/280,896 (52% idle) — CPU 151% of budget
    */

   /* B8KJ  별의 카비 - 거울속의 대미궁
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 136,315/280,896 (51% idle) — CPU 151% of budget
    */

   /* A2NJ  Sonic Advance 2 (Korea-patch J-K v20201008 v0.2)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 136,352/280,896 (51% idle) — CPU 152% of budget
    */

   /* B8KE  별의 커비 - 거울의 대미궁 (Kirby &amp; The Amazing Mirror)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 136,386/280,896 (51% idle) — CPU 152% of budget
    */

   {
      // 철권 어드밴스 (Tekken Advance)
      //   exec 136,502/280,896 cy/frame (51% idle) — CPU 152% of budget
      "ATKE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x800074a,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 슈퍼마리오월드 (한글패치)
      //   exec 137,516/280,896 cy/frame (51% idle) — CPU 153% of budget
      "AA2C",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80005ec,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AK2E  얼티밋 머슬 - 영웅의 길 (Ultimate Muscle - The Kinnikuman Legacy - The Path of the Superhero)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 138,188/280,896 (51% idle) — CPU 154% of budget
    */

   {
      // 록맨 제로 3 (한글패치)
      //   exec 138,788/280,896 cy/frame (51% idle) — CPU 154% of budget
      "BZ3J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80019c4,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 슈퍼마리오 브라더스3 (Super Mario Advance 4 - Super Mario 3 + Mario Brothers)
      //   exec 139,692/280,896 cy/frame (50% idle) — CPU 155% of budget
      "AX4J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000732,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* BGAJ  SD 건담 G 제네레이션 어드밴스 (SD Gundam G Generation Advance)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 140,092/280,896 (50% idle) — CPU 156% of budget
    */

   {
      // 록맨 제로 2 (Megaman Zero 2)
      //   exec 140,290/280,896 cy/frame (50% idle) — CPU 156% of budget
      "A62J",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x800066c,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 메이드 인 와리오 (한글패치)
      //   exec 140,911/280,896 cy/frame (50% idle) — CPU 157% of budget
      "AZWJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8000f5e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AVFJ  전설의 스타피2
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 141,888/280,896 (49% idle) — CPU 158% of budget
    */

   /* BGNE  기동전사 건담 시드 배틀 어썰트 (Mobile Suit Gundam SEED - Battle Assault)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 142,231/280,896 (49% idle) — CPU 158% of budget
    */

   /* B3DJ  전설의 스타피3
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 144,586/280,896 (49% idle) — CPU 161% of budget
    */

   /* AG7J  어드밴스 GTA (Advance GTA)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 145,220/280,896 (48% idle) — CPU 161% of budget
    */

   /* AOEE  레고 드롬 레이서즈 (Drome Racers)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 145,290/280,896 (48% idle) — CPU 161% of budget
    */

   /* AIPJ  사일런트 스코프 (Silent Scope)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 145,354/280,896 (48% idle) — CPU 162% of budget
    */

   {
      // 슈퍼 버블 팝 (Super Bubble Pop)
      //   exec 148,559/280,896 cy/frame (47% idle) — CPU 165% of budget
      "AVZE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8013cb4,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 슈퍼 퍼즐파이터II Turbo터보
      //   exec 148,774/280,896 cy/frame (47% idle) — CPU 165% of budget
      "AZ8E",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8002b5e,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* B8CJ  킹덤 하츠 - 체인 오브 메모리즈 (Kingdom Hearts Chain of Memories)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 152,174/280,896 (46% idle) — CPU 169% of budget
    */

   /* B3EJ  삼국지 영걸전 (Sangokushi - Eiketsuden)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 153,069/280,896 (46% idle) — CPU 170% of budget
    */

   /* APWE  파워레인저 - 와일드포스 (Power Rangers - Wild Force)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 154,376/280,896 (45% idle) — CPU 172% of budget
    */

   /* SV3D  바룸3d레이싱 (Varooom 3D)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 156,150/280,896 (44% idle) — CPU 174% of budget
    */

   /* B36J  진삼국무쌍 어드밴스 (Shin Sangoku Musou Advance)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 156,407/280,896 (44% idle) — CPU 174% of budget
    */

   /* BJHE  저스티스 리그 히어로즈 플래시 (Justice League Heroes - The Flash)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 156,444/280,896 (44% idle) — CPU 174% of budget
    */

   /* AORJ  오리엔탈 블루 - 푸른천외 (Oriental Blue - Ao no Tengai)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 157,304/280,896 (44% idle) — CPU 175% of budget
    */

   {
      // 슈퍼 차이니즈 1+2 어드밴스 (Super Chinese 1, 2 Advance)
      //   exec 163,242/280,896 cy/frame (42% idle) — CPU 181% of budget
      "BSAJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8003540,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* B6JJ  Super Robot Taisen J (Korea-patch J-K ver.Proto)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 163,699/280,896 (42% idle) — CPU 182% of budget
    */

   {
      // 인어공주 멜로디 피치피치피치 (Mermaid Melody - Pichi Pichi Pitch)
      //   exec 164,366/280,896 cy/frame (41% idle) — CPU 183% of budget
      "BMAJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80007fc,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* A6SJ  슈퍼로봇대전 OG (Super Robot Taisen - Original Generation) (4)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 170,321/280,896 (39% idle) — CPU 189% of budget
    */

   {
      // 슈퍼마리오 요시아일랜드 (Super Mario Advance 3 - Yoshi's Island + Mario Brothers)
      //   exec 173,660/280,896 cy/frame (38% idle) — CPU 193% of budget
      "A3AJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8002ba4,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AS8E  스타X
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 173,816/280,896 (38% idle) — CPU 193% of budget
    */

   /* AXRJ  슈퍼 스트리트파이터IIX - 리바이벌
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 177,097/280,896 (37% idle) — CPU 197% of budget
    */

   {
      // 동키콩 컨트리 3 (Donkey Kong Country 3)
      //   exec 178,575/280,896 cy/frame (36% idle) — CPU 198% of budget
      "BDQE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80003a8,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   {
      // 슈퍼 동키콩3 (Super Donkey Kong 3)
      //   exec 178,881/280,896 cy/frame (36% idle) — CPU 199% of budget
      "BDQJ",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x80003a8,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* B42J  건담시드 데스티니 (Kidou Senshi Gundam SEED Destiny)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 180,897/280,896 (36% idle) — CPU 201% of budget
    */

   /* ASTJ  전설의 스타피 (Densetsu no Stafy)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 189,222/280,896 (33% idle) — CPU 210% of budget
    */

   {
      // 얼티밋 윈터 게임즈 (Ultimate Winter Games)
      //   exec 203,757/280,896 cy/frame (27% idle) — CPU 226% of budget
      "BUWE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8003afc,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AO7K  원피스 - 일곱섬의 대보물 (One Piece - Ilgop Seomui Debomool)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 215,105/280,896 (23% idle) — CPU 239% of budget
    */

   /* AVCE  콜벳 50주년
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 216,091/280,896 (23% idle) — CPU 240% of budget
    */

   /* FDKE  클래식 NES 시리즈 - 동키콩 (Classic NES Series - Donkey Kong)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 227,722/280,896 (19% idle) — CPU 253% of budget
    */

   /* FDKJ  패미콤 미니 - Vol. 02 - 동키콩 (Famicom Mini 02 - Donkey Kong)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 227,736/280,896 (19% idle) — CPU 253% of budget
    */

   /* FMBJ  패미콤 미니 - Vol. 11 - 마리오 브라더스 (Famicom Mini 11 - Mario Bros.)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 241,609/280,896 (14% idle) — CPU 268% of budget
    */

   /* ALIE  디즈니 헌티드 맨션 (Haunted Mansion, The)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 244,034/280,896 (13% idle) — CPU 271% of budget
    */

   /* BSWE  스타워즈 - 플라이트 오브 더 팔콘 (Star Wars - Flight of the Falcon)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 245,753/280,896 (13% idle) — CPU 273% of budget
    */

   /* FPTJ  패미콤 미니 - Vol. 24 - 빛의 신화 - 팔루테나의 거울
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 247,080/280,896 (12% idle) — CPU 275% of budget
    */

   /* FTBJ  패미콤 미니 - Vol. 17 - 타카하시 명인의 모험섬 (Famicom Mini 17 - Takahashi Meijin no Bouken-jima)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 248,182/280,896 (12% idle) — CPU 276% of budget
    */

   /* B9AJ  쿠니오군 열혈 컬렉션 1 (Kunio-kun Nekketsu Collection 1)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 249,556/280,896 (11% idle) — CPU 277% of budget
    */

   /* FMPJ  패미콤 미니 - Vol. 08 - 마피 (Famicom Mini 08 - Mappy)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 250,540/280,896 (11% idle) — CPU 278% of budget
    */

   /* B74J  허드슨 베스트 콜렉션 Vol.4 수수께끼 콜렉션
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 251,179/280,896 (11% idle) — CPU 279% of budget
    */

   /* FMRE  클래식 NES 시리즈 - 메트로이드 (Classic NES Series - Metroid)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 251,690/280,896 (10% idle) — CPU 280% of budget
    */

   /* B76J  허드슨 베스트 콜렉션 Vol.6 (Hudson Best Collection Vol. 6 - Bouken-jima Collection)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 252,710/280,896 (10% idle) — CPU 281% of budget
    */

   /* B73J  허드슨 베스트 콜렉션 Vol.3 (Hudson Best Collection Vol. 3 - Action Collection)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 252,884/280,896 (10% idle) — CPU 281% of budget
    */

   /* B7IJ  허드슨 베스트 콜렉션 Vol.1 (Hudson Best Collection Vol. 1 - Bomberman Collection)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 253,497/280,896 (10% idle) — CPU 282% of budget
    */

   /* FMKJ  패미콤 미니 - Vol. 18 - 마계촌 (Famicom Mini 18 - Makaimura)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 257,771/280,896 (8% idle) — CPU 286% of budget
    */

   /* AWOE  울펜슈타인3D
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 258,101/280,896 (8% idle) — CPU 287% of budget
    */

   /* FMRJ  패미콤 미니 - Vol. 23 - 메트로이드
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 258,496/280,896 (8% idle) — CPU 287% of budget
    */

   /* B75J  허드슨 베스트 콜렉션 Vol.5 슈팅 콜렉션 (Hudson Best Collection Vol. 5 - Shooting Collection)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 258,513/280,896 (8% idle) — CPU 287% of budget
    */

   /* BIRK  아이언 키드 (Iron Kid)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 267,284/280,896 (5% idle) — CPU 297% of budget
    */

   /* APZP  핀볼 어드밴스 (Pinball Advance)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 271,091/280,896 (3% idle) — CPU 301% of budget
    */

   /* B9BJ  쿠니오군 열혈 컬렉션 2 (Kunio-kun Nekketsu Collection 2)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 275,515/280,896 (2% idle) — CPU 306% of budget
    */

   /* AGAJ  그라디우스 제네레이션 (Gradius Generation)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 277,885/280,896 (1% idle) — CPU 309% of budget
    */

   {
      // 그라디우스 갤럭시즈 (Gradius Galaxies)
      //   exec 277,887/280,896 cy/frame (1% idle) — CPU 309% of budget
      "AGAE",                      /* gamepak_code         */
      0,                           /* flags (gpSP auto-detects the save type) */
      0x8013844,                   /* idle_loop_target_pc  */
      0,                           /* translation_gate_target_1 */
      0,                           /* translation_gate_target_2 */
      0,                           /* translation_gate_target_3 */
   },

   /* AGAP  그라디우스 제네레이션
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 277,889/280,896 (1% idle) — CPU 309% of budget
    */

   /* B9CJ  쿠니오군 열혈 컬렉션 3 (Kunio-kun Nekketsu Collection 3)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 277,916/280,896 (1% idle) — CPU 309% of budget
    */

   /* AMHJ  봄버맨MAX2
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 277,934/280,896 (1% idle) — CPU 309% of budget
    */

   /* BLJK  Legendz - Buhwarhaneun Siryeonyi Seom
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 278,246/280,896 (1% idle) — CPU 309% of budget
    */

   /* BUZE  얼티밋 아케이드 게임즈 (Ultimate Arcade Games)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 279,227/280,896 (1% idle) — CPU 310% of budget
    */

   /* Home  어나더 월드 (Another World)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 279,325/280,896 (1% idle) — CPU 310% of budget
    */

   /* TRNX  트레인 엑스
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 279,461/280,896 (1% idle) — CPU 311% of budget
    */

   /* AJGE  타잔 - 정글로 돌아오다
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 279,503/280,896 (0% idle) — CPU 311% of budget
    */

   /* BDIJ  강아지와 함께 애정 이야기 (Koinu to Issho - Aijou Monogatari)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 279,668/280,896 (0% idle) — CPU 311% of budget
    */

   /* BUCE  얼티밋 카드 게임즈 (Ultimate Card Games)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 280,248/280,896 (0% idle) — CPU 311% of budget
    */

   /* AI3E  이리디온3D
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 280,264/280,896 (0% idle) — CPU 311% of budget
    */

   /* AEWJ  위닝일레븐
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 280,325/280,896 (0% idle) — CPU 311% of budget
    */

   /* AMWE  머펫 핀볼 메이헴 (Muppet Pinball Mayhem)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 280,431/280,896 (0% idle) — CPU 312% of budget
    */

   /* AWDE  웨이크보딩 (Wakeboarding Unleashed Featuring Shaun Murray)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 280,565/280,896 (0% idle) — CPU 312% of budget
    */

   /* BTLJ  미나노 소프트 시리즈 해피 트럼프 20 (Minna no Soft Series - Happy Trump 20)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 280,588/280,896 (0% idle) — CPU 312% of budget
    */

   /*       아토믹스F (Atomix)
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 280,646/280,896 (0% idle) — CPU 312% of budget
    */

   /* BMHJ  메달 오브 아너 어드밴스
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 280,650/280,896 (0% idle) — CPU 312% of budget
    */

   /* AI2E  이리디온II
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 280,670/280,896 (0% idle) — CPU 312% of budget
    */

   /* AKOJ  킹 오브 파이터즈 EX 네오 블러드 + 33 NES
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 280,834/280,896 (0% idle) — CPU 312% of budget
    */

   /* tvap  GBA TV 튜너
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 280,890/280,896 (0% idle) — CPU 312% of budget
    */

   /* A7KJ  별의 커비 - 꿈의 샘 디럭스 (Kirby - Nightmare in Dream Land) (2)
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 280,896/280,896 (0% idle) — CPU 312% of budget
    */

   /* AGBJ  닌텐도 클라이언트 바이너리
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 280,896/280,896 (0% idle) — CPU 312% of budget
    */

   /* AGSA  플레이얀 AV 플레이어
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 280,896/280,896 (0% idle) — CPU 312% of budget
    */

   /* AIKP  인터네셔날 가라데 어드밴스
    * Hunted (pc histogram + A/B): there is NO wait loop to skip. The frame goes
    * into real work, so no address would make this lighter — it is this heavy.
    * exec 280,896/280,896 (0% idle) — CPU 312% of budget
    */

   /* GBAP  GBA 미니캠
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 280,896/280,896 (0% idle) — CPU 312% of budget
    */

   /* PASS  GBA 무비 플레이어 V2
    * NOT MEASURED — its wait loop was never found, so the spin got counted as
    * work. The number below is the probe's failure, not the game's weight.
    * exec 280,896/280,896 (0% idle) — CPU 312% of budget
    */

