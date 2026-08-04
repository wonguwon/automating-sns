"""services/pipeline.py 매니페스트 load/save 테스트."""

import pytest

from ai_sns_worker.services import pipeline


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """PIPELINE_DIR을 tmp_path 아래로 바꿔 실제 storage/를 건드리지 않는다."""
    monkeypatch.setattr(pipeline, "PIPELINE_DIR", tmp_path / "pipeline")


def test_load_missing_state_returns_empty_fields():
    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id="없는id"))
    assert state.content_id == "없는id"
    assert state.candidate is None
    assert state.content_path is None
    assert state.updated_at is None


def test_save_then_load_roundtrip():
    candidate = {"id": "20260803-01", "title": "테스트 후보"}
    saved = pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id="20260803-01", candidate=candidate)
    )
    assert saved.candidate == candidate
    assert saved.updated_at is not None

    loaded = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id="20260803-01"))
    assert loaded.candidate == candidate
    assert loaded.content_path is None


def test_save_partial_update_keeps_existing_fields():
    content_id = "20260803-02"
    pipeline.save_pipeline_state(pipeline.SavePipelineStateRequest(content_id=content_id, candidate={"id": "x"}))
    updated = pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id=content_id, research_note_path="/a/b.md")
    )
    assert updated.candidate == {"id": "x"}
    assert updated.research_note_path == "/a/b.md"


def test_save_updates_updated_at_each_time():
    content_id = "20260803-03"
    first = pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id=content_id, content_path="/a.json")
    )
    second = pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id=content_id, render_out_dir="/out")
    )
    assert second.updated_at >= first.updated_at
    assert second.content_path == "/a.json"
    assert second.render_out_dir == "/out"
