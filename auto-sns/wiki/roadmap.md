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
- [ ] 나머지 services 파일(research/cardnews/image/reel/render/tts) 실제 로직 이관
- [ ] `core/config.py` API 키 로딩 정책 결정
- [ ] `pipeline_state.py`, 템플릿 세트 관리 함수의 이관 위치 결정

## 3단계: Spring Boot 백엔드

- [x] Spring Boot 프로젝트 생성 — `backend-spring/`(Gradle, `ai.oneground.autosns`)
- [x] MySQL 연결 — 로컬 MySQL(3306), 스키마 `auto_sns`, 계정 정보는 `application-local.yaml`
- [x] JPA 기본 설정 — `ddl-auto: update`(임시 방침)
- [x] users, projects, assets, jobs 최소 엔티티 작성
- [x] job 생성/조회 API 작성 — `POST /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs?projectId=`
  (실제 로컬 MySQL로 생성/조회/404/400 케이스까지 curl로 검증 완료, `wiki/current.md` 참고)
- [ ] users/projects/assets 생성·조회 API (아직 없음 — 로컬 검증용 시드 데이터로만 존재,
  `config/DevDataSeeder.java`, local 프로필 전용)

## 4단계: Python Worker

- [x] MySQL jobs polling worker 작성 — `backend-python/ai_sns_worker/worker.py`(PyMySQL,
  `core/db.py`/`core/config.py`), DB 접속 정보는 `backend-python/.env`
- [x] PENDING → RUNNING → DONE/FAILED 상태 흐름 구현 — 낙관적 잠금(`UPDATE ... WHERE
  status='PENDING'`)으로 동시 처리 방지, 실제 로컬 MySQL로 검증(`tests/test_worker.py`)
- [x] Python service 함수 호출 연결 — `RSS_COLLECT` → `services.rss.collect_feed_items`만
  실제로 연결(실제 네트워크+DB로 end-to-end 스모크 테스트 완료). 나머지 JobType은
  `DISPATCH`에 없어 `NotImplementedError`로 FAILED 처리됨(상태 흐름은 모든 타입에 동작)
- [x] 로그와 에러 메시지 저장 — `logging` 모듈 + `jobs.error_message` 컬럼
- [ ] 나머지 job 타입(candidate_select/deep_research/cardnews_*/reel_*/tts) 연결 —
  해당 services 파일이 실제 구현되는 대로 `DISPATCH`에 추가

## 5단계: React 프론트

- React(Vite) 프로젝트 생성
- 대시보드
- 프로젝트 상세
- job 생성/상태 조회
- 결과 파일 보기

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
