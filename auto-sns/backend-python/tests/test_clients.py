"""core/clients.py의 클라이언트 생성 테스트 — 실제 네트워크 호출 없이 키 유무만 확인한다."""

import pytest

from ai_sns_worker.core import clients


def test_get_openai_client_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        clients.get_openai_client()


def test_get_openai_client_builds_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = clients.get_openai_client()
    assert client.api_key == "sk-test"


def test_get_ark_client_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    with pytest.raises(ValueError):
        clients.get_ark_client()


def test_get_ark_client_builds_with_key_and_base_url(monkeypatch):
    monkeypatch.setenv("ARK_API_KEY", "ark-test")
    client = clients.get_ark_client()
    assert client.api_key == "ark-test"
    assert str(client.base_url).startswith(clients.ARK_BASE_URL)
