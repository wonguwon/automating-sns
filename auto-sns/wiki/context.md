# Context

## 목적

`v3-semi-auto(./version/v3)`(Streamlit)에서 검증된 AI 카드뉴스/릴스 제작 로직을 React +
Spring Boot + MySQL + Python Worker 구조로 고도화 개발하기 위한 새 프로젝트.

## v3-semi-auto와의 관계

- `v3-semi-auto`는 그대로 보존한다. 이 프로젝트가 대체하지 않는다.
- `backend-python/ai_sns_worker/legacy/`에 v3에서 검증된 Python 로직 원본을
  복사해뒀다(`Generate.py`, `Render.py`, `Render_reel_narrated.py`,
  `pipeline_common.py`, `pipeline_state.py`, `sources_store.py`).
- `storage/templates/기본/`에 v3의 렌더 템플릿 세트를 복사해뒀다.
- 카드뉴스/릴스 산출물, `data/` 실행 기록, `__pycache__` 등 대용량/일회성 파일은 옮기지 않았다.

## 목표

- 카드뉴스와 릴스를 AI로 제작하는 웹 서비스
- 처음에는 가족/소수 사용자가 Mac mini에서 사용
- 추후 여러 사용자가 사용할 수 있는 서비스 구조로 확장

## 목표 스택

- Frontend: React(Vite)
- Backend: Spring Boot
- DB: MySQL + JPA
- Worker: Python Worker
- 초기 배포: Mac mini + Docker Compose
- 초기 파일 저장소: Mac mini 로컬 디스크
- 추후 확장: Redis/RabbitMQ, S3/R2, Python FastAPI

## 기존 v3에서 가져올 것

- 검증된 Python 실행 로직
- 카드뉴스/릴스 생성 흐름
- 템플릿 구조
- 시행착오 기록

## 기존 v3에서 가져오지 않을 것

- Streamlit UI
- `st.session_state` 기반 흐름
- 대용량 산출물
- 일회성 실행 데이터
