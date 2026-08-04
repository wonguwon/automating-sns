# Roadmap

## 1단계: 프로젝트 초기 구조

- auto-sns 프로젝트 폴더 생성
- 기존 v3에서 필요한 Python 파일만 legacy로 복사
- services/core 골격 생성
- README, CLAUDE.md, wiki, commands 작성

## 2단계: Python 로직 분리

- [x] 기존 legacy 코드에서 재사용 가능한 함수 파악 — Streamlit 의존은 pipeline_common.py에만
  있고 나머지 legacy 파일은 순수 로직임을 확인 (`wiki/current.md` 참고)
- [x] Streamlit 의존성 제거 지점 파악
- [x] services 함수 input/output DTO 초안 작성 — dataclass 패턴 확정(`wiki/decisions.md`)
- [x] storage 경계 최소 설계 — `storage/` 하위 기능별 폴더 + `core/paths.py` (MySQL 스키마
  전까지의 임시 방침)
- [x] 작은 기능 하나를 services 계층으로 감싸기 — `services/rss.py`(RSS 소스 그룹 관리·수집)
- [x] 나머지 services 파일(research/cardnews/image/reel/render/tts) 실제 로직 이관 완료
  (2026-08-03) — `research.select_candidates/run_deep_research`,
  `cardnews.generate_content_json/generate_insta_caption/set_cover_image`,
  `image.generate_cover_image/generate_scene_image`,
  `reel.generate_reel_script/set_scene_resolved_image`, `tts.list_voices/synthesize_line`,
  `render.render_cardnews/render_reel`. **실제 GPT/이미지/TTS API 호출과 Playwright/ffmpeg
  실행까지 카드뉴스·릴스 경로 전체를 실제로 돌려 검증 완료**(`smoketest-cardnews-01`,
  `wiki/decisions.md` 참고) — 이 과정에서 cover 이미지→content.json 연결 공백을 발견해
  `set_cover_image`로 메웠다. `provider="seedream"`만 ARK_API_KEY 부재로 미검증
- [x] `core/config.py` API 키 로딩 정책 결정 — `load_api_keys()` → `ApiKeys`(openai/ark/
  typecast, 누락 시 None. `wiki/decisions.md` 참고). 실제 사용 시점의 예외 처리는 각
  services 함수 이관 때 추가
- [x] `pipeline_state.py`의 services 이관 위치 결정 — `services/pipeline.py`
  (`load_pipeline_state`/`save_pipeline_state`, `wiki/decisions.md` 참고). 아직 어느
  job 타입에도 연결하지 않음(다른 services 함수가 실제로 쓰게 될 때 연결)
- [x] 템플릿 세트 관리 함수(legacy: `pipeline_common.py`의 `list_templates` 등)의 이관
  완료 — `services/templates.py`(`wiki/decisions.md` 참고). job 타입으로 연결하지는
  않음(템플릿 관리는 API 요청 하나로 처리 가능한 짧은 작업이라 job 큐를 거칠 필요가 있는지
  5단계 React 연동 시 재검토)

## 3단계: Spring Boot 백엔드

- [x] Spring Boot 프로젝트 생성 — `backend-spring/`(Gradle, `ai.oneground.autosns`)
- [x] MySQL 연결 — 로컬 MySQL(3306), 스키마 `auto_sns`, 계정 정보는 `application-local.yaml`
- [x] JPA 기본 설정 — `ddl-auto: update`(임시 방침)
- [x] users, projects, assets, jobs 최소 엔티티 작성
- [x] job 생성/조회 API 작성 — `POST /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs?projectId=`
  (실제 로컬 MySQL로 생성/조회/404/400 케이스까지 curl로 검증 완료, `wiki/current.md` 참고)
- [x] users/projects 생성·조회 API — `POST/GET /api/users`, `POST /api/projects`,
  `GET /api/projects/{id}`, `GET /api/projects?ownerId=`(2026-08-03, 실제 로컬 MySQL로
  생성/조회/목록/404/400 케이스까지 curl로 검증 완료, `wiki/decisions.md` 참고).
  `config/DevDataSeeder.java`는 정리(삭제)했다 — 실제 API로 대체.
- [ ] assets 생성·조회 API (아직 없음 — 엔티티/Repository만 존재)

## 4단계: Python Worker

- [x] MySQL jobs polling worker 작성 — `backend-python/ai_sns_worker/worker.py`(PyMySQL,
  `core/db.py`/`core/config.py`), DB 접속 정보는 `backend-python/.env`
- [x] PENDING → RUNNING → DONE/FAILED 상태 흐름 구현 — 낙관적 잠금(`UPDATE ... WHERE
  status='PENDING'`)으로 동시 처리 방지, 실제 로컬 MySQL로 검증(`tests/test_worker.py`)
- [x] Python service 함수 호출 연결 — `JobType.java`의 10개 타입 전부 `DISPATCH`에
  연결 완료(2026-08-03). `RSS_COLLECT`는 4단계에서, 나머지 9개(`CANDIDATE_SELECT`/
  `DEEP_RESEARCH`/`CARDNEWS_GENERATE`/`COVER_IMAGE_GENERATE`/`CARDNEWS_RENDER`/
  `REEL_SCRIPT_GENERATE`/`SCENE_IMAGE_GENERATE`/`TTS_SYNTHESIZE`/`REEL_RENDER`)는 실제
  GPT/이미지/TTS API 호출과 Playwright/ffmpeg 실행까지 검증한 뒤 연결했다(`wiki/decisions.md`
  참고). 실제 MySQL에 job을 넣고 `worker.poll_once()`가 `DONE`으로 완료 처리하는 것도
  1회 수동 확인. 단위 테스트(monkeypatch)는 `tests/test_worker.py`에 12개 추가, 전체
  98개 통과
- [x] 로그와 에러 메시지 저장 — `logging` 모듈 + `jobs.error_message` 컬럼

## 5단계: React 프론트

- [x] React(Vite) 프로젝트 생성 — `frontend/`(Vite, React 19, TypeScript, `npm`).
  `react-router-dom@7.18.2`(BrowserRouter). Vite dev 서버(`vite.config.ts`)가 `/api`를
  `http://localhost:8080`으로 프록시해 백엔드 CORS 설정 없이 연결(2026-08-03)
- [x] 대시보드 뼈대 — `src/pages/DashboardPage.tsx`: ownerId로 프로젝트 목록 조회, 새
  프로젝트 생성 폼. "전체 프로젝트 목록" API가 없어 ownerId 입력 기반(사용자/인증 개념이
  아직 없어 임시 방편, 인증 도입 시 재검토)
- [x] 프로젝트 상세 뼈대 — `src/pages/ProjectDetailPage.tsx`: 프로젝트 정보, job 생성 폼
  (타입 select + inputJson textarea), job 목록(상태/결과·에러 표시)
- [x] job 생성/상태 조회 — 위 프로젝트 상세 페이지에 포함(별도 화면으로 분리하지 않음)
- [ ] 결과 파일 보기 — 아직 없음. 현재는 `resultJson` 텍스트만 표시하고 실제 파일(PNG/mp4)
  보기는 Asset API가 생긴 뒤 재검토
- 실제 로컬 MySQL로 연결해 Playwright로 브라우저 검증 완료(`wiki/decisions.md` 참고)

## 6단계: 기능 이관

- RSS 수집
- 후보 선별
- 딥리서치
- 카드뉴스 JSON 생성
- 표지 이미지 생성
- 카드뉴스 렌더
- 릴스 대본 생성
- TTS 생성
- 릴스 조립
- 템플릿 관리

## 7단계: 배포

- Mac mini Docker Compose 구성
- 환경변수/API 키 관리
- 로컬 스토리지 마운트
- 내부망 접속 확인
