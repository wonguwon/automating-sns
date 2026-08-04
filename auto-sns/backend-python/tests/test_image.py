"""services/image.py 테스트.

실제 이미지 생성 API는 호출하지 않는다 — get_openai_client/get_ark_client를 가짜 클라이언트로
monkeypatch해서 프롬프트 조립/저장/에러 처리 로직만 검증한다.
"""

import base64
from types import SimpleNamespace

import pytest

from ai_sns_worker.services import image, pipeline


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "PIPELINE_DIR", tmp_path / "pipeline")
    monkeypatch.setattr(image, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(image, "REEL_IMAGES_DIR", tmp_path / "reel_images")


def _fake_image_client(b64_data: bytes | None = None, url: str | None = None, raise_exc: Exception | None = None):
    def generate(**kwargs):
        if raise_exc is not None:
            raise raise_exc
        item = SimpleNamespace(
            url=url, b64_json=base64.b64encode(b64_data).decode("ascii") if b64_data is not None else None
        )
        return SimpleNamespace(data=[item])

    return SimpleNamespace(images=SimpleNamespace(generate=generate))


def test_build_cover_image_prompt_includes_concept_and_extra_direction():
    prompt = image.build_cover_image_prompt("눈 내리는 광화문", "인물 없이")
    assert "눈 내리는 광화문" in prompt
    assert "추가 지시: 인물 없이" in prompt


def test_build_scene_image_prompt_includes_concept():
    prompt = image.build_scene_image_prompt("국회의사당 전경")
    assert "국회의사당 전경" in prompt


def test_generate_cover_image_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        image.generate_cover_image(image.GenerateCoverImageRequest(content_id="x", concept="개념"))


def test_generate_cover_image_success_saves_and_updates_pipeline_state(monkeypatch):
    monkeypatch.setattr(image, "get_openai_client", lambda: _fake_image_client(b64_data=b"fake-png-bytes"))

    result = image.generate_cover_image(image.GenerateCoverImageRequest(content_id="x", concept="개념"))

    assert result.error is None
    assert result.image_path.exists()
    assert result.image_path.read_bytes() == b"fake-png-bytes"
    assert result.image_uri.startswith("file:")

    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id="x"))
    assert state.cover_image_path == str(result.image_path)


def test_generate_cover_image_api_failure_returns_error_without_raising(monkeypatch):
    monkeypatch.setattr(image, "get_openai_client", lambda: _fake_image_client(raise_exc=RuntimeError("boom")))

    result = image.generate_cover_image(image.GenerateCoverImageRequest(content_id="x", concept="개념"))

    assert result.image_path is None
    assert result.image_uri is None
    assert "boom" in result.error


def test_generate_cover_image_seedream_uses_ark_client(monkeypatch):
    called = {}

    def fake_ark_client():
        called["used"] = True
        return _fake_image_client(b64_data=b"seedream-bytes")

    monkeypatch.setattr(image, "get_ark_client", fake_ark_client)

    result = image.generate_cover_image(
        image.GenerateCoverImageRequest(content_id="x", concept="개념", provider="seedream")
    )

    assert called.get("used") is True
    assert result.image_path.read_bytes() == b"seedream-bytes"


def test_generate_scene_image_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        image.generate_scene_image(
            image.GenerateSceneImageRequest(content_id="x", scene_index=0, concept="장면")
        )


def test_generate_scene_image_success_saves_to_scene_path(monkeypatch):
    monkeypatch.setattr(image, "get_openai_client", lambda: _fake_image_client(b64_data=b"scene-bytes"))

    result = image.generate_scene_image(
        image.GenerateSceneImageRequest(content_id="x", scene_index=2, concept="장면")
    )

    assert result.error is None
    assert result.image_path.name == "scene_02.png"
    assert result.image_path.read_bytes() == b"scene-bytes"

    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id="x"))
    assert state.reel_images_dir == str(result.image_path.parent)
