"""core/config.py의 API 키 로딩 정책 테스트.

실제 backend-python/.env는 건드리지 않는다 — monkeypatch로 환경변수만 격리해서 검사한다.
"""

from ai_sns_worker.core import config


def test_load_api_keys_defaults_to_none_when_unset(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.delenv("TYPECAST_API_KEY", raising=False)

    keys = config.load_api_keys()

    assert keys.openai is None
    assert keys.ark is None
    assert keys.typecast is None


def test_load_api_keys_reads_present_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.setenv("TYPECAST_API_KEY", "tc-test")

    keys = config.load_api_keys()

    assert keys.openai == "sk-test"
    assert keys.ark is None
    assert keys.typecast == "tc-test"
