"""환경변수/설정 로딩.

워커는 단독 프로세스로 떠서 backend-python/.env(python-dotenv, Git 추적 제외)를 직접
읽는다. Spring Boot의 application-local.yaml과 마찬가지로 키/비밀번호 값은 이 파일이나
응답에 노출하지 않는다.

API 키 로딩 정책(2026-08-03, research/cardnews/image/tts 이관 대비 결정):
- OPENAI_API_KEY/ARK_API_KEY/TYPECAST_API_KEY는 DB 접속 정보와 달리 하나의 job이 모든
  키를 동시에 쓰지 않는다(예: RSS_COLLECT는 셋 다 필요 없음) — 그래서 `load_api_keys()`는
  키가 없어도 예외를 던지지 않고 `None`으로 채운 `ApiKeys`를 돌려준다.
- 실제로 특정 키가 필요한 시점(예: OpenAI 클라이언트 생성)에 그 services 함수가
  `ValueError` 등으로 예외를 던진다 — legacy `get_client()`의 `RuntimeError`와 같은 원칙,
  services 실패는 예외로 알린다는 기존 결정(`wiki/decisions.md`)을 그대로 따른다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_PATH)


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    name: str
    user: str
    password: str


def load_db_config() -> DbConfig:
    return DbConfig(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "3306")),
        name=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


@dataclass(frozen=True)
class ApiKeys:
    openai: str | None
    ark: str | None
    typecast: str | None


def load_api_keys() -> ApiKeys:
    """세 키 모두 선택 사항이다 — 없으면 None. 실제로 필요한 시점에 호출부(services 함수)가
    예외를 던지는 것을 전제로 한다(모듈 docstring 참고)."""
    return ApiKeys(
        openai=os.environ.get("OPENAI_API_KEY"),
        ark=os.environ.get("ARK_API_KEY"),
        typecast=os.environ.get("TYPECAST_API_KEY"),
    )
