# 개선점 — 무엇이 실제로 잘못되어 있고, 무엇이 잘 되어 있는가

> `v1.11.2` (`fe3b898`) 시점 점검. **실행하고 측정해서 확인한 것만** 적었다.
> 각 항목에 `파일:줄` 근거를 붙였고, 확인하지 못한 것은 "미확인"으로 표시했다.
> 마지막 절 [점검하지 않은 영역](#점검하지-않은-영역)에 사각지대를 남겼다.

## 먼저, 이 코드베이스는 건강하다

점검의 결론부터 적는다. 아래 목록이 길다고 해서 상태가 나쁜 게 아니다.

| 측정 | 결과 |
|---|---|
| 백엔드 테스트 | **1000 passed**, 1 skipped (71s) |
| 백엔드 커버리지 | **96%** — 4,411 stmts 중 186 미커버 |
| 프론트엔드 빌드 | **성공** (4.31s · `index-*.js` 380.78 kB / gzip 115.39 kB) |
| `TODO` / `FIXME` / `HACK` | **0건** |
| npm audit | 3건 — **전부 dev 의존성**, 배포 이미지 미노출 |

커버리지 96%는 이 규모의 개인 프로젝트에서 드물다. 라우터 21개 중 13개가 100%다.
경로 탐색 방어(`extra.py:21`, `downloads.py:148`)도 제대로 되어 있고, DB 마이그레이션은
컬럼마다 "왜 이 컬럼이 필요한가"가 주석으로 남아 있다.

> [!NOTE]
> **커버리지가 곧 정확성은 아니다.** 아래 [B-1](#b-1-대용량-파일을-통째로-메모리에-적재)의
> `downloads.py`는 커버리지 **100%**인데도 결함이 있다. 테스트가 작은 파일만 다루기 때문이다.

## 📑 한눈에 보기

| # | 항목 | 성격 | 영향 | 상태 |
|---|---|---|---|---|
| [A-1](#a-1-데모-시스템-목록이-백엔드와-3건-어긋남) | 데모 시스템 목록이 백엔드와 3건 어긋남 | 🟡 사소 | 데모 페이지 한정 · 앱 동작 영향 없음 | 30분 |
| [A-2](#a-2-envexample이-안내하는-설정이-docker에서-동작하지-않음) | 문서대로 설정해도 동작 안 함 | 🔴 결함 | 설정 13개가 Docker에서 무효 | **✅ v1.11.4** |
| [A-3](#a-3-백엔드-에러-메시지가-한국어-전용-56135) | 에러 메시지 한국어 전용 (68/135) | 🟠 품질 | 11개 언어 사용자가 한글 토스트를 봄 | **✅ v1.11.6** |
| [A-4](#a-4-한국어-외-11개-로케일이-170개-문자열-뒤처짐) | 로케일 11개가 ~170개 문자열 누락 | 🟠 품질 | UI 약 30%가 영어로 샘 | 반나절 |
| [B-1](#b-1-대용량-파일을-통째로-메모리에-적재) | 대용량 파일 메모리 적재 | 🔴 위험 | Pi에서 최대 1 GB 스파이크 | **✅ v1.11.4** |
| [B-2](#b-2-ci가-릴리스-태그에서만-테스트를-돈다) | CI가 태그에서만 테스트 | 🔴 위험 | 254커밋이 무검증 통과 | **✅ v1.11.4** |
| [B-3](#b-3-python-의존성-미고정) | Python 의존성 미고정 | 🟠 위험 | 같은 커밋이 다른 이미지를 만듦 | **✅ v1.11.4** |
| [B-4](#b-4-테스트가-12-gb-실파일을-만든다) | 테스트가 1.2 GB 실파일 생성 | 🟠 위험 | tmpfs 고갈 · RAM 1 GiB 스파이크 | **✅ v1.11.4** |
| [C-1](#c-1-큰-파일이-곧-변경이-잦은-파일)–[C-7](#c-7-npm-audit-3건--전부-dev-의존성) | 유지보수성 7건 | 🟡 부채 | 계속 비용을 무는 것들 | — |

- [A. 확인된 불일치](#a-확인된-불일치) — 문서·데모와 실제가 어긋난 것
- [B. 위험](#b-위험) — 아직 사고가 안 났을 뿐인 것
- [C. 유지보수성](#c-유지보수성) — 당장 고장난 건 아니지만 계속 비용을 무는 것
- [실행 순서 제안](#실행-순서-제안)
- [점검하지 않은 영역](#점검하지-않은-영역)

---

# A. 확인된 불일치

## A-1. 데모 시스템 목록이 백엔드와 3건 어긋남

`frontend/src/demo.js:16`의 `SYSTEMS` 배열은 `backend/app/systems.py`를 손으로 복사한
것이다. 프로그램으로 대조하면 3개가 어긋나 있다:

| 시스템 | 백엔드 (실제) | `demo.js` (표시) |
|---|---|---|
| `lynx` | `experimental: `**`true`** | `experimental: `**`false`** |
| `homebrew` | `exts: [bin, dat, `**`xip, smc`**`]` | `exts: [bin, dat]` |
| `col` | `name: "Coleco`**` `**`Vision"` | `name: "ColecoVision"` |

효과는 GitHub Pages 데모에 한정된다. `demo.js:116`이 `experimental`로 목록을 거르므로
데모 기본 뷰에는 Atari Lynx가 뜨고, `GNW_EXPERIMENTAL_MODE=false`인 기본 설치에는 뜨지
않는다. 나머지 둘은 데모 전용 정적 데이터라 아무 동작에도 영향이 없다.

> 처음에는 이 항목을 결함으로 올렸는데, 과한 등급이었다. Lynx는 업스트림 `main`에
> 2026-07-05 병합되어 릴리스만 나오면 공식으로 승격된다 — 데모가 틀렸다기보다 며칠
> 앞서 있는 쪽에 가깝다. 앱이 고장나는 종류의 문제가 아니다.

**원인** — 수동 동기화. `systems.py`는 90일간 26커밋, `demo.js`는 16커밋으로 같이 고쳐지고
있지만 손으로 맞추고 있으니 새는 게 당연하다.

**수정** — 빌드 타임 생성이 정답이지만, 패리티 테스트가 훨씬 싸고 즉시 효과가 있다:

```python
# backend/tests/test_demo_parity.py
def test_demo_systems_match_backend():
    """demo.js의 SYSTEMS는 systems.py에서 복사된 것이다. 손으로 맞추고 있으니
    시스템을 더하거나 플래그를 바꿀 때마다 조용히 어긋난다."""
    ...  # demo.js의 배열을 파싱해 SYSTEMS와 비교
```

## A-2. `.env.example`이 안내하는 설정이 Docker에서 동작하지 않음

> [!TIP]
> **해결됨 (v1.11.4).** compose가 문서화된 10개 키를 `${VAR:-}`로 전달한다. 미설정 시
> 빈 문자열이 오는데, `config.py`의 `_env`/`_env_int`가 이를 "미설정"으로 읽어 기본값을
> 쓴다 — 이게 없으면 `int("")`로 컨테이너가 부팅조차 못 한다. `.env.example`에 빠져 있던
> CD/청크 캡 4개도 채웠다. 검증 스크립트로 격차 0 확인.

`.env.example:31-39`는 아래를 사용자 설정 가능한 것으로 문서화하고, `README.md:308`도
`GNW_CORS_ORIGINS`를 설정 표에 싣고 있다:

```
GNW_CORS_ORIGINS   GNW_MAX_ROM_BYTES    GNW_MAX_VIDEO_BYTES
GNW_MAX_MUSIC_BYTES   GNW_MAX_FIRMWARE_BYTES   GNW_MAX_EXTRA_BYTES
```

그런데 **컨테이너에는 하나도 전달되지 않는다.** 세 가지가 겹쳤다:

1. `docker-compose.yml:24-37`의 `environment:` 블록은 6개 키만 넘긴다.
2. `config.py:8 _load_env_file()`이 루트 `.env`를 직접 읽지만,
   `.dockerignore:22-25`의 `**/.env`가 이미지에서 제외한다.
3. compose가 자동 로드하는 `.env`는 `${...}` **치환용**이다 — compose 파일이 참조하지 않는
   변수는 컨테이너에 도달하지 않는다.

즉 **문서를 그대로 따라 설정해도 아무 일도 일어나지 않는다.** 소스에서 uvicorn으로 직접
띄울 때만 동작한다. 정작 compose의 주석은 이렇게 적혀 있다:

```yaml
environment:
  # Override any config via env; defaults match the app's config.py.   ← 실제로는 6개만
```

`config.py`가 읽는 19개 중 **13개가 compose 미전달**, 그중 7개는 `.env.example`에도 없다
(`GNW_DATA_DIR` `GNW_API_PORT` `GNW_FRONTEND_PORT` `GNW_MAX_CD_FILE_BYTES`
`GNW_MAX_CD_TOTAL_BYTES` `GNW_MAX_CHUNK_BYTES` `GNW_MAX_UPLOAD_TOTAL_BYTES`).

**수정** — compose에 `env_file: .env` 한 줄이 가장 간단하다.

## A-3. 백엔드 에러 메시지가 한국어 전용 (56/135)

> [!TIP]
> **해결됨 (v1.11.6).** AST로 세어보니 56이 아니라 **68건**이었다(f-string 12건을 정규식이
> 놓쳤다). 고유 문자열 40개를 매핑 표 하나로 영어 치환 + `ko.js` 생성을 동시에 구동해
> 어긋날 여지를 없앴다. 번역은 `toast.jsx` 한 곳에서 일어난다 — 모든 에러 토스트가
> 거기를 지나가므로 `api.js`에 `t()`를 배선할 필요가 없었다. 값이 들어가는 메시지는
> `": "` 앞 stem만 번역하고 값은 그대로 붙인다.
> 재발 방지: `test_error_language.py`가 `app/`의 `detail=`에 한글이 하나라도 들어오면
> 스위트를 깨뜨린다.

`HTTPException` 135건 중 **56건이 한글 `detail`**이다:

```python
extra.py:66     detail="빈 파일입니다"
extra.py:68     detail="파일이 너무 큽니다"
music.py:20     detail="빈 파일입니다"
gamelist.py:25  detail="gamelist 파일을 찾을 수 없습니다 (DATA에 먼저 올리세요)"
```

프론트는 이 `detail`을 **그대로 사용자에게 띄운다** — `api.js:61, 117, 126, 132, 348, 409`
전부 `new Error(body.detail)` 형태다.

공개 이미지는 `GNW_KOREAN_MODE=false`가 기본이고 UI는 12개 언어를 지원한다.
독일어 사용자가 업로드에 실패하면 **"파일이 너무 큽니다"** 토스트를 본다.

**수정** — `detail`을 영어(이 프로젝트의 소스 언어)로 통일하고 프론트에서 `t()`에 태운다.
`i18n.jsx`가 이미 "영어 원문 = 키" 구조라 추가 배선이 거의 없다.

## A-4. 한국어 외 11개 로케일이 ~170개 문자열 뒤처짐

| locale | keys | `ko` 대비 누락 | 마지막 수정 | 90일 커밋 |
|---|---:|---:|---|---:|
| `ko` | 590 | — | **2026-07-25** | **62** |
| `es` `fr` `it` `no` `pt` `ru` | 424 | 169 | 2026-07-15 | 10 |
| `de` | 423 | 170 | 2026-07-15 | 10 |
| `ja` `zh-CN` `zh-TW` | 422 | 171 | 2026-07-15 | 10 |
| `en` | 35 | — | 2026-07-13 | 2 |

11개 로케일 전부가 **2026-07-15에 멈춰 있고**, 한국어만 07-25까지 계속 간다.
`i18n.jsx`의 fallback이 영어 원문이라 앱이 깨지진 않지만, **UI의 약 30%가 영어로 샌다.**

> `en.js`가 35개인 건 정상이다. 영어가 소스 언어고 이 파일은 동음이의 오버라이드 전용이다
> (`en.js:1-5` 주석에 설명되어 있다).

누락분이 어떤 기능의 문자열인지는 세지 않았다 — 최근 기능(GBA 측정, SD 제외, 클록)에
몰려 있을 것으로 추정하나 **미확인**.

**수정** — 번역 자체보다 **재발 방지가 먼저다.** 지금은 누락을 아무도 감지하지 못한다.
CI에 키 패리티 검사를 넣고 임계치를 넘으면 실패시킨다.

---

# B. 위험

## B-1. 대용량 파일을 통째로 메모리에 적재

> [!TIP]
> **해결됨 (v1.11.4).** 세 곳 모두 `FileResponse`로 교체. 부수 이득도 실측했다 —
> Range 요청이 `206 Partial Content` / `Content-Range: bytes 1-2/14`로 응답한다.
> 업로드 경로의 `await file.read()`는 아직 남아 있다.

`downloads.py`의 세 엔드포인트가 파일 전체를 RAM에 올린다:

| 위치 | 대상 | 상한 (`config.py`) |
|---|---|---|
| `downloads.py:117` | ROM 원본 (브라우저 에뮬레이터용) | `MAX_ROM_BYTES` 64 MB |
| `downloads.py:153` | CD 트랙 `.bin` / `.iso` | **`MAX_CD_FILE_BYTES` 1 GB** |
| `downloads.py:217` | MP3 다운로드 | `MAX_MUSIC_BYTES` 64 MB |

PC Engine CD 게임을 브라우저에서 실행하면 트랙마다 최대 1 GB가 한 번에 잡힌다.

**같은 파일 안에 이미 정답이 있다.** `downloads.py:241`의 `music_stream`은 `FileResponse`를
쓰고, 주석에 이유까지 적혀 있다:

> "FileResponse honors Range requests so the audio element can seek/scrub
> (the download endpoint can't)"

세 곳을 `FileResponse`로 바꾸면 메모리 문제가 사라지고 **Range 지원이 덤으로 온다** —
에뮬레이터가 큰 CD 이미지를 부분 요청할 수 있게 되는 건 그 자체로 실질적인 개선이다.

업로드 경로도 같은 패턴이다 (전체 23곳): `videos.py:70`(512 MB 상한), `roms.py:515,557`,
`extra.py:64`, `clock.py:57`, `music.py:53`, `firmware.py:65`.
청크 업로드(`uploads.py`)는 이미 올바르게 처리하고 있으니 단발 업로드만 정리하면 된다.

## B-2. CI가 릴리스 태그에서만 테스트를 돈다

> [!TIP]
> **해결됨 (v1.11.4).** `.github/workflows/ci.yml` 신설 — `push`(main) + `pull_request`에서
> 백엔드 테스트와 프론트 빌드를 돌린다. 릴리스 워크플로의 테스트 게이트는 일부러 남겼다:
> 태그가 "이전 커밋에서 CI가 초록이었다"는 이유로 이미지를 내보내면 안 된다.

`.github/workflows/docker-publish.yml:6-9`:

```yaml
on:
  push:
    tags: ["v*"]      # ← main 푸시도, PR도 아니다
  workflow_dispatch:
```

main에 푸시하거나 PR을 열어도 **테스트가 한 번도 안 돈다.** 깨진 코드는 태그를 붙이는
순간에야 드러난다. 최근 30일 **254커밋이 전부 무검증으로** 들어갔다.

프론트엔드는 아예 빌드 검증이 없다. `pages.yml`은 머지 **후** main 푸시에 배포만 한다.

**수정** — test 잡을 별도 워크플로로 분리해 `on: [push, pull_request]`로 돌리고,
`npm ci && npm run build`를 게이트에 추가한다. 빌드가 4.3초라 비용은 무시할 수준이다.

## B-3. Python 의존성 미고정

> [!TIP]
> **해결됨 (v1.11.4).** 실행 중인 v1.11.3 컨테이너에서 읽은 실제 버전으로 `==` 고정.
> 오늘 도는 것은 그대로 두고 드리프트만 막았다.

`backend/requirements.txt`:

```
fastapi>=0.115      uvicorn[standard]>=0.32     python-multipart>=0.0.12
pillow>=10.4        httpx>=0.27                 py7zr>=1.0
capstone==5.0.7     ← 유일하게 고정됨
```

`Dockerfile:73`이 이걸 그대로 설치한다. **같은 커밋이 시점에 따라 다른 이미지를 만든다.**
몇 달 뒤 재빌드하면 FastAPI 메이저 변경을 그대로 끌어온다.

멀티아치 빌드는 amd64/arm64를 서로 다른 러너에서 병렬로 돌리므로, 그 사이에 릴리스가 끼면
**아치별로 다른 버전이 박힐 수도 있다** — 이론상 가능하다는 것이고 재현하지 않았다, **미확인**.

**수정** — `pip freeze` 기반 `requirements.lock` 또는 `==` 고정.

## B-4. 테스트가 1.2 GB 실파일을 만든다

> [!TIP]
> **해결됨 (v1.11.4).** `truncate()` 기반 sparse 파일로 전환. 해당 테스트 파일의 실제
> 디스크 사용이 **1.2 GB → 2.3 MB**, 스위트 전체는 **약 1.6 GB → 327 MB**.
> 프로덕션 코드가 `st_size`만 읽으므로 동작은 동일하다.

`backend/tests/test_packaging_more.py:554`:

```python
(cache / f"sd-{i:040x}.zip").write_bytes(b"\0" * (mb * 1024 * 1024))
```

두 테스트가 실제 바이트를 쓴다 — `test_the_cache_may_spend_what_it_is_already_holding`(:585)이
**1.0 GiB**, `test_a_tight_disk_evicts_everything_but_the_newest`(:575)가 600 MB (200×3).

문제가 둘이다:

1. `b"\0" * (1024**3)`은 **1 GiB를 먼저 RAM에 만든다.** Pi에서 그대로 스파이크.
2. 전체 실행마다 tmp에 ~1.6 GB가 남고, pytest는 기본으로 최근 3회분을 보관한다 → **약 5 GB.**
   이 머신의 `/tmp`는 tmpfs **4 GB**다. 점검 중 실제로 100% 차서 명령이 실패했고,
   07-24 실행분 1.7 GB가 아직 남아 있었다.

> [!TIP]
> **sparse 파일로 바꾸면 끝난다.** 프로덕션 코드는 `st_size`만 읽는다 —
> `packaging.py:97, 153, 309, 313, 336` 전부 `.stat().st_size`이고 내용을 절대 읽지 않으므로
> 안전하다:
>
> ```python
> with open(cache / f"sd-{i:040x}.zip", "wb") as f:
>     f.truncate(mb * 1024 * 1024)   # 디스크 0바이트, RAM 0바이트, st_size는 그대로
> ```

---

# C. 유지보수성

## C-1. 큰 파일이 곧 변경이 잦은 파일

90일 churn 상위와 파일 크기가 정확히 겹친다:

| 파일 | 줄 수 | 90일 커밋 |
|---|---:|---:|
| `frontend/src/theme.css` | 2,901 | **64** |
| `frontend/src/locales/ko.js` | 632 | 62 |
| `frontend/src/components.jsx` | **2,059** | 52 |
| `frontend/src/emulator.jsx` | 643 | 28 |
| `backend/app/routers/covers.py` | 754 | — |

`components.jsx`는 40개 export가 든 잡동사니다 — 헬퍼(`systemColor`, `langLabel`),
상수(`FLAG_OPTIONS`, `GBA_LOAD_FILTERS`), 그리고 **`RomCard` 하나가 729줄**(1213-1942).

`tabs/`로 분리한 작업은 이미 잘 되어 있다 (13개 파일, 최대 512줄).
**같은 손질을 `components.jsx`에 한 번 더 하면 된다.** `RomCard`를 자기 파일로 빼는 것만으로
절반이 준다.

백엔드는 상대적으로 양호하다. 최장 함수는 `db.py:100 _migrate` 224줄인데 선형 마이그레이션
나열이라 문제 없고, 실질 이상치는 `roms.py:35 upload_roms` 172줄 하나다.

## C-2. `backend/` 루트에 일회성 스크립트 21개, 그중 9개는 참조 0건

코드·문서·CI 어디에서도 언급되지 않는 것들:

```
atari_covers.py   a7800_covers.py  cover_vb.py   dedup_hash.py     fill_manual.py
import_snes.py    korean_vb.py     recover_covers.py               regen_clean_img.py
```

> `import_32x.py`도 이 목록에 있었으나 32X 지원 제거와 함께 삭제되었다.

게다가 `Dockerfile:76`의 `COPY backend/ ./backend/`가 이것들과 `tests/`를 **이미지에 그대로
싣는다** — `.dockerignore`에 제외 규칙이 없다.

**수정** — `backend/scripts/oneoff/`로 이동 + `.dockerignore`에 `backend/tests` 추가.

## C-3. 중복 보일러플레이트

| 중복 | 위치 | 규모 |
|---|---|---|
| `_require_rom()` **완전 동일 정의** | `covers.py:63`, `downloads.py:28` | 2곳 |
| `ascii_name` + `Content-Disposition` 조립 | `extra.py:84` `data.py:76` `covers.py:214` `downloads.py:92,123,215` | 6곳 |
| `require_session(conn, session_id)` 수동 호출 | 라우터 전역 | **65곳** |

앞의 둘은 헬퍼 하나씩으로 정리된다. 세 번째는 FastAPI `Depends`로 뽑을 수 있다 —
`main.py:42`가 `require_experimental_mode`로 **이미 그 패턴을 쓰고 있다**.

## C-4. FastAPI `@app.on_event` deprecated

`main.py:67`, `main.py:138`. 테스트 실행 시 경고로 나온다. lifespan 컨텍스트 매니저로 이전 필요.

겸사겸사 `_startup()`은 지금 **68줄짜리 마이그레이션 나열**이다 — 시드 2종, 임시파일 청소,
legacy 디렉터리 이동, 백필 2종, 스트랜디드 커버 정리, trash/백업 만료, 캐시 정리.
lifespan으로 옮길 때 `services/startup.py`로 빼면 자연스럽다.

## C-5. 도구·자동화 공백

- **린터/포매터가 전혀 없다** — ruff / eslint / prettier 설정 파일 0개.
  `pyproject.toml`도 `pytest.ini`도 없다.
- **버전 문자열 2곳 수동 동기화** — `main.py:16`의 `version="1.11.2"`와
  `frontend/package.json:4`. 지금은 일치하지만 놓치기 쉽다.
- **Node 버전 불일치** — Dockerfile은 `node:20-alpine`, 로컬은 v24.14.1.
  `package.json`에 `engines` 필드가 없다.
- `except Exception` 20건 중 3건이 `pass`로 조용히 삼킴.
- `print()` 14건 vs `logging` 4건 — 컨테이너 로그 레벨 제어가 안 된다.

## C-6. 남은 deprecation

| 대상 | 위치 | 기한 |
|---|---|---|
| `re.split(..., 1)` positional maxsplit | `gamelist.py:67, 109` | Python 3.13 deprecated → 3.14 제거. 이미지가 3.12라 지금은 안전 |
| Pillow `getdata()` | `tests/test_covers.py:111` | Pillow 14 (2027-10) 제거 |
| `@app.on_event` | `main.py:67, 138` | [C-4](#c-4-fastapi-appon_event-deprecated) 참조 |

테스트 실행 시 경고 1,186건 중 대부분이 위 셋이다.

## C-7. npm audit 3건 — 전부 dev 의존성

| 패키지 | 심각도 | 내용 |
|---|---|---|
| `postcss` ≤8.5.17 | high | sourceMappingURL 경로 탐색 → `.map` 파일 노출 |
| `vite` ≤6.4.1 | high(표기) | optimized deps `.map` 경로 탐색 |
| `esbuild` ≤0.24.2 | moderate | dev 서버가 임의 사이트의 요청에 응답 |

**셋 다 빌드/개발 서버 전용이다.** 배포 이미지에는 `dist/` 산출물만 들어가므로
**사용자에게 노출되지 않는다.** 다만 `npm run dev`를 신뢰할 수 없는 네트워크에서 돌리면
esbuild 건은 실제 위험이다. Vite 5 → 7 업그레이드로 한 번에 해소된다.

---

# 실행 순서 제안

| # | 항목 | 근거 | 비용 |
|---|---|---|---|
| ~~1~~ | ~~CI 트리거 확대~~ | ✅ v1.11.4 — `ci.yml` 신설 | — |
| ~~2~~ | ~~`FileResponse` 3곳 교체~~ | ✅ v1.11.4 — Range 지원 실측 확인 | — |
| ~~3~~ | ~~테스트 sparse 파일 전환~~ | ✅ v1.11.4 — 스위트 1.6 GB → 327 MB | — |
| ~~4~~ | ~~compose 환경변수 전달~~ | ✅ v1.11.4 — 격차 0 확인 | — |
| ~~5~~ | ~~requirements 고정~~ | ✅ v1.11.4 | — |
| 6 | demo 패리티 테스트 + 드리프트 3건 수정 | [A-1](#a-1-데모-시스템-목록이-백엔드와-3건-어긋남). 값어치는 재발 방지 쪽 | 30분 |
| ~~7a~~ | ~~에러 `detail` 영어화~~ ✅ v1.11.6 · 남은 것: 로케일 패리티 검사 | [A-3](#a-3-백엔드-에러-메시지가-한국어-전용-56135), [A-4](#a-4-한국어-외-11개-로케일이-170개-문자열-뒤처짐) | 반나절 |
| 8 | 일회성 스크립트 정리 + `.dockerignore` | [C-2](#c-2-backend-루트에-일회성-스크립트-21개-그중-9개는-참조-0건) | 20분 |
| 9 | lifespan 전환 + `RomCard` 분리 + 중복 헬퍼 정리 | [C-1](#c-1-큰-파일이-곧-변경이-잦은-파일), [C-3](#c-3-중복-보일러플레이트), [C-4](#c-4-fastapi-appon_event-deprecated) | 1일 |

**1~5번은 v1.11.4에서 처리했다.** 남은 것은 6~9번 — 데모 패리티, i18n, 스크립트 정리,
그리고 lifespan/`RomCard` 분해다.

---

# 점검하지 않은 영역

정직하게 남긴다. 아래는 이번에 보지 않았으므로, "문제가 없다"가 아니라 "모른다"이다.

- **프론트엔드 런타임 동작** — 실제 앱을 띄워 클릭해보지 않았다. React 훅 의존성 배열,
  경쟁 상태, 메모리 누수는 미확인이다. 린터가 없어 정적 검사도 불가능했다.
- **펌웨어 / SD 카드 실물 검증** — 생성된 ZIP을 실제 기기에 넣어보지 않았다.
- **A-4의 누락 문자열 내용** — 개수만 셌고, 어떤 기능의 문자열인지는 추정이다.
- **B-3의 아치별 버전 불일치** — 이론상 가능하다고만 적었고 재현하지 않았다.
- **동시성** — 여러 사용자가 동시에 업로드/ZIP 빌드할 때의 SQLite 잠금 경합.
  `db.connect()`(`db.py:85`)는 `timeout`/WAL 설정 없이 기본값을 쓴다.
  단일 세션(`session_id='public'`) 공유 라이브러리 구조라 점검 가치가 있어 보인다.
