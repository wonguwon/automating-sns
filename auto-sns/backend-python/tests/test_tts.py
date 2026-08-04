"""services/tts.py 테스트.

실제 타입캐스트 API는 호출하지 않는다 — requests.get/post를 monkeypatch해서 요청 조립/저장/
에러 처리 로직만 검증한다.
"""

from types import SimpleNamespace

import pytest

from ai_sns_worker.services import pipeline, tts


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "REEL_AUDIO_DIR", tmp_path / "reel_audio")
    monkeypatch.setattr(pipeline, "PIPELINE_DIR", tmp_path / "pipeline")


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, content=b"", text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.content = content
        self.text = text

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def test_list_voices_missing_key_raises(monkeypatch):
    monkeypatch.delenv("TYPECAST_API_KEY", raising=False)
    with pytest.raises(ValueError):
        tts.list_voices()


def test_list_voices_returns_list_response(monkeypatch):
    monkeypatch.setenv("TYPECAST_API_KEY", "tc-key")
    monkeypatch.setattr(
        tts.requests, "get", lambda *a, **k: _FakeResponse(json_data=[{"voice_id": "v1"}])
    )

    result = tts.list_voices()

    assert result.voices == [{"voice_id": "v1"}]


def test_list_voices_returns_dict_wrapped_response(monkeypatch):
    monkeypatch.setenv("TYPECAST_API_KEY", "tc-key")
    monkeypatch.setattr(
        tts.requests, "get", lambda *a, **k: _FakeResponse(json_data={"voices": [{"voice_id": "v2"}]})
    )

    result = tts.list_voices()

    assert result.voices == [{"voice_id": "v2"}]


def test_synthesize_line_missing_key_raises(monkeypatch):
    monkeypatch.delenv("TYPECAST_API_KEY", raising=False)
    with pytest.raises(ValueError):
        tts.synthesize_line(tts.SynthesizeLineRequest(content_id="x", line_no=1, text="안녕"))


def test_synthesize_line_success_saves_audio(monkeypatch):
    monkeypatch.setenv("TYPECAST_API_KEY", "tc-key")
    monkeypatch.setattr(tts.requests, "post", lambda *a, **k: _FakeResponse(status_code=200, content=b"audio-bytes"))

    result = tts.synthesize_line(tts.SynthesizeLineRequest(content_id="x", line_no=3, text="안녕하세요"))

    assert result.audio_path.name == "line_03.mp3"
    assert result.audio_path.read_bytes() == b"audio-bytes"

    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id="x"))
    assert state.reel_audio_dir == str(result.audio_path.parent)


def test_synthesize_line_failure_raises_runtime_error(monkeypatch):
    monkeypatch.setenv("TYPECAST_API_KEY", "tc-key")
    monkeypatch.setattr(
        tts.requests, "post", lambda *a, **k: _FakeResponse(status_code=500, text="server error")
    )

    with pytest.raises(RuntimeError):
        tts.synthesize_line(tts.SynthesizeLineRequest(content_id="x", line_no=1, text="안녕"))
