# auto-sns

Streamlit v3(`v3-semi-auto`)에서 검증된 AI 카드뉴스/릴스 제작 로직을 서비스형
구조(React + Spring Boot + MySQL + Python Worker)로 옮기기 위한 새 프로젝트다.

## 현재 단계

- `v3-semi-auto`는 그대로 보존한다 — 수정하지 않는다.
- 이 프로젝트는 아직 구조만 갖췄다. Spring Boot/React/MySQL은 아직 없다.
- `backend-python/ai_sns_worker/legacy/`에 v3에서 검증된 원본 Python 로직을
  그대로 복사해뒀다 — 참고/재사용 원본이며 리팩토링 대상이 아니다.
- `backend-python/ai_sns_worker/services/`는 legacy 로직을 옮겨 담을 자리다.
  지금은 함수 골격과 TODO만 있고 실제 구현은 없다.
- `storage/`에는 렌더링에 필요한 템플릿(`templates/기본/`)만 옮겨왔다. 카드뉴스/릴스
  결과물, `data/` 실행 기록 등 대용량 산출물은 옮기지 않았다.

자세한 결정 사항은 [wiki/decisions.md](wiki/decisions.md) 참조.
