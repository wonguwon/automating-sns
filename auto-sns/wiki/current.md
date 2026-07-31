# Current

## 현재 초점

기존 Streamlit v3 프로젝트에서 검증된 Python 로직을 auto-sns의 새 구조로 보존하고, 이후 서비스형 구조로 옮기기 위한 초기 정리 단계다.

## 진행 중인 작업(2026-07-31)

- React 코드는 아직 없다.
- 4단계(Python Worker) 착수 — `backend-python/ai_sns_worker/worker.py`가 PyMySQL로
  `auto_sns.jobs` 테이블을 polling한다: `PENDING`(오래된 순) 하나를 집어 `RUNNING`으로
  낙관적 잠금 전환 → `DISPATCH` 테이블로 job `type`별 처리 함수 호출 → 성공하면
  `DONE`+`result_json`, 실패(연결 안 된 타입 포함)하면 `FAILED`+`error_message`.
  `RSS_COLLECT`만 `services.rss.collect_feed_items`에 실제로 연결했고, 실제 로컬 MySQL +
  실제 RSS 네트워크로 end-to-end 확인(수동 스모크 테스트, item_count 32건 수집·정리 완료).
  DB 접속 정보는 `backend-python/.env`(Git 추적 제외)에서 읽는다.
- 이 과정에서 버그를 하나 발견·수정했다: Spring Boot의 `Job.inputJson`/`resultJson`이
  `@Lob`만 쓴 탓에 MySQL에서 `tinytext`(255바이트)로 생성돼 있었다 — `columnDefinition =
  "TEXT"`로 명시하도록 고치고, 기존 컬럼도 `ALTER TABLE`로 넓혔다(운영 데이터 없는 시점이라
  안전하게 처리).
- 3단계(Spring Boot 백엔드) 완료 — `backend-spring/`(Gradle, 패키지 `ai.oneground.autosns`,
  Java 17, Spring Boot 4.0.7)는 사용자가 Spring Initializr로 직접 생성했다. 그 위에
  User/Project/Asset/Job 최소 엔티티+Repository, `POST/GET /api/jobs` API를 구현했다.
  로컬 MySQL(3306, 스키마 `auto_sns`)에 실제로 연결해 curl로 생성(201)/단건 조회(200)/
  프로젝트별 목록(200)/존재하지 않는 job(404)/존재하지 않는 project(404)/유효성 검증
  실패(400)까지 확인했다. DB 계정 정보는 `application-local.yaml`(Git 추적 제외, local
  프로필)에만 있고 이 세션 대화에는 노출되지 않았다.
- User/Project 생성 API가 아직 없어서, Job API 검증용으로 `config/DevDataSeeder.java`
  (local 프로필 전용, 테이블이 비어 있을 때만 1건 생성)를 추가해뒀다 — 실제 API가 생기면
  이 시더는 정리 대상.
- 2단계(Python 로직 분리) 착수 — `services/rss.py`(RSS 소스 그룹 관리·수집)를 첫 실제
  구현 대상으로 완료했다: `list_feed_groups`, `create_feed_group`(GPT 피드 제안 제외 —
  [decisions.md](decisions.md) 참고), `add_feed`, `update_feed`(부분 수정), `remove_feed`,
  `health_check_group`, `collect_feed_items`. 나머지 services 파일(cardnews/image/reel/
  render/research/tts)은 여전히 함수 골격 + TODO 상태다.
- `core/paths.py`에 `SOURCES_DIR`/`RSS_COLLECT_DIR`(둘 다 `storage/` 하위) 상수 추가.
  `core/config.py`, `core/storage.py`는 아직 TODO 상태 유지.
- legacy 코드의 절대 import 문제는 services/rss.py를 새로 작성(legacy 파일 직접 import
  안 함)하는 방식으로 자연히 우회했다 — 다른 legacy 파일들도 이 방식을 따를 것으로 예상.
- 테스트 인프라 신설: `backend-python/.venv`(로컬 전용 가상환경, 시스템 파이썬 미사용),
  `backend-python/pytest.ini`, `backend-python/tests/test_rss.py`(그룹 CRUD 6개 테스트,
  전부 통과 확인). `health_check_group`/`collect_feed_items`는 실제 네트워크(BBC RSS)로
  수동 스모크 테스트까지 확인했고, 임시 스크립트/데이터는 정리했다(repo `storage/`는
  건드리지 않음).
- `pipeline_state.py`(파이프라인 매니페스트 load_state/save_state)와 템플릿 세트 관리
  함수는 아직 어느 services 파일에도 매핑하지 않은 채로 남아 있다(발견만 해둠).

## 다음 작업

1. 나머지 services 파일(research/cardnews/image/reel/render/tts) 실제 로직 이관 — 하나씩
   끝날 때마다 `worker.py`의 `DISPATCH`에 해당 JobType을 연결 (Streamlit 의존 부분은
   pipeline_common.py에서만 발견됨 — `get_client`/`content_id_widget`/`show_*_dialog`/
   각 함수 내 `st.error` 호출)
2. `core/config.py` API 키 로딩 정책 결정 (OpenAI/ARK/Typecast 키 — RSS의 GPT 피드 제안,
   딥리서치, 이미지·TTS 이관에 공통으로 필요)
3. `pipeline_state.py`, 템플릿 세트 관리 함수의 services 이관 위치 결정
4. users/projects 생성 API(간단하게라도) 추가하고 `DevDataSeeder` 정리 여부 판단
5. 5단계(React 프론트) 착수

자세한 순서는 [roadmap.md](roadmap.md) 참조.

## 주의사항

- 기존 v3 프로젝트는 수정하지 않는다.
- auto-sns 폴더 안에서만 작업한다.
- 아직 React 구현은 시작하지 않는다.
- 대용량 산출물, mp4, png 결과물, data 실행 결과는 복사하지 않는다.
- DB 계정 정보(`application-local.yaml`, `backend-python/.env`)는 Git에 올리지 않고
  대화에도 노출하지 않는다.