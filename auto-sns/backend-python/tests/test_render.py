"""services/render.py 테스트.

render_cardnews의 실제 Playwright 렌더(_render_slides)와 render_reel의 실제 ffmpeg 실행은
로컬 실행 도구가 필요해 monkeypatch로 대체한다 — 여기서는 오케스트레이션(파일 조회/저장,
pipeline_state 갱신, 입력 검증)과 순수 헬퍼 함수(자막 줄바꿈/모션 필터식/샷 묶기)만 검증한다.
"""

import json
from types import SimpleNamespace

import pytest

from ai_sns_worker.services import pipeline, render, templates


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "PIPELINE_DIR", tmp_path / "pipeline")
    monkeypatch.setattr(templates, "TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr(render, "TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr(render, "CARDNEWS_OUTPUT_DIR", tmp_path / "outputs" / "cardnews")
    monkeypatch.setattr(render, "REEL_OUTPUT_DIR", tmp_path / "outputs" / "reel")


# ============================================================
# 순수 헬퍼 함수
# ============================================================
def test_wrap_two_lines_short_text_unchanged():
    assert render._wrap_two_lines("짧은자막", 10) == ["짧은자막"]


def test_wrap_two_lines_splits_at_nearest_space_to_middle():
    assert render._wrap_two_lines("가나다 라마바 사아자 차카타", 10) == ["가나다 라마바", "사아자 차카타"]


def test_wrap_two_lines_no_space_returns_as_is():
    assert render._wrap_two_lines("가나다라마바사아자차카타파하", 5) == ["가나다라마바사아자차카타파하"]


def test_top_aligned_line_ys():
    assert render._top_aligned_line_ys(100, 3, 50, 10) == [100, 160, 220]


def test_motion_filter_expr_static_has_no_zoom():
    z, x, y = render._motion_filter_expr("static", 30)
    assert z == "1"


def test_motion_filter_expr_zoom_in_uses_zoom_step():
    z, x, y = render._motion_filter_expr("zoom_in", 30)
    assert "zoom+" in z


def test_group_into_shots_groups_consecutive_same_scene():
    lines = [
        {"scene_index": 0}, {"scene_index": 0}, {"scene_index": 1}, {"scene_index": 1}, {"scene_index": 1},
    ]
    assert render._group_into_shots(lines) == [(0, 0, 2), (1, 2, 5)]


def test_ffmpeg_escape_path_escapes_colon_and_backslash():
    escaped = render._ffmpeg_escape_path(render.Path("C:\\a\\b.otf"))
    assert escaped == "C\\:/a/b.otf"


# ============================================================
# render_cardnews — 오케스트레이션(Playwright 실제 렌더는 monkeypatch로 대체)
# ============================================================
def _create_template():
    templates.create_template(
        templates.CreateTemplateRequest(name="기본", html_bytes=b"<html></html>", prompt_bytes=b"prompt")
    )


def test_render_cardnews_missing_content_raises():
    _create_template()
    with pytest.raises(FileNotFoundError):
        render.render_cardnews(render.RenderCardnewsRequest(content_id="없는id", template_name="기본"))


def test_render_cardnews_missing_template_raises(tmp_path):
    content_path = tmp_path / "content.json"
    content_path.write_text(json.dumps({"slides": []}), encoding="utf-8")
    pipeline.save_pipeline_state(pipeline.SavePipelineStateRequest(content_id="x", content_path=str(content_path)))

    with pytest.raises(FileNotFoundError):
        render.render_cardnews(render.RenderCardnewsRequest(content_id="x", template_name="없음"))


def test_render_cardnews_success_writes_side_files_and_updates_pipeline_state(tmp_path, monkeypatch):
    _create_template()
    content = {"slides": [{"source": "http://a"}], "caption": "본문", "hashtags": ["뉴스"]}
    content_path = tmp_path / "content.json"
    content_path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    pipeline.save_pipeline_state(pipeline.SavePipelineStateRequest(content_id="x", content_path=str(content_path)))

    recorded = {}

    def fake_render_slides(template_path, content_arg, out_dir, slide_count):
        recorded["template_path"] = template_path
        recorded["slide_count"] = slide_count

    monkeypatch.setattr(render, "_render_slides", fake_render_slides)

    result = render.render_cardnews(render.RenderCardnewsRequest(content_id="x", template_name="기본"))

    assert recorded["slide_count"] == 3  # 표지 1 + 슬라이드 1 + CTA 1
    assert result.out_dir.exists()
    assert (result.out_dir / "caption.txt").read_text(encoding="utf-8").startswith("본문")
    assert "슬라이드 1: http://a" in (result.out_dir / "sources.md").read_text(encoding="utf-8")

    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id="x"))
    assert state.render_out_dir == str(result.out_dir)


# ============================================================
# render_reel — 오케스트레이션(ffmpeg/ffprobe 실행은 monkeypatch로 대체)
# ============================================================
def _fake_subprocess_run(cmd, **kwargs):
    if cmd[0] == "ffprobe":
        return SimpleNamespace(returncode=0, stdout="2.000\n", stderr="")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def _setup_reel_state(tmp_path, monkeypatch, n_lines=2):
    scene_image = tmp_path / "scene_00.png"
    scene_image.write_bytes(b"fake-png")

    script = {
        "title_line1": "제목1",
        "title_line2": "제목2",
        "scenes": [{"motion": "static", "resolved_image_path": str(scene_image)}],
        "lines": [{"speaker": "나레이션", "text": f"대사{i}", "scene_index": 0} for i in range(n_lines)],
    }
    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    for i in range(1, n_lines + 1):
        (audio_dir / f"line_{i:02d}.mp3").write_bytes(b"fake-audio")

    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(
            content_id="x", reel_script_path=str(script_path), reel_audio_dir=str(audio_dir)
        )
    )
    monkeypatch.setattr(render.subprocess, "run", _fake_subprocess_run)
    return script_path, audio_dir


def test_render_reel_missing_script_raises():
    with pytest.raises(FileNotFoundError):
        render.render_reel(render.RenderReelRequest(content_id="없는id"))


def test_render_reel_missing_audio_dir_raises(tmp_path):
    script_path = tmp_path / "script.json"
    script_path.write_text("{}", encoding="utf-8")
    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id="x", reel_script_path=str(script_path))
    )
    with pytest.raises(FileNotFoundError):
        render.render_reel(render.RenderReelRequest(content_id="x"))


def test_render_reel_missing_scene_image_raises(tmp_path, monkeypatch):
    script = {"scenes": [{"motion": "static", "resolved_image_path": None}], "lines": [{"text": "a", "scene_index": 0}]}
    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps(script), encoding="utf-8")
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "line_01.mp3").write_bytes(b"x")
    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id="x", reel_script_path=str(script_path), reel_audio_dir=str(audio_dir))
    )
    monkeypatch.setattr(render.subprocess, "run", _fake_subprocess_run)

    with pytest.raises(FileNotFoundError):
        render.render_reel(render.RenderReelRequest(content_id="x"))


def test_render_reel_success_builds_mp4_and_updates_pipeline_state(tmp_path, monkeypatch):
    _setup_reel_state(tmp_path, monkeypatch, n_lines=2)

    result = render.render_reel(render.RenderReelRequest(content_id="x"))

    assert result.total_duration == pytest.approx(4.0)
    assert result.out_path.name == "x.mp4"

    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id="x"))
    assert state.reel_path == str(result.out_path)
