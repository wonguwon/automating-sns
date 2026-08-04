# Current

## Loop State

상태: ready

현재 작업:
- 2단계(Python 로직 분리)와 4단계(Python Worker)를 사실상 완료했다. 나머지 services 함수
  (GPT/이미지/TTS/렌더 포함)를 전부 이관했고, 카드뉴스 경로·릴스 경로를 실제로 끝까지
  돌려 검증했으며(진짜 GPT/이미지/TTS API 호출, 진짜 Playwright/ffmpeg 실행), 발견된 통합
  공백 2건(릴스 이미지→대본, 카드뉴스 표지→content.json)을 코드로 메웠다. `worker.py`의
  `DISPATCH`에 `JobType.java`의 10개 타입을 전부 연결했다.

다음 실행 후보(사용자 확정 순서, 2026-08-03):
1. [x] `storage/`의 런타임 산출 폴더를 `.gitignore`에 추가 완료 — [decisions.md](decisions.md)
   참고. `storage/assets/fonts/`는 소스 자료로 보고 추적 제외하지 않되 아직 커밋은 안 함.
2. [x] users/projects 생성 API 추가, `DevDataSeeder` 정리 완료 — [decisions.md](decisions.md)
   참고. 로컬 MySQL로 생성/조회/목록/404/400 curl 검증 완료, 회귀 없이 job 생성도 확인.
3. [x] 5단계(React 프론트) 뼈대 착수 완료 — `frontend/`(Vite+React+TS), 대시보드/프로젝트
   상세 화면 + 백엔드 API 연결까지 Playwright로 실제 브라우저 검증 완료
   ([decisions.md](decisions.md) 참고). 사용자 선택 범위가 "뼈대만 먼저"였으므로 나머지
   화면(결과 파일 보기 등)은 다음 세션에서 이어간다.
4. `provider="seedream"`(ARK_API_KEY) 경로는 아직 미검증 — 사용자가 키를 추가하면 확인
   (순서와 무관하게 키 준비되는 대로 별도 처리)

막힌 문제:
- 없음

사용자 결정 필요:
- 없음(제안 목록만 있음, 급한 것 없음)

### 상태 값 규칙

- `ready`: 다음 작업을 진행할 수 있음
- `working`: 작업 중
- `blocked`: 오류나 구조 문제로 진행 불가
- `needs-decision`: 사용자 결정 필요
- `done`: 현재 로드맵 기준 진행할 작업 없음


## 진행 중인 작업(2026-08-03)

- React 프론트 뼈대 착수 — `frontend/`(Vite, React 19, TypeScript, `npm`). 대시보드
  (`src/pages/DashboardPage.tsx`, ownerId 기반 프로젝트 목록/생성)와 프로젝트 상세
  (`src/pages/ProjectDetailPage.tsx`, job 생성 폼 + job 목록)까지만 구현하고 멈췄다
  (사용자 선택: "프로젝트 뼈대만 먼저"). `src/api/client.ts`/`src/api/types.ts`로 백엔드
  연결 경계를 뒀다. Vite dev 서버가 `/api`를 Spring Boot(8080)로 프록시(`vite.config.ts`).
  실제 로컬 MySQL + Spring Boot(`local` 프로필) + Vite dev 서버를 함께 띄우고 Playwright로
  브라우저에서 목록 조회→상세 이동→job 생성→목록 갱신까지 전부 실제로 확인했다(콘솔 에러
  없음). 자세한 내용은 [decisions.md](decisions.md) 참고. 결과 파일 보기(PNG/mp4 등)는
  아직 없음 — Asset API가 생긴 뒤 재검토.
- 3단계(Spring Boot 백엔드) 완료 — `backend-spring/`(Gradle, 패키지 `ai.oneground.autosns`,
  Java 17, Spring Boot 4.0.7)는 사용자가 Spring Initializr로 직접 생성했다. User/Project/
  Asset/Job 최소 엔티티+Repository, `POST/GET /api/jobs` API를 구현했다. 로컬 MySQL(3306,
  스키마 `auto_sns`)에 실제로 연결해 curl로 생성(201)/단건 조회(200)/프로젝트별 목록(200)/
  존재하지 않는 job(404)/존재하지 않는 project(404)/유효성 검증 실패(400)까지 확인했다.
  DB 계정 정보는 `application-local.yaml`(Git 추적 제외, local 프로필)에만 있다.
- User/Project 생성 API를 추가하고(`POST/GET /api/users`, `POST/GET /api/projects`,
  `GET /api/projects?ownerId=`) `config/DevDataSeeder.java`는 정리(삭제)했다(2026-08-03,
  [decisions.md](decisions.md) 참고).
- 2단계(Python 로직 분리) — `services/rss.py`(RSS 소스 그룹 관리·수집)를 첫 실제 구현
  대상으로 완료했다: `list_feed_groups`, `create_feed_group`(GPT 피드 제안 제외 —
  [decisions.md](decisions.md) 참고), `add_feed`, `update_feed`(부분 수정), `remove_feed`,
  `health_check_group`, `collect_feed_items`. `health_check_group`/`collect_feed_items`는
  실제 네트워크(BBC RSS)로 수동 스모크 테스트까지 확인했다.
- legacy 코드의 절대 import 문제는 services 파일을 새로 작성(legacy 파일 직접 import 안
  함)하는 방식으로 자연히 우회했다 — 모든 services 파일이 이 방식을 따랐다.
- 테스트 인프라: `backend-python/.venv`(로컬 전용 가상환경, 시스템 파이썬 미사용),
  `backend-python/pytest.ini`.
- `pipeline_state.py` → `services/pipeline.py`(`load_pipeline_state`/`save_pipeline_state`,
  `core/paths.py`에 `PIPELINE_DIR`). legacy의 `save_state(**updates)`(임의 키+런타임 검증)
  대신 `SavePipelineStateRequest` dataclass(None=기존 값 유지)로 이관했다. 지금은 거의
  모든 GPT/이미지/TTS 함수가 이 매니페스트를 실제로 읽고 쓴다.
- `core/config.py`에 `load_api_keys()` → `ApiKeys`(openai/ark/typecast, 누락 시 None —
  DB 설정과 달리 세 키 모두 선택 사항). `core/clients.py`에 `get_openai_client()`/
  `get_ark_client()`(키 없으면 ValueError).
- `services/templates.py` 완료: `list_templates`/`get_template`/`create_template`/
  `update_template_files`/`add_template_examples`/`delete_template_example`/
  `delete_template`. `core/paths.py`에 `TEMPLATES_DIR`.
- **2단계 나머지 services 함수(GPT/이미지/TTS/렌더) 이관 + 실제 실행 검증 + DISPATCH 연결
  전부 완료(2026-08-03, 사용자 지시: "다 해두고 나중에 실행방법 알려주면
  사용자확인하는 식으로" → 이후 "시작해"로 실제 실행까지 승인)**:
  - `services/research.py`: `select_candidates`(GPT로 RSS 항목 → 후보 카드, `storage/
    candidates/<group_id>/<날짜>.json` 저장), `run_deep_research`(원문 fetch + GPT로
    조사 노트 생성, `storage/research/<id>.md` 저장 + pipeline_state에 candidate/
    research_note_path 기록).
  - `services/cardnews.py`: `generate_content_json`(템플릿 prompt.md를 시스템 프롬프트로
    사용, `storage/content/<id>.json` 저장. JSON 파싱 실패 시 예외 대신 content=None+원본
    출력 반환 — legacy 의도 유지), `generate_insta_caption`, `set_cover_image`(신규 —
    아래 "실제 실행 중 발견한 공백" 참고).
  - `services/image.py`: `generate_cover_image`/`generate_scene_image`(provider="openai"
    또는 "seedream"). API 키 누락은 ValueError(즉시 실패)지만, 실제 이미지 생성 API 호출
    자체가 실패하면 예외 대신 image_uri=None+error 메시지 반환 — legacy의 "실패 시 단색
    폴백" 의도 유지.
  - `services/reel.py`: `generate_reel_script`, `set_scene_resolved_image`(신규 — 아래
    참고). 릴스 사진 라이브러리는 이관하지 않음(photo_library는 호출부가 직접 넘김).
  - `services/tts.py`: `list_voices`/`synthesize_line`(Typecast REST). legacy는 TTS
    실패를 소프트 실패로 다뤘지만 여기서는 하드 예외로 바꿨다(오디오 없이는 render_reel이
    이어질 수 없어서). 성공 시 pipeline_state.reel_audio_dir 기록.
  - `services/render.py`: `render_cardnews`(Playwright/chromium), `render_reel`(ffmpeg
    zoompan/drawtext/concat).
  - `core/paths.py`에 `CAND_DIR`/`RESEARCH_DIR`/`CONTENT_DIR`/`ASSETS_DIR`/
    `REEL_SCRIPT_DIR`/`REEL_IMAGES_DIR`/`REEL_AUDIO_DIR`/`OUTPUTS_DIR`/`CARDNEWS_OUTPUT_DIR`/
    `REEL_OUTPUT_DIR` 추가.
  - **의존성 설치**: `backend-python/.venv`에 `openai`/`requests`/`beautifulsoup4`/
    `playwright`를 설치했다(사용자 확인 후, `requirements.txt`에는 이미 있던 패키지들).
    이후 실행 검증 중 이 venv의 Playwright(1.62.0)가 요구하는 브라우저 revision이 로컬
    캐시에 없다는 걸 발견해 `playwright install chromium`도 실행했다(사용자 확인 후,
    Microsoft CDN에서 다운로드) — **처음에 "이미 설치돼 있다"고 확인한 건 다른 도구가
    설치한 다른 revision이었던 것으로 판명**, 실제로 실행해보고서야 드러났다.
  - 폰트 파일 `Pretendard-Black.otf`를 `v3-semi-auto/assets/fonts/`에서
    `storage/assets/fonts/`로 복사했다(v3 원본은 그대로 둠).
  - **실제 실행 검증 완료**: `smoketest-cardnews-01`이라는 테스트 content_id로 카드뉴스
    경로(select_candidates → run_deep_research → generate_content_json →
    generate_cover_image → render_cardnews)와 릴스 경로(generate_reel_script →
    generate_scene_image×3 → set_scene_resolved_image → synthesize_line×9 → render_reel)
    를 각각 실제 GPT/이미지/TTS API 호출과 실제 Playwright/ffmpeg 실행으로 끝까지
    돌렸다 — 카드뉴스 PNG 6장×2세트, 릴스 mp4(17.75초) 전부 실제로 생성되어 육안으로
    확인했다(스크린샷/프레임 확인함).
  - **실제 실행 중 발견한 통합 공백 2건**을 코드로 메웠다:
    1) `generate_cover_image`가 만든 이미지가 `content.json`의 `cover.image`에 반영되지
       않아 `render_cardnews`가 표지 이미지 없이(단색 폴백) 렌더됨 → `cardnews.py`에
       `set_cover_image(content_id, image_uri)` 추가.
    2) 릴스 대본의 `resolved_image_path`를 채우는 함수가 원래 없었음(legacy도 UI 단계
       에서만 했음) → `reel.py`에 `set_scene_resolved_image(content_id, scene_index,
       image_path)` 추가(이건 스모크 테스트 전, 계획 단계에서 미리 발견해 추가함).
  - `worker.py`의 `DISPATCH`에 `JobType.java`의 나머지 9개 타입 전부 연결:
    `CANDIDATE_SELECT`/`DEEP_RESEARCH`/`CARDNEWS_GENERATE`/`COVER_IMAGE_GENERATE`/
    `CARDNEWS_RENDER`/`REEL_SCRIPT_GENERATE`/`SCENE_IMAGE_GENERATE`/`TTS_SYNTHESIZE`/
    `REEL_RENDER`. `COVER_IMAGE_GENERATE`/`SCENE_IMAGE_GENERATE`의 dispatch 함수는
    이미지 생성 직후 `set_cover_image`/`set_scene_resolved_image`를 자동으로 호출한다.
  - 실제 로컬 MySQL에 `CARDNEWS_RENDER` job을 직접 넣고 `worker.poll_once()`가 이를
    집어 `DONE`으로 완료 처리하는 것도 1회 수동 확인(테스트 스위트에는 포함 안 함, 확인
    후 해당 job/project/user 행 정리함).
  - `jobs.type` 컬럼이 실제로는 `JobType.java` 값만 허용하는 SQL `ENUM`이라는 것도 이
    과정에서 확인했다(VARCHAR로 알고 있었던 게 틀림 — 임의 문자열 삽입 시 `Data
    truncated` 오류로 발견). `tests/test_worker.py`의 "연결 안 된 타입" 테스트는 DB
    통합 테스트 대신 `DISPATCH` 키 목록 대조로 바꿨다.
  - 테스트: `test_clients.py`/`test_research.py`/`test_cardnews.py`/`test_image.py`/
    `test_reel.py`/`test_tts.py`/`test_render.py`/`test_worker.py` 전체 — **98개 전부
    통과**. `render.py`는 Playwright/ffmpeg 실행부를 monkeypatch로 대체하고 순수 헬퍼
    함수(자막 줄바꿈/모션 필터식/샷 묶기 등)는 직접 검증했다.
  - `provider="seedream"`(ARK_API_KEY)만 미검증으로 남아 있다.
  - 스모크 테스트로 생성된 실제 파일들(`storage/candidates/smoketest-group/`,
    `storage/research/smoketest-cardnews-01.md`, `storage/content/
    smoketest-cardnews-01.json`, `storage/assets/cover-smoketest-cardnews-01.png`,
    `storage/outputs/cardnews/smoketest-cardnews-01/`, `storage/reel_script/
    smoketest-cardnews-01.json`, `storage/reel_images/smoketest-cardnews-01/`,
    `storage/reel_audio/smoketest-cardnews-01/`, `storage/outputs/reel/
    smoketest-cardnews-01.mp4`)은 정리하지 않고 그대로 남겨뒀다 — `storage/`가 현재
    `.gitignore`에 없어 untracked 상태로 쌓여 있다(아래 "다음 작업" 참고).

## 다음 작업

1. [x] `storage/`의 런타임 산출 하위 폴더를 `.gitignore`에 추가 완료(2026-08-03,
   [decisions.md](decisions.md) 참고).
2. [x] users/projects 생성 API 추가하고 `DevDataSeeder` 정리 완료(2026-08-03,
   [decisions.md](decisions.md) 참고).
3. [x] 5단계(React 프론트) 뼈대(대시보드/프로젝트 상세) 완료(2026-08-03,
   [decisions.md](decisions.md) 참고).
4. 5단계 나머지 화면 이어가기 ← 다음 — 결과 파일 보기(Asset API 필요), 템플릿 관리
   (`services/templates.py`)를 job 큐 없이 직접 API로 노출할지 결정 필요.
5. `provider="seedream"`(ARK_API_KEY) 경로는 사용자가 키를 추가하면 실제 실행으로 확인한다.

자세한 순서는 [roadmap.md](roadmap.md) 참조.

## 주의사항

- 기존 v3 프로젝트는 수정하지 않는다.
- auto-sns 폴더 안에서만 작업한다.
- React 프론트는 뼈대(대시보드/프로젝트 상세)까지만 진행했다 — 나머지 화면은 사용자와
  순서를 다시 확인하고 진행한다(한 번에 다 만들지 않기로 함).
- 대용량 산출물, mp4, png 결과물, data 실행 결과는 복사하지 않는다(생성은 이번처럼 실제
  services 실행으로 만들어지는 건 별개).
- DB 계정 정보(`application-local.yaml`, `backend-python/.env`)는 Git에 올리지 않고
  대화에도 노출하지 않는다.
- `ARK_API_KEY`는 사용자가 직접 `.env`에 추가하기로 했다 — `.env` 파일은 건드리지 않는다.
- 실제 GPT/이미지/TTS API 호출이나 Playwright/ffmpeg 실행이 필요한 새 작업은 여전히
  실행 전 사용자 확인을 받는다(비용 발생 가능) — 이번에 검증됐다고 앞으로는 확인 없이
  실행해도 된다는 뜻은 아니다.
