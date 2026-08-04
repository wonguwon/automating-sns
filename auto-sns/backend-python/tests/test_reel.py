"""services/reel.py 테스트.

generate_reel_script는 실제로는 GPT 호출(비용 발생)이 필요하다 — get_openai_client를 가짜
클라이언트로 monkeypatch해서 프롬프트 조립/파싱/저장 로직만 검증한다.
"""

import json
from types import SimpleNamespace

import pytest

from ai_sns_worker.services import pipeline, reel


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "PIPELINE_DIR", tmp_path / "pipeline")
    monkeypatch.setattr(reel, "REEL_SCRIPT_DIR", tmp_path / "reel_script")


def _fake_openai_client(content: str):
    def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_generate_reel_script_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        reel.generate_reel_script(reel.GenerateReelScriptRequest(content_id="x", research_note="노트"))


def test_generate_reel_script_success_saves_and_updates_pipeline_state(monkeypatch):
    fake_script = {"title_line1": "제목1", "title_line2": "제목2", "scenes": [], "lines": []}
    monkeypatch.setattr(reel, "get_openai_client", lambda: _fake_openai_client(f"```json\n{json.dumps(fake_script)}\n```"))

    result = reel.generate_reel_script(
        reel.GenerateReelScriptRequest(
            content_id="x", research_note="노트", photo_library=[{"file": "a.png", "description": "설명"}]
        )
    )

    assert result.script == {**fake_script, "id": "x"}
    assert result.saved_path.exists()

    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id="x"))
    assert state.reel_script_path == str(result.saved_path)


def test_generate_reel_script_parse_failure_returns_none_without_raising(monkeypatch):
    monkeypatch.setattr(reel, "get_openai_client", lambda: _fake_openai_client("JSON이 아닌 응답"))

    result = reel.generate_reel_script(reel.GenerateReelScriptRequest(content_id="x", research_note="노트"))

    assert result.script is None
    assert result.saved_path is None
    assert result.raw_output == "JSON이 아닌 응답"


def test_build_reel_script_prompt_without_photo_library_uses_placeholder():
    system_prompt, user_prompt = reel._build_reel_script_prompt(
        reel.GenerateReelScriptRequest(content_id="x", research_note="노트")
    )
    assert "등록된 사진 없음" in user_prompt
    assert "나레이션" in system_prompt


def test_build_reel_script_prompt_with_photo_library_lists_files():
    _, user_prompt = reel._build_reel_script_prompt(
        reel.GenerateReelScriptRequest(
            content_id="x", research_note="노트", photo_library=[{"file": "a.png", "description": "설명"}]
        )
    )
    assert "a.png: 설명" in user_prompt


def _save_script(tmp_path, content_id="x", scenes=None):
    scenes = scenes if scenes is not None else [{"motion": "static"}]
    script_path = tmp_path / f"{content_id}.json"
    script_path.write_text(json.dumps({"scenes": scenes, "lines": []}, ensure_ascii=False), encoding="utf-8")
    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id=content_id, reel_script_path=str(script_path))
    )
    return script_path


def test_set_scene_resolved_image_missing_script_raises():
    with pytest.raises(FileNotFoundError):
        reel.set_scene_resolved_image(
            reel.SetSceneResolvedImageRequest(content_id="없는id", scene_index=0, image_path="/a.png")
        )


def test_set_scene_resolved_image_invalid_index_raises(tmp_path):
    _save_script(tmp_path, scenes=[{"motion": "static"}])
    with pytest.raises(IndexError):
        reel.set_scene_resolved_image(
            reel.SetSceneResolvedImageRequest(content_id="x", scene_index=5, image_path="/a.png")
        )


def test_set_scene_resolved_image_updates_script_and_file(tmp_path):
    script_path = _save_script(tmp_path, scenes=[{"motion": "static"}, {"motion": "zoom_in"}])

    result = reel.set_scene_resolved_image(
        reel.SetSceneResolvedImageRequest(content_id="x", scene_index=1, image_path="/scene_01.png")
    )

    assert result.script["scenes"][1]["resolved_image_path"] == "/scene_01.png"
    assert "resolved_image_path" not in result.script["scenes"][0]

    saved = json.loads(script_path.read_text(encoding="utf-8"))
    assert saved["scenes"][1]["resolved_image_path"] == "/scene_01.png"
