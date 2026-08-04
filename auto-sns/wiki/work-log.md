# Work Log

날짜별 작업 내역을 짧게 기록한다.

## 2026-07-31

- auto-sns 프로젝트 방향 결정
- 목표 스택 결정: React(Vite), Spring Boot, MySQL/JPA, Python Worker
- 기존 Python 로직은 Java로 옮기지 않고 legacy/services 구조로 분리하기로 결정
- 초기 worker는 MySQL jobs polling 방식으로 시작하기로 결정

## 2026-08-03

- `services/pipeline.py`(파이프라인 매니페스트), `core/config.py`(API 키 로딩 정책),
  `services/templates.py`(템플릿 세트 관리), `services/research.py`의 `get_research_note`,
  `services/cardnews.py`의 `get_content_json`을 순서대로 이관·검증
- 사용자 지시("다 해두고 나중에 실행방법 알려주면 사용자확인하는 식으로")에 따라 나머지
  GPT/이미지/TTS/렌더 services 함수를 전부 코드로 이관: `research.select_candidates/
  run_deep_research`, `cardnews.generate_content_json/generate_insta_caption`,
  `image.generate_cover_image/generate_scene_image`, `reel.generate_reel_script`,
  `tts.list_voices/synthesize_line`, `render.render_cardnews/render_reel`
- `core/clients.py` 신설(OpenAI/Ark 클라이언트 생성)
- 이 과정에서 `backend-python/.venv`에 openai/requests/beautifulsoup4/playwright 미설치
  상태를 발견해 사용자 확인 후 설치(requirements.txt에는 이미 있던 패키지)
- 83개 테스트 전부 통과(외부 API 호출/Playwright/ffmpeg는 전부 monkeypatch로 대체 — 실제
  실행은 아직 한 번도 하지 않음)
- `JobType.java`와 새 services 함수 이름이 1:1로 대응하는지 확인(불일치 없음), `DISPATCH`
  연결은 실제 실행 검증 전이라 보류
- 이어서 실행 전제조건 확인 → 폰트 파일 복사 → `reel.set_scene_resolved_image` 추가(릴스
  이미지→대본 연결 공백) → 사용자 승인 하에 카드뉴스·릴스 경로 전체를 실제로 실행 검증
  (진짜 GPT/이미지/TTS API 호출, 진짜 Playwright/ffmpeg 실행 — smoketest-cardnews-01)
- 실행 중 두 가지를 발견·수정: (1) Playwright 브라우저 캐시가 있어도 이 venv의 버전과
  안 맞으면 무용지물 — `playwright install chromium`으로 재설치, (2) 표지 이미지가
  content.json에 반영 안 되는 공백 — `cardnews.set_cover_image` 추가
- `worker.py`의 `DISPATCH`에 `JobType.java`의 나머지 9개 타입 전부 연결, 실제 MySQL job
  1건으로 전체 흐름(등록 → poll → DONE)도 확인. 전체 테스트 98개 통과
- 2단계·4단계를 사실상 완료 상태로 표시(남은 건 seedream 이미지 provider 검증과
  users/projects API, React뿐)