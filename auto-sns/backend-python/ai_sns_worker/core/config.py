"""환경변수/설정 로딩.

DB 접속 정보만 우선 다룬다(2026-07-31, 4단계 워커 polling 연결 시 결정) — 워커는 단독
프로세스로 떠서 backend-python/.env(python-dotenv, Git 추적 제외)를 직접 읽는다.
Spring Boot의 application-local.yaml과 마찬가지로 DB_USER/DB_PASSWORD 값은 이 파일이나
응답에 노출하지 않는다.

TODO: OPENAI_API_KEY, ARK_API_KEY, TYPECAST_API_KEY 로딩은 여전히 미정 — 해당 services
파일(research/image/tts 등)을 실제로 이관할 때 이 모듈에 추가한다.
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
