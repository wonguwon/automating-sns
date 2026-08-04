# Decisions

이 문서는 장기적으로 유지될 확정 결정만 기록한다.

## 확정된 결정

- 기존 v3 프로젝트는 수정하지 않는다.
- 새 프로젝트 폴더는 `auto-sns`다.
- auto-sns는 기존 Streamlit 도구를 서비스형 구조로 옮기기 위한 새 프로젝트다.
- 기존 Python 로직은 Java로 옮기지 않는다.
- 검증된 Python 코드는 `backend-python/ai_sns_worker/legacy/`에 보존한다.
- 새 Python 호출 경계는 `backend-python/ai_sns_worker/services/`에 만든다.
- `services/` 계층은 Streamlit, Spring Boot, DB를 직접 알지 않는다.
- `services/` 함수는 입력 객체를 받고 결과 객체를 반환하는 구조로 설계한다.
- Spring Boot는 사용자, 프로젝트, 권한, 작업 상태, 파일 메타데이터, API의 중심이 된다.
- DB는 MySQL을 사용한다.
- ORM은 JPA를 기본으로 사용한다.
- 초기 worker는 MySQL `jobs` 테이블 polling 방식으로 계획한다.
- 긴 작업은 Spring Boot API 요청 안에서 직접 실행하지 않는다.
- 초기 파일 저장소는 Mac mini 로컬 디스크를 사용한다.
- 추후 Redis/RabbitMQ 또는 Python FastAPI로 확장 가능하게 경계를 둔다.
- services 함수의 request/result DTO는 표준 라이브러리 `dataclass`를 사용한다(2026-07-31,
  RSS 기능 이관 시 결정 — 새 의존성 추가 없음).
- services 함수는 실패를 `st.error` 대신 예외(`ValueError`/`FileNotFoundError`/`IndexError`
  등)로 알린다 — worker.py가 잡아서 job 실패로 기록하는 것을 전제로 한다(2026-07-31).
- MySQL 스키마가 정해지기 전까지, 파일 기반 저장 경로는 `storage/` 아래에 기능별 하위 폴더를
  두고 `core/paths.py`에서 관리한다(예: `storage/sources/`, `storage/rss_collect/`,
  2026-07-31 — 최종 형태는 3단계 Spring Boot/MySQL 스키마 설계 때 재검토).
- Python 워커의 로컬 개발/테스트는 `backend-python/.venv` 가상환경을 사용한다(시스템/전역
  파이썬 환경을 건드리지 않기 위함, 2026-07-31). `.venv/`는 `.gitignore`에 포함했다.
- Spring Boot 프로젝트는 `backend-spring/`(Gradle, 패키지 베이스 `ai.oneground.autosns`,
  Java 17)로 생성한다(2026-07-31, 사용자가 Spring Initializr로 직접 생성 — 의존성:
  Spring Web, Spring Data JPA, MySQL Driver, Validation, Lombok).
- 로컬 개발 DB는 이 머신에 이미 떠 있는 로컬 MySQL 인스턴스(3306)를 사용하고, 스키마명은
  `auto_sns`다(2026-07-31 — Docker MySQL 등 별도 인스턴스를 쓰지 않기로 결정).
- DB 계정 정보(username/password)는 `backend-spring/src/main/resources/application-local.yaml`
  (Git 추적 제외, `local` 프로필 전용, 로컬에서 직접 생성)에만 두고 기본 `application.yaml`이나
  코드에는 넣지 않는다(2026-07-31 — 비밀번호가 대화/문서에 노출되지 않도록).
- jobs 테이블 최소 구조를 확정한다(2026-07-31, `backend-spring/.../domain/job/Job.java`):
  `id`, `project_id`(FK), `type`(enum — services/*.py 함수와 1:1 대응, `JobType.java`),
  `status`(enum: PENDING/RUNNING/DONE/FAILED), `input_json`/`result_json`(TEXT, 스키마를
  강제하지 않고 JSON 문자열 그대로 저장), `error_message`, `created_at`, `updated_at`.
- `users`/`projects`/`assets` 최소 엔티티를 확정한다: User(email, displayName) →
  Project(owner, name) → Job(project, type, status, input/result json) / Asset(project,
  job 선택적, type, filePath). Asset은 실제 파일이 아니라 `storage/`의 경로만 가리킨다.
- services 함수 실패 시 `st.error` 대신 예외를 쓰기로 한 것과 마찬가지로, Spring Boot
  쪽 최소 에러 처리는 `ResponseStatusException`으로 404/400을 내려준다(2026-07-31 — 별도
  `@ControllerAdvice`나 커스텀 예외 계층은 아직 만들지 않음, 필요해지면 추가).
- JPA `ddl-auto: update`는 초기 개발 단계 임시 방침이다(2026-07-31) — 실제 마이그레이션
  도구(Flyway 등) 도입 여부는 별도로 결정한다.
- Job 엔티티의 `input_json`/`result_json`은 `@Lob` 대신 `@Column(columnDefinition = "TEXT")`로
  명시한다(2026-07-31 — `@Lob`만 쓰면 이 Hibernate/MySQL 조합에서 `tinytext`(255바이트)로
  만들어져 결과 JSON이 조금만 커도 저장이 실패하는 걸 실제로 확인함).
- Python 워커는 PyMySQL로 MySQL에 직접 연결한다(ORM 없음, 2026-07-31) — jobs 테이블만
  다루고 users/projects/assets는 아직 건드리지 않는다. DB 접속 정보는 `backend-python/.env`
  (Git 추적 제외, python-dotenv)에 `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`로 둔다.
- 워커의 job 처리 흐름을 확정한다(2026-07-31, `backend-python/ai_sns_worker/worker.py`):
  `WHERE status='PENDING' ORDER BY created_at ASC LIMIT 1`로 하나를 집고,
  `UPDATE ... WHERE status='PENDING'`(영향받은 행 수로 낙관적 잠금)로 RUNNING 전환 —
  여러 워커가 동시에 떠도 같은 job을 두 번 처리하지 않는다. 이후 `DISPATCH` 테이블(job
  `type` 문자열 → 처리 함수)로 분기하고, 매핑이 없으면 `NotImplementedError`로 FAILED
  처리한다(상태 흐름 자체는 모든 job 타입에 대해 동작).
- 워커가 실제로 연결한 첫 job 타입은 `RSS_COLLECT`뿐이었다(`services.rss.collect_feed_items`
  호출) — 나머지 타입은 해당 services 파일이 실제 구현되고 실제 실행까지 검증된 뒤
  `DISPATCH`에 추가했다(2026-08-03, 아래 "GPT/이미지/TTS/렌더 실제 실행 검증" 항목 참고).
  `JobType.java`의 10개 값 전부가 이제 `DISPATCH`에 연결돼 있다.
- `pipeline_state.py`(단계 간 연결 매니페스트)는 `services/pipeline.py`로 이관한다(2026-08-03).
  `core/paths.py`에 `PIPELINE_DIR`(`storage/pipeline/`) 추가. `load_pipeline_state`/
  `save_pipeline_state` 두 함수로 이관했고, 부분 갱신은 `services/rss.py`의
  `UpdateFeedRequest`와 같은 패턴(요청 DTO에서 None인 필드는 기존 값 유지)을 그대로 따른다.
  legacy의 `**updates` 방식(임의 키 허용 + 런타임 검증)은 쓰지 않는다 — dataclass 필드로
  고정해 잘못된 필드명을 타입 단계에서 막는다. 아직 job 타입으로 연결하지 않았다 — 다른
  services 함수(research/cardnews/reel 등)가 실제로 이 매니페스트를 읽고 쓰게 될 때
  worker에서 호출한다.
- `core/config.py`의 API 키 로딩 정책을 확정한다(2026-08-03): `OPENAI_API_KEY`/
  `ARK_API_KEY`/`TYPECAST_API_KEY`는 `load_api_keys()`가 `ApiKeys` dataclass로 반환하되,
  DB 접속 정보(`load_db_config()`)와 달리 누락돼도 예외를 던지지 않고 `None`으로 채운다 —
  job 하나가 세 키를 동시에 다 쓰지 않기 때문(예: RSS_COLLECT는 셋 다 불필요). 실제로 특정
  키가 필요한 시점에 그 services 함수가 예외를 던지는 것을 전제로 한다(legacy `get_client()`의
  `RuntimeError`와 같은 원칙, services 실패=예외 결정을 그대로 따름). 실제 `.env` 파일은
  건드리지 않았다 — 키 이름만 코드/문서에 남기고 값은 그대로 로컬 `.env`에 둔다.
- `services/research.py`의 `get_research_note`를 먼저 이관한다(2026-08-03, GPT 호출이
  필요 없는 부분만 우선 착수). 저장된 조사 노트의 경로는 자체적으로 다시 정하지 않고
  `services/pipeline.py` 매니페스트의 `research_note_path`를 그대로 따른다(그쪽이
  canonical).
- 템플릿 세트 관리 함수는 `services/templates.py`로 이관한다(2026-08-03). `core/paths.py`에
  `TEMPLATES_DIR`(`storage/templates/`) 추가. legacy의 `list_templates`/
  `list_template_examples`/`is_valid_template_name`/`create_template`/
  `update_template_files`/`add_template_examples`/`delete_template_example`/
  `delete_template`을 그대로 옮기되, `services/rss.py`의 DTO/예외 패턴(부분 갱신은 None=유지,
  실패는 `ValueError`/`FileNotFoundError`)을 따른다. GPT/이미지 생성이 필요 없는 순수 파일
  관리 기능이라 API 키 정책과 무관하게 바로 이관했다. `tests/test_templates.py`(9개)로
  검증했고, 실제 `storage/templates/기본/`(read-only)로 `list_templates`/`get_template`
  결과가 실제 파일과 일치하는지 수동으로 재확인했다(파일 삭제/수정 없음).
- `services/cardnews.py`의 `get_content_json`을 먼저 이관한다(2026-08-03,
  services/research.py의 get_research_note와 동일한 이유·패턴). content.json 경로는
  `services/pipeline.py` 매니페스트의 `content_path`를 그대로 따른다.
- GPT/이미지/TTS/렌더 호출이 필요한 나머지 services 함수는 "코드는 지금 다 이관해두고, 실제
  실행은 방법을 안내한 뒤 사용자 확인을 받고 나서 한다"는 방침으로 진행한다(2026-08-03,
  사용자 결정). 즉 아래 함수들은 전부 실제로 이관·단위 테스트(외부 호출은 monkeypatch로
  대체)까지 완료했지만, 실제 GPT/이미지/TTS API 호출이나 Playwright/ffmpeg 실행은 **한 번도
  하지 않았다** — 실행 전 반드시 이 세션에서처럼 사용자에게 실행 방법을 안내하고 확인을 받는다.
  - `core/clients.py` 신설: `get_openai_client()`/`get_ark_client()` — `core/db.py`가
    `core/config.py`의 DB 설정으로 실제 커넥션을 만드는 것과 같은 위치(설정 로딩 vs 실제
    클라이언트 생성 분리). 키가 없으면 `ValueError`.
  - `services/research.py`: `select_candidates`(legacy: sources_store.
    select_candidates_from_items — SELECT_PERSONA_TEMPLATE/SELECT_CRITERIA_PROMPT/
    SELECT_OUTPUT_SCHEMA 프롬프트를 그대로 옮김, 결과는 `storage/candidates/<group_id>/
    <날짜>.json`에 저장), `run_deep_research`(legacy: pipeline_common.
    build_research_prompt/run_research_prompt/fetch_article_text — 노트를
    `storage/research/<content_id>.md`에 저장하고 완료 시 `services/pipeline.py`
    매니페스트에 candidate+research_note_path를 함께 기록. legacy는 "이 후보로 진행"과
    "딥리서치 실행"을 별도 화면 단계로 나눴지만 job 단위로는 하나로 묶는 게 자연스러워
    합쳤다). legacy의 `load_select_prompt_state`/`save_select_prompt_state`(마지막으로
    편집한 선별 프롬프트 기억)는 이관하지 않았다 — UI 편의 기능이라 범위 밖(아래 미확정
    목록 참고).
  - `services/cardnews.py`: `generate_content_json`(legacy: pipeline_common.
    build_content_json_prompt/run_content_json_prompt — 시스템 프롬프트는
    `services/templates.py`의 `get_template`이 돌려주는 prompt.md를 그대로 씀. **JSON
    파싱 실패 시 예외를 던지지 않고 content=None+원본 출력을 그대로 돌려준다** — legacy의
    의도적 설계를 그대로 유지했다. 모델이 스키마를 어긴 응답은 "시스템 오류"가 아니라
    사람이 원본을 보고 프롬프트를 고쳐 재시도할 대상이라는 판단), `generate_insta_caption`
    (legacy: pipeline_common.run_insta_caption — 파일 저장 없이 텍스트만 반환).
  - `services/image.py`: `generate_cover_image`/`generate_scene_image`(legacy:
    pipeline_common._generate_image_to_path 계열, Generate.py의 IMAGE_PROMPT_TEMPLATE/
    SEEDREAM_MODEL 상수). provider="openai"(GPT Image 2, 기본) 또는 "seedream"
    (Volcengine Ark, `core/clients.get_ark_client()`). **API 키 누락은 하드
    ValueError(즉시 실패)로 두되, 실제 이미지 생성 API 호출 자체가 실패하면(네트워크/응답
    형식 등) 예외 대신 `image_uri=None`+`error` 메시지를 결과에 담아 돌려준다** — legacy가
    "표지 이미지 실패 시 단색 폴백으로 계속 진행"하도록 설계한 것을 그대로 유지(전체
    파이프라인을 막지 않기 위함).
  - `services/reel.py`: `generate_reel_script`(legacy: pipeline_common.
    build_reel_script_prompt/run_reel_script_prompt/REEL_SCRIPT_SYSTEM_PROMPT — 대본
    JSON 파싱 실패 시 cardnews.generate_content_json과 동일하게 예외 대신 None 반환).
    릴스 사진 라이브러리(assets/reel_photos/+index.json 관리, legacy: load_reel_photo_index/
    add_reel_photo/delete_reel_photo)는 이관하지 않았다 — `photo_library`는 호출부가
    직접 넘기는 인자로만 받는다(파일로 관리하는 라이브러리 자체는 별도 관심사).
  - `services/tts.py`: `list_voices`/`synthesize_line`(legacy: pipeline_common.
    list_typecast_voices/synthesize_reel_line). **legacy는 TTS 실패를 소프트 실패(화면
    에러+False/None 반환)로 다뤘지만 여기서는 하드 예외로 바꿨다** — 표지 이미지와 달리
    TTS 오디오가 없으면 릴스 조립(render_reel)이 어차피 이어질 수 없어 소프트 실패가
    도움이 되지 않기 때문. 성공 시 `services/pipeline.py` 매니페스트에 reel_audio_dir을
    기록한다.
  - `services/render.py`: `render_cardnews`(legacy: Render.render — Playwright/chromium
    으로 4:5 캐러셀+9:16 스토리 PNG 스크린샷, 스키마 위반·텍스트 넘침은 그 자리에서
    RuntimeError), `render_reel`(legacy: Render_reel_narrated.build_reel — ffmpeg
    zoompan/drawtext/concat으로 mp4 조립, 보조 함수 전부 포함). `render_reel`은 대본의
    각 장면에 `resolved_image_path`가 이미 채워져 있다고 가정한다 — legacy도 이 필드를
    "장면 이미지 준비"라는 UI 단계에서만 채웠고 대응하는 서비스 함수가 없었다. 이 공백은
    `services/reel.py`의 `set_scene_resolved_image(content_id, scene_index, image_path)`로
    메웠다(2026-08-03) — `services/pipeline.py` 매니페스트의 `reel_script_path`가 가리키는
    대본 JSON을 읽어 `scenes[scene_index].resolved_image_path`를 채우고 같은 경로에 다시
    저장한다. 대본 없음은 `FileNotFoundError`, 잘못된 scene_index는 `IndexError`
    (services/rss.py의 `update_feed`와 같은 패턴).
  - `core/paths.py`에 `CAND_DIR`/`RESEARCH_DIR`/`CONTENT_DIR`/`ASSETS_DIR`/
    `REEL_SCRIPT_DIR`/`REEL_IMAGES_DIR`/`REEL_AUDIO_DIR`/`OUTPUTS_DIR`/
    `CARDNEWS_OUTPUT_DIR`/`REEL_OUTPUT_DIR` 추가 — 기존 SOURCES_DIR/RSS_COLLECT_DIR/
    PIPELINE_DIR/TEMPLATES_DIR과 같은 flat 레이아웃.
  - 이 작업을 위해 `backend-python/.venv`에 `openai`/`requests`/`beautifulsoup4`/
    `playwright` 패키지를 설치했다(2026-08-03, 사용자 확인 후 — `requirements.txt`에는
    이미 적혀 있었으나 `.venv`에는 없었다).
- 실행 전제조건을 확인하고 준비했다(2026-08-03): `.env`에 `OPENAI_API_KEY`/
  `TYPECAST_API_KEY`는 있고 `ARK_API_KEY`는 없음(사용자가 직접 `.env`에 추가하기로 함 —
  그때까지 `image.py`의 `provider="seedream"` 경로는 실제로 검증되지 않은 채로 남는다.
  기본값은 이미 `provider="openai"`라 당장 막히지는 않는다). ffmpeg/ffprobe는 PATH에
  있었다(Chocolatey). 폰트 파일 `Pretendard-Black.otf`는 `v3-semi-auto/assets/fonts/`에서
  `storage/assets/fonts/`로 복사했다(v3 원본은 그대로 둠).
  **정정**: Playwright 브라우저는 로컬 캐시에 "이미 설치돼 있다"고 처음 확인했으나 실제로는
  다른 버전(revision 1228, 다른 도구가 설치한 것)이었고, 이 프로젝트가 방금 설치한
  `playwright==1.62.0`이 요구하는 revision 1234는 없었다 — 실제로 `render_cardnews`를
  실행해보고 나서야 드러난 실수다. `playwright install chromium`으로 다시 설치해 해결했다
  (사용자 확인 후 진행, Microsoft CDN에서 다운로드). 캐시 폴더가 있다고 해서 이 프로젝트
  venv의 Playwright가 실제로 쓸 수 있는 버전이라고 가정하면 안 된다는 교훈.
- **GPT/이미지/TTS/렌더 실제 실행 검증 완료(2026-08-03)** — 사용자 승인 하에 카드뉴스
  경로와 릴스 경로를 각각 실제로 끝까지 돌려봤다(테스트 content_id: `smoketest-cardnews-01`):
  - 카드뉴스 경로: `select_candidates`(진짜 GPT 호출, 후보 2개) → `run_deep_research`
    (진짜 GPT 호출 + 원문 fetch) → `generate_content_json`(진짜 GPT 호출, 파싱 성공) →
    `generate_cover_image`(진짜 OpenAI 이미지 생성 API 호출, provider="openai") →
    `render_cardnews`(진짜 Playwright, PNG 6장×2세트).
  - 릴스 경로: `generate_reel_script`(진짜 GPT 호출, 장면 3개·대사 9줄) →
    `generate_scene_image`×3(진짜 이미지 생성) → `synthesize_line`×9(진짜 Typecast TTS,
    기본 음성 `tc_68f0727fd62a5934102f7ec0`/Minuk 실존 확인) → `render_reel`(진짜 ffmpeg,
    17.75초 mp4 완성).
  - 이 과정에서 실제 통합 공백 하나를 더 발견·수정했다: `generate_cover_image`가 만든
    이미지가 저장된 `content.json`의 `cover.image`에 반영되지 않아 `render_cardnews`가
    이미지 없이(단색 폴백) 렌더됐다 — legacy도 이 연결은 UI 단계에서만 했고 대응 서비스
    함수가 없었다. `services/cardnews.py`에 `set_cover_image(content_id, image_uri)`를
    추가해 메웠다(services/reel.py의 `set_scene_resolved_image`와 같은 역할·패턴).
  - `backend-python/ai_sns_worker/worker.py`의 `DISPATCH`에 `JobType.java`의 나머지 9개
    타입을 전부 연결했다: `CANDIDATE_SELECT`/`DEEP_RESEARCH`/`CARDNEWS_GENERATE`/
    `COVER_IMAGE_GENERATE`/`CARDNEWS_RENDER`/`REEL_SCRIPT_GENERATE`/`SCENE_IMAGE_GENERATE`/
    `TTS_SYNTHESIZE`/`REEL_RENDER`. `COVER_IMAGE_GENERATE`/`SCENE_IMAGE_GENERATE`의 dispatch
    함수는 이미지 생성 직후 `set_cover_image`/`set_scene_resolved_image`를 자동으로 호출해
    연결한다 — job을 만드는 쪽이 이 연결 단계를 몰라도 되게 하기 위함.
  - 단위 테스트(monkeypatch로 외부 호출 대체) 12개를 `tests/test_worker.py`에 추가했고,
    `jobs.type` 컬럼이 실제로는 `VARCHAR`가 아니라 `JobType.java` 값만 허용하는 SQL
    `ENUM`이라는 것도 이 과정에서 확인했다(임의 문자열 삽입 시 `Data truncated` 오류) —
    "연결 안 된 타입" 테스트는 DB 통합 테스트 대신 `DISPATCH` 키 목록 대조로 바꿨다.
  - 추가로 실제 로컬 MySQL에 `CARDNEWS_RENDER` job 행을 직접 넣고 `worker.poll_once()`가
    이를 집어 `DONE`으로 완료 처리하는 것까지 1회 확인했다(테스트 스위트에는 포함하지
    않음 — RSS_COLLECT 스모크 테스트와 같은 성격의 수동 확인, 끝난 뒤 해당 job/project/
    user 행은 정리함).
  - 전체 테스트 스위트는 98개 전부 통과.
  - 스모크 테스트로 생성된 실제 파일들(`storage/candidates/smoketest-group/`,
    `storage/research/smoketest-cardnews-01.md`, `storage/content/
    smoketest-cardnews-01.json`, `storage/assets/cover-smoketest-cardnews-01.png`,
    `storage/outputs/cardnews/smoketest-cardnews-01/`, `storage/reel_script/
    smoketest-cardnews-01.json`, `storage/reel_images/smoketest-cardnews-01/`,
    `storage/reel_audio/smoketest-cardnews-01/`, `storage/outputs/reel/
    smoketest-cardnews-01.mp4`)은 정리하지 않고 그대로 남겨뒀다 — git에는 아직 커밋되지
    않은 untracked 파일이다(`storage/`는 현재 `.gitignore`에 없음). 이 산출물들을 계속
    보존할지, `storage/`의 런타임 산출 하위 폴더들을 `.gitignore`에 추가할지는 사용자
    판단이 필요하다.
  - `provider="seedream"`(Volcengine Ark) 경로는 `ARK_API_KEY`가 없어 이번 실행 검증에
    포함되지 않았다 — 여전히 미검증 상태.

- `storage/`의 런타임 산출 하위 폴더는 `.gitignore`에 추가한다(2026-08-03): `candidates/`,
  `content/`, `pipeline/`, `reel_audio/`, `reel_images/`, `reel_script/`, `research/`,
  `outputs/cardnews/`, `outputs/reel/`, `assets/cover-*.png`. `storage/templates/`(v3에서
  옮긴 렌더 템플릿 세트)와 `storage/assets/fonts/`(v3에서 옮긴 폰트 파일)는 소스 자료로
  보고 추적 대상에서 제외하지 않는다(둘 다 실행 산출물이 아니라 사람이 준비해 옮긴
  자료라는 점에서 같은 성격). 기존 스모크 테스트 산출물은 삭제하지 않고 그대로 두되,
  이제 untracked 상태로 git 추적에서 빠진다. `storage/assets/fonts/`는 아직 커밋되지
  않았다(이번 작업은 `.gitignore` 정리만 포함, 커밋은 요청 시 별도 진행).

- users/projects 생성·조회 API를 `job` 패키지와 같은 패턴으로 확정한다(2026-08-03,
  `backend-spring/.../user/`, `.../project/`): `UserController`/`UserService`,
  `ProjectController`/`ProjectService`, DTO는 `record` + `@NotBlank`/`@NotNull`/`@Email`
  (`CreateUserRequest`/`UserResponse`, `CreateProjectRequest`/`ProjectResponse`). 엔드포인트:
  `POST /api/users`, `GET /api/users/{id}`, `POST /api/projects`(존재하지 않는 `ownerId`는
  404), `GET /api/projects/{id}`, `GET /api/projects?ownerId=`. 실패 처리는 job API와 같은
  `ResponseStatusException`(404/400) 방침을 그대로 따른다 — 별도 예외 계층 없음.
  `ProjectRepository`에 `findByOwnerIdOrderByCreatedAtDesc` 추가(JobRepository의
  `findByProjectIdOrderByCreatedAtDesc`와 같은 패턴). 로컬 MySQL로 생성(201)/단건 조회(200)/
  목록 조회(200)/존재하지 않는 user·project(404)/유효성 검증 실패(400, 이메일 누락)까지
  curl로 확인했고, 새 project로 job 생성(`POST /api/jobs`)도 회귀 없이 되는 것까지 확인했다
  (검증에 쓴 테스트 user/project/job 행은 확인 후 정리함). `config/DevDataSeeder.java`는
  실제 생성 API가 생겼으므로 삭제했다(2026-08-03) — 로컬 curl 테스트는 이제 `POST
  /api/users` → `POST /api/projects` → `POST /api/jobs` 순서로 직접 만들어 진행한다.
  assets 생성·조회 API는 이번 범위에 포함하지 않았다(엔티티/Repository만 존재, 아직 필요
  시점이 아니라 판단).

- React 프론트 프로젝트를 확정한다(2026-08-03, 사용자 결정): 폴더 `frontend/`, Vite +
  React 19 + TypeScript, 패키지 매니저는 `npm`(로컬에 pnpm/yarn 없음), 라우팅은
  `react-router-dom`. 이번 작업 범위는 "프로젝트 뼈대만 먼저"(사용자 선택) —
  대시보드/프로젝트 상세 화면과 백엔드 API 연결 확인까지만 하고, 나머지 화면은 다음
  세션에서 화면 단위로 순차 진행한다.
  - `react-router-dom` 최신(7.18.2)에는 `npm audit`이 "RSC Mode CSRF Bypass"(GHSA-qwww-
    vcr4-c8h2) 취약점을 표시하지만, 이 프로젝트는 RSC를 쓰지 않는 순수 클라이언트
    SPA(Vite, `BrowserRouter`)라 해당 없음. `npm audit fix --force`가 제안하는 7.11.0으로
    내리면 오히려 SPA에도 적용되는 오픈 리다이렉트/XSS 등 14개 취약점 범위에 들어가
    최신 버전(7.18.2)을 그대로 유지하기로 결정했다.
  - Vite dev 서버는 `vite.config.ts`의 `server.proxy`로 `/api` 요청을 `http://localhost:8080`
    (Spring Boot)으로 프록시한다 — 백엔드에 별도 CORS 설정을 추가하지 않기 위한 선택
    (로컬 개발 전용 방편, 배포 시 재검토 필요).
  - `src/api/client.ts`(fetch 래퍼) + `src/api/types.ts`(백엔드 DTO와 대응하는 TS 타입,
    `JobType`/`JobStatus`는 `JobType.java`/`JobStatus.java`와 수동으로 값 맞춤 — 코드
    생성기는 아직 도입하지 않음)로 백엔드 연결 경계를 둔다.
  - `DashboardPage`(ownerId로 프로젝트 목록 조회·생성)와 `ProjectDetailPage`(프로젝트
    정보, job 생성 폼, job 목록)를 구현했다. "전체 프로젝트 목록"·인증 개념이 아직 없어
    ownerId를 직접 입력받는 임시 방편이다 — 인증/세션이 생기면 재검토 대상.
  - 실제 로컬 MySQL(스키마 `auto_sns`)에 연결한 Spring Boot(`local` 프로필) + Vite dev
    서버를 함께 띄우고 Playwright로 브라우저에서 검증했다: 대시보드에서 기존 시드 프로젝트
    (`Dev Project`, id 1, DevDataSeeder가 살아있던 이전 세션에 생성된 실데이터) 목록 조회
    성공 → 상세 페이지 이동 → job 생성(`RSS_COLLECT`) → 목록에 `PENDING` 상태로 즉시 반영
    확인. 콘솔 에러/경고 없음. 검증에 쓴 테스트 job 행(id 19)은 확인 후 정리함(기존 시드
    프로젝트/유저는 그대로 둠 — 이번 세션이 만든 게 아니라 삭제하지 않음).
  - `frontend/`의 `dist/`, `node_modules/`는 Vite 스캐폴드가 만든 `frontend/.gitignore`가
    이미 추적 제외한다.

## 아직 확정되지 않은 것 (여기 적지 않음)

- assets에 대한 생성·조회 API 설계(users/projects/jobs는 확정됨, `config/DevDataSeeder.java`는
  삭제함 — 위 "users/projects 생성·조회 API" 항목 참고)
- React 화면 구성
- core/storage.py의 실제 정책(로컬 디스크 직접 쓰기 유지 vs 교체 가능한 인터페이스로 감싸기)
- RSS 그룹 생성 시 GPT 피드 후보 제안(legacy: generate_feeds_from_prompt) 이관 여부 — 아직
  이관하지 않음(코드/테스트까지 끝낸 다른 GPT 함수들과 달리 이 항목은 손대지 않았다)
- select_prompt_state(마지막 편집한 선별 프롬프트 기억)와 릴스 사진 라이브러리(reel_photos
  index.json 관리)는 이관 범위에서 의도적으로 제외했다 — 필요해지면 어느 services 파일에
  둘지 결정
- `provider="seedream"`(Volcengine Ark) 이미지 생성 경로는 `ARK_API_KEY`가 없어 실제
  실행 검증을 하지 못했다 — 사용자가 키를 추가하면 검증
- `storage/`의 런타임 산출 하위 폴더(candidates/content/research/reel_*/outputs 등)를
  `.gitignore`에 추가할지 — 현재는 추적 대상이라 스모크 테스트 산출물이 untracked 상태로
  쌓여 있다
- 실제 마이그레이션 도구(Flyway/Liquibase) 도입 여부
- Mac mini 배포 시 MySQL 인스턴스는 이 로컬 개발 인스턴스와 별개로 준비해야 한다는 점만
  분명함 — 배포용 스키마 초기화 방식은 7단계에서 결정

이 항목들은 결정되는 즉시 위 "확정된 결정" 목록에 추가한다.
