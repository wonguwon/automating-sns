"""OpenAI 호환 API 클라이언트 생성.

core/db.py가 core/config.py의 DB 접속 정보로 실제 커넥션을 만드는 것과 같은 위치다 —
core/config.py는 키 값만 읽고, 이 모듈이 그 키로 실제 클라이언트 객체를 만든다.

services 함수 실패는 예외로 알린다는 기존 결정(wiki/decisions.md)에 따라, 키가 없으면
`ValueError`를 던진다 — legacy `get_client()`의 `RuntimeError`와 같은 원칙.
"""

from __future__ import annotations

from openai import OpenAI

from .config import load_api_keys

# Volcengine Ark(바이트댄스)는 OpenAI 호환 API를 제공하므로 openai 패키지를 그대로 쓰되
# base_url과 api_key만 바꿔서 별도 클라이언트를 만든다. legacy/Generate.py에서 그대로 옮김.
ARK_BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3"


def get_openai_client() -> OpenAI:
    keys = load_api_keys()
    if not keys.openai:
        raise ValueError("OPENAI_API_KEY가 없습니다. backend-python/.env에 OPENAI_API_KEY=sk-...를 추가하세요.")
    return OpenAI(api_key=keys.openai)


def get_ark_client() -> OpenAI:
    keys = load_api_keys()
    if not keys.ark:
        raise ValueError("ARK_API_KEY가 없습니다. backend-python/.env에 ARK_API_KEY=...를 추가하세요.")
    return OpenAI(api_key=keys.ark, base_url=ARK_BASE_URL)
