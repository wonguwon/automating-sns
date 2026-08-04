"""services/research.py 테스트.

select_candidates/run_deep_research는 실제로는 GPT 호출(비용 발생)이 필요하다 — 여기서는
`get_openai_client`를 가짜 클라이언트로 monkeypatch해서 프롬프트 조립/파싱/저장 로직만
검증한다. 실제 OpenAI API는 호출하지 않는다. run_deep_research의 원문 fetch(requests.get)도
monkeypatch로 대체해 실제 네트워크를 타지 않는다.
"""

from types import SimpleNamespace

import pytest

from ai_sns_worker.services import pipeline, research


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """PIPELINE_DIR/CAND_DIR/RESEARCH_DIR을 tmp_path 아래로 바꿔 실제 storage/를 건드리지 않는다."""
    monkeypatch.setattr(pipeline, "PIPELINE_DIR", tmp_path / "pipeline")
    monkeypatch.setattr(research, "CAND_DIR", tmp_path / "candidates")
    monkeypatch.setattr(research, "RESEARCH_DIR", tmp_path / "research")


def _fake_openai_client(content: str):
    def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_get_research_note_missing_state_raises():
    with pytest.raises(FileNotFoundError):
        research.get_research_note(research.GetResearchNoteRequest(content_id="없는id"))


def test_get_research_note_state_without_path_raises():
    pipeline.save_pipeline_state(pipeline.SavePipelineStateRequest(content_id="x", candidate={"id": "x"}))
    with pytest.raises(FileNotFoundError):
        research.get_research_note(research.GetResearchNoteRequest(content_id="x"))


def test_get_research_note_missing_file_raises(tmp_path):
    note_path = tmp_path / "research" / "x.md"
    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id="x", research_note_path=str(note_path))
    )
    with pytest.raises(FileNotFoundError):
        research.get_research_note(research.GetResearchNoteRequest(content_id="x"))


def test_get_research_note_reads_existing_file(tmp_path):
    note_dir = tmp_path / "research"
    note_dir.mkdir()
    note_path = note_dir / "x.md"
    note_path.write_text("# 조사 노트\n내용", encoding="utf-8")
    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id="x", research_note_path=str(note_path))
    )

    result = research.get_research_note(research.GetResearchNoteRequest(content_id="x"))

    assert result.content_id == "x"
    assert result.note_path == note_path
    assert "조사 노트" in result.note_text


def test_select_candidates_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        research.select_candidates(research.SelectCandidatesRequest(group_id="g1", items=[]))


def test_select_candidates_parses_and_saves(monkeypatch):
    fake_candidates = [{"id": "20260803-01", "title": "테스트 후보"}]
    monkeypatch.setattr(
        research, "get_openai_client", lambda: _fake_openai_client(f"```json\n{__import__('json').dumps(fake_candidates)}\n```")
    )

    result = research.select_candidates(
        research.SelectCandidatesRequest(
            group_id="g1", items=[{"feed": "테스트피드", "tier": "1", "title": "제목", "summary": "요약", "link": "http://x"}]
        )
    )

    assert result.group_id == "g1"
    assert result.candidates == fake_candidates
    assert result.saved_path.exists()
    assert result.saved_path.read_text(encoding="utf-8").strip().startswith("[")


def test_run_deep_research_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        research.run_deep_research(
            research.RunDeepResearchRequest(content_id="x", candidate={"title": "t"})
        )


def test_run_deep_research_without_sources_skips_fetch_and_saves_note(monkeypatch):
    monkeypatch.setattr(research, "get_openai_client", lambda: _fake_openai_client("조사 노트 본문"))

    result = research.run_deep_research(
        research.RunDeepResearchRequest(
            content_id="x", candidate={"title": "제목", "one_line": "한줄", "angle": "각도"}
        )
    )

    assert result.fetched_any_article is False
    assert result.note_text == "조사 노트 본문"
    assert result.note_path.read_text(encoding="utf-8") == "조사 노트 본문"

    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id="x"))
    assert state.candidate == {"title": "제목", "one_line": "한줄", "angle": "각도"}
    assert state.research_note_path == str(result.note_path)


def test_run_deep_research_fetches_article_text(monkeypatch):
    monkeypatch.setattr(research, "get_openai_client", lambda: _fake_openai_client("노트"))

    fake_html = "<html><body><article><p>실제 기사 본문 내용입니다.</p></article></body></html>"
    monkeypatch.setattr(
        research.requests, "get", lambda *a, **k: SimpleNamespace(status_code=200, text=fake_html)
    )

    result = research.run_deep_research(
        research.RunDeepResearchRequest(
            content_id="y",
            candidate={"title": "제목", "one_line": "한줄", "angle": "각도", "sources": ["http://example.com/a"]},
        )
    )

    assert result.fetched_any_article is True
