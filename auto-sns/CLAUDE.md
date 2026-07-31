# CLAUDE.md

이 문서는 이 저장소(`auto-sns`)에서 작업할 때 따라야 할 규칙이다.

`auto-sns`는 기존 Streamlit v3 프로젝트에서 검증된 AI 카드뉴스/릴스 제작 로직을
React + Spring Boot + MySQL + Python Worker 기반 서비스 구조로 이전하기 위한 새 프로젝트다.

## 작업 시작 시 먼저 읽을 문서

작업을 시작하기 전에 아래 문서를 먼저 읽는다.

1. `wiki/context.md` — 프로젝트 목적, 현재 상태, 목표 구조
2. `wiki/current.md` — 현재 진행 중인 작업과 바로 이어갈 내용
3. `wiki/decisions.md` — 현재까지 확정된 결정
4. `wiki/roadmap.md` — 다음 단계

필요할 때만 아래 문서를 추가로 읽는다.

- `wiki/retrospective.md` — 시행착오와 방향 전환 기록
- `wiki/work-log.md` — 날짜별 작업 로그

## 사실 판단 우선순위

정보가 서로 다르거나 위키가 오래됐을 수 있다. 판단이 필요할 때는 다음 순서를 따른다.

1. 실제 실행 결과와 테스트
2. 현재 코드
3. `wiki/current.md`
4. `wiki/context.md`
5. `wiki/decisions.md`
6. `wiki/roadmap.md`
7. `wiki/retrospective.md`
8. 과거 참고자료와 기존 v3 프로젝트

위키 내용과 실제 코드/실행 결과가 다르면 코드와 실행 결과를 우선하고,
위키가 오래된 것으로 판단되면 갱신을 제안한다.

## 작업 범위

- 작업은 `auto-sns` 폴더 안에서만 한다.
- 요청 범위 밖의 대규모 리팩터링을 하지 않는다.
- 확인하지 않은 기능을 작동한다고 가정하지 않는다.
- 실행하지 않은 테스트를 통과했다고 말하지 않는다.
- API 키와 환경변수 값을 문서나 응답에 노출하지 않는다.
- 대용량 산출물, mp4, png 결과물, 실행 data는 요청 없이 복사하지 않는다.

## 아키텍처 원칙

- 기존 Python 로직은 Java로 옮기지 않는다.
- 검증된 Python 원본은 `backend-python/ai_sns_worker/legacy/`에 보존한다.
- 새 Python 호출 경계는 `backend-python/ai_sns_worker/services/`에 만든다.
- `services/` 계층은 Streamlit, Spring Boot, DB를 직접 알지 않는다.
- `services/` 함수는 입력 객체를 받고 결과 객체를 반환하는 구조로 설계한다.
- Spring Boot는 사용자, 프로젝트, 권한, 작업 상태, 파일 메타데이터, API의 중심이 된다.
- 긴 작업은 Spring Boot API 요청 안에서 직접 실행하지 않고 jobs 기반 비동기 작업으로 처리한다.
- 초기 worker는 MySQL `jobs` 테이블 polling 방식으로 계획한다.
- 추후 Redis/RabbitMQ 또는 Python FastAPI로 확장 가능하게 경계를 둔다.

## 목표 스택

- Frontend: React(Vite)
- Backend: Spring Boot
- DB: MySQL + JPA
- Worker: Python Worker
- 초기 배포: Mac mini + Docker Compose
- 초기 파일 저장소: Mac mini 로컬 디스크

## 위키 갱신 원칙

- 작업 종료 시, 장기적으로 유효한 변화가 있을 때만 위키를 갱신한다.
- 현재 진행 상태가 바뀌면 `wiki/current.md`를 갱신한다.
- 확정된 결정이 생기면 `wiki/decisions.md`를 갱신한다.
- 다음 작업 순서가 바뀌면 `wiki/roadmap.md`를 갱신한다.
- 시행착오나 방향 전환 이유가 있으면 `wiki/retrospective.md`에 남긴다.
- 일회성 디버깅 로그와 대화 전문은 위키에 저장하지 않는다.

## 작업 종료 시 보고

작업을 마칠 때 다음을 보고한다.

- 변경한 파일
- 실제 검증 결과 (무엇을 실행/테스트했는지, 하지 않았다면 그것도 명시)
- 갱신한 위키 문서와 갱신 이유
- 확인하지 못한 사항