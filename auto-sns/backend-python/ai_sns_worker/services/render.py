"""카드뉴스 PNG 렌더 및 릴스 mp4 조립.

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO를 받고 result DTO를 반환한다.
- 실패는 예외로 알린다.

이 두 함수는 외부 API 호출은 필요 없지만(비용 없음) 로컬 실행 도구가 있어야 동작한다 —
`render_cardnews`는 Playwright 브라우저 바이너리(`playwright install`), `render_reel`은
ffmpeg/ffprobe가 PATH에 있어야 한다. 코드는 이관해뒀지만 실제 실행 전에는 이 도구들이
설치돼 있는지 확인하고 사용자 확인을 받는다(2026-08-03, `wiki/decisions.md` 참고).
`render_reel`은 폰트 파일(`storage/assets/fonts/Pretendard-Black.otf`)도 필요한데 아직
이 저장소에 옮겨두지 않았다 — 실제 실행 전에 추가해야 한다.

legacy 대응:
- legacy/Render.py (render, write_side_files)
- legacy/Render_reel_narrated.py (build_reel과 그 보조 함수 전체)

`render_reel`은 대본(services/reel.py가 저장한 reel_script/<id>.json)의 각 장면에
`resolved_image_path`가 이미 채워져 있다고 가정한다 — legacy도 이 필드를 "장면 이미지 준비"
UI 단계에서 채운 뒤 넘겨받기만 했다(별도 services 함수 없음, 2026-08-03 확인 — 이번 단계
이관 범위 밖. services/image.py의 generate_scene_image가 이미지를 생성한 뒤, 호출부가 그
경로를 대본 JSON에 다시 써넣는 연결 작업이 아직 없다).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..core.paths import ASSETS_DIR, CARDNEWS_OUTPUT_DIR, REEL_OUTPUT_DIR, TEMPLATES_DIR
from . import cardnews, pipeline, templates


# ============================================================
# 카드뉴스 렌더 — legacy/Render.py
# ============================================================
@dataclass
class RenderCardnewsRequest:
    content_id: str
    template_name: str


@dataclass
class RenderCardnewsResult:
    content_id: str
    out_dir: Path
    slide_count: int


def _write_side_files(content: dict, out_dir: Path) -> None:
    """caption.txt/sources.md/content.json 사본을 출력 폴더에 함께 남긴다.
    legacy: Render.write_side_files"""
    caption = content.get("caption", "")
    hashtags = " ".join(f"#{h}" for h in content.get("hashtags", []))
    (out_dir / "caption.txt").write_text(f"{caption}\n\n{hashtags}", encoding="utf-8")

    lines = ["# 출처\n"]
    for i, s in enumerate(content.get("slides", []), start=1):
        if s.get("source"):
            lines.append(f"- 슬라이드 {i}: {s['source']}")
    (out_dir / "sources.md").write_text("\n".join(lines), encoding="utf-8")

    (out_dir / "content.json").write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_slides(template_path: Path, content: dict, out_dir: Path, slide_count: int) -> None:
    """Playwright(chromium)로 캐러셀(4:5)/스토리(9:16) PNG를 실제로 스크린샷 뜬다. 스키마 위반
    또는 텍스트 넘침이 있으면 그 자리에서 RuntimeError를 던지고 멈춘다 — 깨진 카드가 조용히
    만들어지는 걸 막기 위함(legacy와 동일). 실제 실행에는 Playwright 브라우저 바이너리가
    필요하다. 테스트는 이 함수를 통째로 monkeypatch해서 render_cardnews의 나머지 오케스트레이션
    (폴더 생성, 파일 저장, pipeline_state 갱신)만 검증한다.
    legacy: Render.render의 sync_playwright 블록"""
    from playwright.sync_api import sync_playwright

    content_json = json.dumps(content, ensure_ascii=False)
    template_url = f"file://{template_path.resolve()}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for ratio, folder in [("45", "carousel"), ("916", "story")]:
                for i in range(slide_count):
                    page = browser.new_page(viewport={"width": 1400, "height": 2100})
                    page.add_init_script(f"window.__EXTERNAL_CONTENT__ = {content_json};")
                    page.goto(f"{template_url}?r={ratio}&i={i}")
                    page.wait_for_selector('body[data-ready="1"]', timeout=15000)

                    errs = page.evaluate("() => window.__validationErrors || []")
                    if errs:
                        raise RuntimeError("스키마 검증 실패 — 렌더 중단:\n  - " + "\n  - ".join(errs))

                    overflow = page.evaluate(
                        "() => { const b = document.querySelector('.bodyc'); "
                        "return b ? b.scrollHeight > b.clientHeight + 2 : false; }"
                    )
                    if overflow:
                        raise RuntimeError(
                            f"슬라이드 {i + 1} ({folder}) 텍스트 넘침 — "
                            "글자수를 줄이거나 상한(LIMITS)을 확인하세요."
                        )

                    out_path = out_dir / folder / f"{i + 1:02d}.png"
                    page.locator(".frame").screenshot(path=str(out_path))
                    page.close()
        finally:
            browser.close()


def render_cardnews(request: RenderCardnewsRequest) -> RenderCardnewsResult:
    """content.json + 템플릿으로 4:5 캐러셀 PNG 세트와 9:16 스토리 PNG 세트를 렌더한다.
    완료 후 services/pipeline.py 매니페스트에 render_out_dir을 기록한다.
    실제 실행에는 Playwright 브라우저 바이너리가 필요하다 — 실행 전 사용자 확인 필요
    (모듈 docstring 참고).
    legacy: Render.render"""
    content_result = cardnews.get_content_json(cardnews.GetContentJsonRequest(content_id=request.content_id))
    content = json.loads(content_result.content_text)

    templates.get_template(templates.GetTemplateRequest(name=request.template_name))  # 존재 검증
    template_path = TEMPLATES_DIR / request.template_name / "template.html"

    out_dir = CARDNEWS_OUTPUT_DIR / request.content_id
    (out_dir / "carousel").mkdir(parents=True, exist_ok=True)
    (out_dir / "story").mkdir(parents=True, exist_ok=True)
    _write_side_files(content, out_dir)

    slide_count = len(content.get("slides", [])) + 2  # 표지 1 + 본문 N + CTA 1
    _render_slides(template_path, content, out_dir, slide_count)

    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id=request.content_id, render_out_dir=str(out_dir))
    )

    return RenderCardnewsResult(content_id=request.content_id, out_dir=out_dir, slide_count=slide_count)


# ============================================================
# 릴스 조립 — legacy/Render_reel_narrated.py
# ============================================================
FPS = 30
WIDTH, HEIGHT = 1080, 1920
# 위/아래 검은 바 — 위에는 제목(2줄), 아래에는 그 순간 대사(자막, 1~2줄)를 얹는다. 이미지는
# 그 사이 가운데 영역에만 채운다. 수치는 legacy 실측 기반: 상단 바 452px 고정, 가운데 이미지는
# 4:3(가로) 비율로 화면 폭을 그대로 채우고, 하단 바는 나머지.
TITLE_BAR_H = 452
IMAGE_AREA_H = round(WIDTH * 3 / 4)
SUBTITLE_BAR_H = HEIGHT - TITLE_BAR_H - IMAGE_AREA_H
# zoompan은 원본 해상도 그대로 확대하면 계단현상이 보여서, 먼저 2배 캔버스로 키운 뒤 줌/팬한다.
UPSCALE_W, UPSCALE_IMG_H = WIDTH * 2, IMAGE_AREA_H * 2
ZOOM_STEP = 0.0015
PAN_ZOOM = 1.15  # 패닝 중에는 이동할 여백을 두기 위해 약간 확대한 상태를 유지한다
TITLE_FONTSIZE = 99
SUBTITLE_FONTSIZE = 68
LINE_GAP = 18  # 제목·자막이 2줄일 때 줄 사이 여백
TITLE_TOP_MARGIN = 185  # 스마트폰 전면 카메라(펀치홀) 위치를 피하기 위한 제목 상단 고정 여백
SUBTITLE_RIGHT_MARGIN = 160  # 자막 오른쪽 정렬 기준 여백
SUBTITLE_TOP_MARGIN = 40  # 자막이 사진 바로 아래 붙도록 — 바 안 세로 중앙정렬 대신 상단 고정
SUBTITLE_MAX_CHARS = 10  # 한 줄 최대 글자 수 — 이보다 길면 공백 기준으로 2줄로 나눈다
# 한글 렌더링을 위해 폰트 파일을 직접 지정한다(fontconfig 이름 매칭에 기대지 않는다).
# TODO(실행 전 필수): 이 파일을 storage/assets/fonts/에 옮겨둬야 한다 — 아직 옮기지 않았다.
FONT_PATH = ASSETS_DIR / "fonts" / "Pretendard-Black.otf"


@dataclass
class RenderReelRequest:
    content_id: str
    bgm_path: Path | None = None
    bgm_volume: float = 0.15


@dataclass
class RenderReelResult:
    content_id: str
    out_path: Path
    total_duration: float


def _ffmpeg_escape_path(path: Path) -> str:
    """ffmpeg filtergraph 옵션 값 안에 경로를 넣을 때, 드라이브 콜론(:)과 역슬래시를
    이스케이프한다. legacy: Render_reel_narrated.ffmpeg_escape_path"""
    return str(path).replace("\\", "/").replace(":", r"\:")


def _wrap_two_lines(text: str, max_chars: int) -> list[str]:
    """자막이 max_chars보다 길면 가운데에 가장 가까운 공백에서 2줄로 나눈다.
    legacy: Render_reel_narrated.wrap_two_lines"""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    mid = len(text) / 2
    space_positions = [i for i, c in enumerate(text) if c == " "]
    if not space_positions:
        return [text]
    split_at = min(space_positions, key=lambda i: abs(i - mid))
    line1, line2 = text[:split_at].strip(), text[split_at:].strip()
    return [line1, line2] if line1 and line2 else [text]


def _top_aligned_line_ys(top: int, n_lines: int, fontsize: int, gap: int) -> list[int]:
    """legacy: Render_reel_narrated.top_aligned_line_ys"""
    line_h = fontsize + gap
    return [top + i * line_h for i in range(n_lines)]


def _probe_duration(path: Path) -> float:
    """legacy: Render_reel_narrated.probe_duration"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"오디오 길이 확인 실패: {path}\n{result.stderr}")
    return float(result.stdout.strip())


def _find_line_audio(audio_dir: Path, line_no: int) -> Path:
    """legacy: Render_reel_narrated.find_line_audio"""
    matches = sorted(audio_dir.glob(f"line_{line_no:02d}.*"))
    if not matches:
        raise FileNotFoundError(f"오디오 파일 없음: {audio_dir}/line_{line_no:02d}.*")
    return matches[0]


def _group_into_shots(lines: list[dict]) -> list[tuple[int, int, int]]:
    """연속된 줄 중 scene_index가 같은 구간을 하나의 샷으로 묶는다.
    legacy: Render_reel_narrated.group_into_shots"""
    shots = []
    start = 0
    n = len(lines)
    for i in range(1, n + 1):
        if i == n or lines[i]["scene_index"] != lines[start]["scene_index"]:
            shots.append((lines[start]["scene_index"], start, i))
            start = i
    return shots


def _motion_filter_expr(motion: str, frames: int) -> tuple[str, str, str]:
    """motion에 맞는 zoompan의 z(줌)/x/y(팬) 표현식을 돌려준다.
    legacy: Render_reel_narrated.motion_filter_expr"""
    last_frame = max(1, frames - 1)
    if motion == "zoom_in":
        z = f"min(zoom+{ZOOM_STEP},1.5)"
        x = "iw/2-(iw/zoom/2)"
    elif motion == "zoom_out":
        z = f"if(eq(on,0),1.5,max(zoom-{ZOOM_STEP},1.0))"
        x = "iw/2-(iw/zoom/2)"
    elif motion == "pan_left":
        z = f"{PAN_ZOOM}"
        x = f"(iw-iw/zoom)*(1-on/{last_frame})"
    elif motion == "pan_right":
        z = f"{PAN_ZOOM}"
        x = f"(iw-iw/zoom)*(on/{last_frame})"
    else:  # static
        z = "1"
        x = "iw/2-(iw/zoom/2)"
    y = "ih/2-(ih/zoom/2)"
    return z, x, y


def _render_shot(image_path: Path, motion: str, duration: float, out_path: Path) -> None:
    """이미지 한 장에 motion 효과를 적용해 duration 길이의 무음 비디오 클립을 만든다.
    legacy: Render_reel_narrated.render_shot"""
    frames = max(1, round(duration * FPS))
    z, x, y = _motion_filter_expr(motion, frames)
    vf = (
        f"scale={UPSCALE_W}:{UPSCALE_IMG_H}:force_original_aspect_ratio=increase,"
        f"crop={UPSCALE_W}:{UPSCALE_IMG_H},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={WIDTH}x{IMAGE_AREA_H}:fps={FPS},"
        f"pad={WIDTH}:{HEIGHT}:0:{TITLE_BAR_H}:color=black,"
        f"format=yuv420p,setsar=1"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"장면 렌더 실패({image_path}):\n{result.stderr[-3000:]}")


def render_reel(request: RenderReelRequest) -> RenderReelResult:
    """대본(services/reel.py가 저장한 JSON)+장면 이미지(각 scene의 resolved_image_path)+
    TTS 오디오(services/tts.py가 저장한 파일)로 릴스 mp4를 조립한다. 대본이나 오디오, 장면
    이미지가 없으면 예외를 던진다.
    실제 실행에는 ffmpeg/ffprobe와 폰트 파일이 필요하다 — 실행 전 사용자 확인 필요
    (모듈 docstring 참고).
    legacy: Render_reel_narrated.build_reel"""
    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id=request.content_id))
    if not state.reel_script_path:
        raise FileNotFoundError(f"릴스 대본이 아직 생성되지 않았습니다: {request.content_id}")
    if not state.reel_audio_dir:
        raise FileNotFoundError(f"릴스 TTS 오디오가 아직 생성되지 않았습니다: {request.content_id}")

    script_path = Path(state.reel_script_path)
    audio_dir = Path(state.reel_audio_dir)
    if not script_path.exists():
        raise FileNotFoundError(f"대본 파일 없음: {script_path}")
    if not audio_dir.exists():
        raise FileNotFoundError(f"오디오 폴더 없음: {audio_dir}")

    script = json.loads(script_path.read_text(encoding="utf-8"))
    lines = script.get("lines", [])
    scenes = script.get("scenes", [])
    if len(lines) < 1:
        raise ValueError(f"대본에 줄이 없습니다: {script_path}")
    if len(scenes) < 1:
        raise ValueError(f"대본에 장면(scenes)이 없습니다: {script_path}")

    audios, durations = [], []
    for i in range(1, len(lines) + 1):
        audio_path = _find_line_audio(audio_dir, i)
        audios.append(audio_path)
        durations.append(_probe_duration(audio_path))

    shots = _group_into_shots(lines)
    total_duration = sum(durations)
    out_path = REEL_OUTPUT_DIR / f"{request.content_id}.mp4"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        shot_paths = []
        for si, (scene_idx, start, end) in enumerate(shots):
            scene = scenes[scene_idx]
            image_path = scene.get("resolved_image_path")
            if not image_path or not Path(image_path).exists():
                raise FileNotFoundError(
                    f"장면 {scene_idx + 1}의 이미지가 없습니다 — services/image.py로 먼저 생성하고 "
                    "대본의 resolved_image_path에 반영하세요."
                )
            shot_duration = sum(durations[start:end])
            shot_path = tmp / f"shot_{si:02d}.mp4"
            _render_shot(Path(image_path), scene.get("motion", "static"), shot_duration, shot_path)
            shot_paths.append(shot_path)

        cmd = ["ffmpeg", "-y"]
        for p in shot_paths:
            cmd += ["-i", str(p)]
        for a in audios:
            cmd += ["-i", str(a)]
        bgm_idx = None
        if request.bgm_path is not None:
            bgm_idx = len(shot_paths) + len(audios)
            cmd += ["-i", str(request.bgm_path)]

        filters = []
        v_labels = "".join(f"[{i}:v]" for i in range(len(shot_paths)))
        filters.append(f"{v_labels}concat=n={len(shot_paths)}:v=1:a=0[vconcat]")

        font_escaped = _ffmpeg_escape_path(FONT_PATH)
        cur_label = "vconcat"

        title_lines = [
            t for t in (script.get("title_line1", ""), script.get("title_line2", "")) if (t or "").strip()
        ]
        title_colors = ["white", "yellow"]
        if title_lines:
            ys = _top_aligned_line_ys(TITLE_TOP_MARGIN, len(title_lines), TITLE_FONTSIZE, LINE_GAP)
            for idx, (txt, y) in enumerate(zip(title_lines, ys)):
                title_file = tmp / f"title_{idx}.txt"
                title_file.write_text(txt.strip(), encoding="utf-8")
                out_label = f"vtitle{idx}"
                color = title_colors[idx] if idx < len(title_colors) else "white"
                filters.append(
                    f"[{cur_label}]drawtext=fontfile='{font_escaped}':textfile='{_ffmpeg_escape_path(title_file)}':"
                    f"expansion=none:fontsize={TITLE_FONTSIZE}:fontcolor={color}:x=(w-text_w)/2:y={y}[{out_label}]"
                )
                cur_label = out_label

        cum_time = 0.0
        for i, line in enumerate(lines):
            start, end = cum_time, cum_time + durations[i]
            cum_time = end
            sublines = _wrap_two_lines(line.get("text", ""), SUBTITLE_MAX_CHARS)
            ys = _top_aligned_line_ys(
                TITLE_BAR_H + IMAGE_AREA_H + SUBTITLE_TOP_MARGIN, len(sublines), SUBTITLE_FONTSIZE, LINE_GAP
            )
            for j, (txt, y) in enumerate(zip(sublines, ys)):
                line_file = tmp / f"subtitle_{i:02d}_{j}.txt"
                line_file.write_text(txt, encoding="utf-8")
                out_label = f"vsub{i}_{j}"
                filters.append(
                    f"[{cur_label}]drawtext=fontfile='{font_escaped}':textfile='{_ffmpeg_escape_path(line_file)}':"
                    f"expansion=none:fontsize={SUBTITLE_FONTSIZE}:fontcolor=white:x=w-{SUBTITLE_RIGHT_MARGIN}-text_w:y={y}:"
                    f"enable='between(t,{start:.3f},{end:.3f})'[{out_label}]"
                )
                cur_label = out_label
        final_video_label = cur_label

        a_labels = "".join(f"[{len(shot_paths) + i}:a]" for i in range(len(audios)))
        filters.append(f"{a_labels}concat=n={len(audios)}:v=0:a=1[narr]")

        if request.bgm_path is not None:
            filters.append(
                f"[{bgm_idx}:a]aloop=loop=-1:size=2e9,atrim=0:{total_duration:.3f},"
                f"volume={request.bgm_volume},afade=t=out:st={max(total_duration - 1, 0):.3f}:d=1[bgm]"
            )
            filters.append("[narr][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]")
            audio_out_label = "aout"
        else:
            audio_out_label = "narr"

        filter_complex = ";".join(filters)

        cmd += [
            "-filter_complex", filter_complex,
            "-map", f"[{final_video_label}]",
            "-map", f"[{audio_out_label}]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-r", str(FPS),
            "-s", f"{WIDTH}x{HEIGHT}",
            "-t", f"{total_duration:.3f}",
            str(out_path),
        ]

        out_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 실행 실패:\n{result.stderr[-3000:]}")

    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id=request.content_id, reel_path=str(out_path))
    )

    return RenderReelResult(content_id=request.content_id, out_path=out_path, total_duration=total_duration)
