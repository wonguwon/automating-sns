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
- 워커가 실제로 연결한 첫 job 타입은 `RSS_COLLECT`뿐이다(`services.rss.collect_feed_items`
  호출) — 나머지 타입은 해당 services 파일이 실제 구현되는 대로 `DISPATCH`에 추가한다.

## 아직 확정되지 않은 것 (여기 적지 않음)

- users/projects/assets에 대한 생성·수정 API 설계(Job 생성/조회 API만 확정됨) — 로컬 개발
  편의를 위한 `config/DevDataSeeder.java`(local 프로필 전용)로 임시 대체 중
- React 화면 구성
- core/config.py의 실제 정책(DB 설정은 확정, OpenAI/ARK/Typecast API 키 로딩 방식은 미정)
- core/storage.py의 실제 정책(로컬 디스크 직접 쓰기 유지 vs 교체 가능한 인터페이스로 감싸기)
- 템플릿(html/prompt/예시 이미지) 관리 로직을 어느 services 파일에 둘지
- RSS 그룹 생성 시 GPT 피드 후보 제안(legacy: generate_feeds_from_prompt) 이관 여부 —
  core/config.py의 API 키 정책이 정해진 뒤 판단
- 실제 마이그레이션 도구(Flyway/Liquibase) 도입 여부
- Mac mini 배포 시 MySQL 인스턴스는 이 로컬 개발 인스턴스와 별개로 준비해야 한다는 점만
  분명함 — 배포용 스키마 초기화 방식은 7단계에서 결정

이 항목들은 결정되는 즉시 위 "확정된 결정" 목록에 추가한다.
