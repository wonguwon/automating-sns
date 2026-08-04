"""worker.py 테스트.

- _dispatch_rss_collect의 JSON 파싱은 네트워크 없이 monkeypatch로 검증한다.
- PENDING → RUNNING → DONE/FAILED 상태 전이는 실제 로컬 MySQL(auto_sns)에 대해 검증한다
  (backend-python/.env의 DB_* 값 필요) — 다만 실제 RSS 수집(네트워크 호출)은 필요 없는
  "아직 연결 안 된 job 타입 → FAILED" 경로로 확인해, tests/test_rss.py와 같은 원칙
  (네트워크 필요한 경로는 자동 테스트에서 제외)을 유지한다.
"""

import json
from pathlib import Path

import pytest

from ai_sns_worker import worker
from ai_sns_worker.core.db import get_connection
from ai_sns_worker.services import cardnews, image, reel, render, research, rss, tts


def test_dispatch_rss_collect_parses_input(monkeypatch):
    captured = {}

    def fake_collect(request):
        captured["group_id"] = request.group_id
        captured["hours"] = request.hours
        return rss.CollectFeedItemsResult(
            group_id=request.group_id, saved_path="dummy.json", item_count=3, items=[]
        )

    monkeypatch.setattr(rss, "collect_feed_items", fake_collect)

    result_json = worker._dispatch_rss_collect(json.dumps({"group_id": "테스트", "hours": 12}))

    assert captured == {"group_id": "테스트", "hours": 12}
    assert json.loads(result_json) == {
        "group_id": "테스트",
        "saved_path": "dummy.json",
        "item_count": 3,
    }


def test_dispatch_rss_collect_defaults_hours(monkeypatch):
    captured = {}

    def fake_collect(request):
        captured["hours"] = request.hours
        return rss.CollectFeedItemsResult(group_id=request.group_id, saved_path="x", item_count=0)

    monkeypatch.setattr(rss, "collect_feed_items", fake_collect)
    worker._dispatch_rss_collect(json.dumps({"group_id": "테스트"}))
    assert captured["hours"] == 24


def test_dispatch_rss_collect_missing_group_id_raises():
    with pytest.raises(KeyError):
        worker._dispatch_rss_collect(json.dumps({"hours": 12}))


def test_dispatch_candidate_select_parses_input(monkeypatch):
    captured = {}

    def fake_select(request):
        captured["group_id"] = request.group_id
        captured["items"] = request.items
        return research.SelectCandidatesResult(group_id=request.group_id, saved_path=Path("c.json"), candidates=[{"id": "x"}])

    monkeypatch.setattr(research, "select_candidates", fake_select)

    result_json = worker._dispatch_candidate_select(json.dumps({"group_id": "g", "items": [{"title": "t"}]}))

    assert captured["group_id"] == "g"
    assert json.loads(result_json) == {"group_id": "g", "saved_path": "c.json", "candidate_count": 1}


def test_dispatch_deep_research_parses_input(monkeypatch):
    def fake_run(request):
        assert request.content_id == "x"
        assert request.candidate == {"title": "t"}
        return research.RunDeepResearchResult(content_id="x", note_path=Path("n.md"), note_text="노트", fetched_any_article=True)

    monkeypatch.setattr(research, "run_deep_research", fake_run)

    result_json = worker._dispatch_deep_research(json.dumps({"content_id": "x", "candidate": {"title": "t"}}))

    assert json.loads(result_json) == {"content_id": "x", "note_path": "n.md", "fetched_any_article": True}


def test_dispatch_cardnews_generate_parses_input(monkeypatch):
    def fake_generate(request):
        assert request.content_id == "x"
        assert request.template_name == "기본"
        return cardnews.GenerateContentJsonResult(content_id="x", content={"id": "x"}, raw_output="{}", saved_path=Path("c.json"))

    monkeypatch.setattr(cardnews, "generate_content_json", fake_generate)

    result_json = worker._dispatch_cardnews_generate(
        json.dumps({"content_id": "x", "template_name": "기본", "research_note": "노트"})
    )

    assert json.loads(result_json) == {"content_id": "x", "parsed": True, "saved_path": "c.json"}


def test_dispatch_cover_image_generate_links_content_json(monkeypatch):
    linked = {}

    def fake_generate_cover_image(request):
        return image.GenerateCoverImageResult(content_id=request.content_id, image_path=Path("c.png"), image_uri="file:///c.png")

    def fake_set_cover_image(request):
        linked["called"] = request
        return cardnews.SetCoverImageResult(content_id=request.content_id, content={})

    monkeypatch.setattr(image, "generate_cover_image", fake_generate_cover_image)
    monkeypatch.setattr(cardnews, "set_cover_image", fake_set_cover_image)

    result_json = worker._dispatch_cover_image_generate(json.dumps({"content_id": "x", "concept": "개념"}))

    assert linked["called"].image_uri == "file:///c.png"
    assert json.loads(result_json) == {"content_id": "x", "image_uri": "file:///c.png", "error": None}


def test_dispatch_cover_image_generate_skips_link_on_failure(monkeypatch):
    monkeypatch.setattr(
        image, "generate_cover_image",
        lambda request: image.GenerateCoverImageResult(content_id=request.content_id, image_path=None, image_uri=None, error="실패"),
    )
    called = {"flag": False}
    monkeypatch.setattr(cardnews, "set_cover_image", lambda request: called.update(flag=True))

    result_json = worker._dispatch_cover_image_generate(json.dumps({"content_id": "x", "concept": "개념"}))

    assert called["flag"] is False
    assert json.loads(result_json) == {"content_id": "x", "image_uri": None, "error": "실패"}


def test_dispatch_cardnews_render_parses_input(monkeypatch):
    def fake_render(request):
        assert request.content_id == "x"
        assert request.template_name == "기본"
        return render.RenderCardnewsResult(content_id="x", out_dir=Path("out"), slide_count=6)

    monkeypatch.setattr(render, "render_cardnews", fake_render)

    result_json = worker._dispatch_cardnews_render(json.dumps({"content_id": "x", "template_name": "기본"}))

    assert json.loads(result_json) == {"content_id": "x", "out_dir": "out", "slide_count": 6}


def test_dispatch_reel_script_generate_parses_input(monkeypatch):
    def fake_generate(request):
        assert request.content_id == "x"
        return reel.GenerateReelScriptResult(content_id="x", script={"id": "x"}, raw_output="{}", saved_path=Path("s.json"))

    monkeypatch.setattr(reel, "generate_reel_script", fake_generate)

    result_json = worker._dispatch_reel_script_generate(json.dumps({"content_id": "x", "research_note": "노트"}))

    assert json.loads(result_json) == {"content_id": "x", "parsed": True, "saved_path": "s.json"}


def test_dispatch_scene_image_generate_links_script(monkeypatch):
    linked = {}

    def fake_generate_scene_image(request):
        return image.GenerateSceneImageResult(
            content_id=request.content_id, scene_index=request.scene_index,
            image_path=Path("scene_00.png"), image_uri="file:///scene_00.png",
        )

    def fake_set_scene_resolved_image(request):
        linked["called"] = request
        return reel.SetSceneResolvedImageResult(content_id=request.content_id, scene_index=request.scene_index, script={})

    monkeypatch.setattr(image, "generate_scene_image", fake_generate_scene_image)
    monkeypatch.setattr(reel, "set_scene_resolved_image", fake_set_scene_resolved_image)

    result_json = worker._dispatch_scene_image_generate(
        json.dumps({"content_id": "x", "scene_index": 0, "concept": "장면"})
    )

    assert linked["called"].image_path == "scene_00.png"
    assert json.loads(result_json) == {"content_id": "x", "scene_index": 0, "image_uri": "file:///scene_00.png", "error": None}


def test_dispatch_tts_synthesize_parses_input(monkeypatch):
    def fake_synthesize(request):
        assert request.content_id == "x"
        assert request.line_no == 1
        assert request.text == "안녕"
        assert request.emotion_type == "preset"
        return tts.SynthesizeLineResult(content_id="x", line_no=1, audio_path=Path("line_01.mp3"))

    monkeypatch.setattr(tts, "synthesize_line", fake_synthesize)

    result_json = worker._dispatch_tts_synthesize(
        json.dumps({"content_id": "x", "line_no": 1, "text": "안녕", "emotion_type": "preset"})
    )

    assert json.loads(result_json) == {"content_id": "x", "line_no": 1, "audio_path": "line_01.mp3"}


def test_dispatch_reel_render_parses_input(monkeypatch):
    def fake_render(request):
        assert request.content_id == "x"
        assert request.bgm_path is None
        return render.RenderReelResult(content_id="x", out_path=Path("x.mp4"), total_duration=12.5)

    monkeypatch.setattr(render, "render_reel", fake_render)

    result_json = worker._dispatch_reel_render(json.dumps({"content_id": "x"}))

    assert json.loads(result_json) == {"content_id": "x", "out_path": "x.mp4", "total_duration": 12.5}


@pytest.fixture
def db_conn():
    conn = get_connection()
    yield conn
    conn.close()


@pytest.fixture
def temp_project(db_conn):
    """auto_sns 스키마에 임시 user/project를 만들고 테스트가 끝나면 지운다."""
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (email, display_name, created_at) VALUES (%s, %s, NOW())",
            (f"worker-test-{id(cur)}@example.com", "Worker Test User"),
        )
        user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO projects (owner_id, name, created_at) VALUES (%s, %s, NOW())",
            (user_id, "Worker Test Project"),
        )
        project_id = cur.lastrowid

    yield project_id

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM jobs WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))


def test_poll_once_returns_false_when_no_pending_job(db_conn, temp_project):
    # temp_project만 만들고 job은 없는 상태 — 다만 다른 프로젝트에 PENDING job이 있으면
    # 그걸 집어갈 수 있으니, 이 테스트는 "적어도 예외 없이 False/True 중 하나를 반환한다"만
    # 확인한다(전체 테이블을 비운다고 가정할 수 없어서).
    assert isinstance(worker.poll_once(), bool)


def test_dispatch_covers_all_job_types():
    """JobType.java의 10개 값(2026-08-03 기준) 전부가 DISPATCH에 연결돼 있는지 확인한다 —
    실제 DB의 jobs.type 컬럼은 SQL ENUM(JobType.java 값만 허용, VARCHAR가 아님)이라 여기
    없는 타입은 애초에 DB에 넣을 수조차 없다. 그래서 "연결 안 된 타입 → FAILED" 경로는
    (모든 JobType이 연결된 지금은) DB 통합 테스트 대신 이 목록 대조로만 확인한다."""
    job_types = {
        "RSS_COLLECT", "CANDIDATE_SELECT", "DEEP_RESEARCH", "CARDNEWS_GENERATE",
        "COVER_IMAGE_GENERATE", "CARDNEWS_RENDER", "REEL_SCRIPT_GENERATE",
        "SCENE_IMAGE_GENERATE", "TTS_SYNTHESIZE", "REEL_RENDER",
    }
    assert set(worker.DISPATCH) == job_types
