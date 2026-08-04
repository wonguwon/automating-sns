"""services/cardnews.py 테스트.

generate_content_json/generate_insta_caption은 실제로는 GPT 호출(비용 발생)이 필요하다 —
여기서는 get_openai_client를 가짜 클라이언트로 monkeypatch해서 프롬프트 조립/파싱/저장
로직만 검증한다. 실제 OpenAI API는 호출하지 않는다.
"""

from types import SimpleNamespace

import pytest

from ai_sns_worker.services import cardnews, pipeline, templates


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """PIPELINE_DIR/TEMPLATES_DIR/CONTENT_DIR을 tmp_path 아래로 바꿔 실제 storage/를 건드리지 않는다."""
    monkeypatch.setattr(pipeline, "PIPELINE_DIR", tmp_path / "pipeline")
    monkeypatch.setattr(templates, "TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr(cardnews, "CONTENT_DIR", tmp_path / "content")


def _fake_openai_client(content: str):
    def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_get_content_json_missing_state_raises():
    with pytest.raises(FileNotFoundError):
        cardnews.get_content_json(cardnews.GetContentJsonRequest(content_id="없는id"))


def test_get_content_json_state_without_path_raises():
    pipeline.save_pipeline_state(pipeline.SavePipelineStateRequest(content_id="x", candidate={"id": "x"}))
    with pytest.raises(FileNotFoundError):
        cardnews.get_content_json(cardnews.GetContentJsonRequest(content_id="x"))


def test_get_content_json_missing_file_raises(tmp_path):
    content_path = tmp_path / "content" / "x.json"
    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id="x", content_path=str(content_path))
    )
    with pytest.raises(FileNotFoundError):
        cardnews.get_content_json(cardnews.GetContentJsonRequest(content_id="x"))


def test_get_content_json_reads_existing_file(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    content_path = content_dir / "x.json"
    content_path.write_text('{"title": "테스트"}', encoding="utf-8")
    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id="x", content_path=str(content_path))
    )

    result = cardnews.get_content_json(cardnews.GetContentJsonRequest(content_id="x"))

    assert result.content_id == "x"
    assert result.content_path == content_path
    assert "테스트" in result.content_text


def _create_template():
    templates.create_template(
        templates.CreateTemplateRequest(name="기본", html_bytes=b"<html></html>", prompt_bytes=b"system prompt")
    )


def test_generate_content_json_missing_key_raises(monkeypatch):
    _create_template()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        cardnews.generate_content_json(
            cardnews.GenerateContentJsonRequest(content_id="x", template_name="기본", research_note="노트")
        )


def test_generate_content_json_missing_template_raises():
    with pytest.raises(FileNotFoundError):
        cardnews.generate_content_json(
            cardnews.GenerateContentJsonRequest(content_id="x", template_name="없음", research_note="노트")
        )


def test_generate_content_json_success_saves_and_updates_pipeline_state(monkeypatch):
    _create_template()
    monkeypatch.setattr(
        cardnews, "get_openai_client", lambda: _fake_openai_client('```json\n{"cover": {"headline": "h"}}\n```')
    )

    result = cardnews.generate_content_json(
        cardnews.GenerateContentJsonRequest(
            content_id="x", template_name="기본", research_note="노트", source_urls=["http://a"]
        )
    )

    assert result.content == {"cover": {"headline": "h"}, "id": "x"}
    assert result.saved_path.exists()

    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id="x"))
    assert state.content_path == str(result.saved_path)


def test_generate_content_json_parse_failure_returns_none_without_raising(monkeypatch):
    _create_template()
    monkeypatch.setattr(cardnews, "get_openai_client", lambda: _fake_openai_client("이건 JSON이 아님"))

    result = cardnews.generate_content_json(
        cardnews.GenerateContentJsonRequest(content_id="x", template_name="기본", research_note="노트")
    )

    assert result.content is None
    assert result.saved_path is None
    assert result.raw_output == "이건 JSON이 아님"


def test_set_cover_image_missing_content_raises():
    with pytest.raises(FileNotFoundError):
        cardnews.set_cover_image(cardnews.SetCoverImageRequest(content_id="없는id", image_uri="file:///a.png"))


def test_set_cover_image_updates_content_and_file(tmp_path):
    content_path = tmp_path / "x.json"
    content_path.write_text('{"cover": {"headline": "h"}}', encoding="utf-8")
    pipeline.save_pipeline_state(pipeline.SavePipelineStateRequest(content_id="x", content_path=str(content_path)))

    result = cardnews.set_cover_image(
        cardnews.SetCoverImageRequest(content_id="x", image_uri="file:///cover-x.png")
    )

    assert result.content["cover"]["image"] == "file:///cover-x.png"
    assert result.content["cover"]["headline"] == "h"

    import json

    saved = json.loads(content_path.read_text(encoding="utf-8"))
    assert saved["cover"]["image"] == "file:///cover-x.png"


def test_generate_insta_caption_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        cardnews.generate_insta_caption(cardnews.GenerateInstaCaptionRequest(research_note="노트"))


def test_generate_insta_caption_returns_text(monkeypatch):
    monkeypatch.setattr(cardnews, "get_openai_client", lambda: _fake_openai_client("캡션 본문 #태그"))

    result = cardnews.generate_insta_caption(cardnews.GenerateInstaCaptionRequest(research_note="노트"))

    assert result.caption == "캡션 본문 #태그"
