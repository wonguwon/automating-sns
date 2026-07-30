#!/usr/bin/env python3
"""
릴스 조립기(대사 내레이션 + 장면 기반, 2026-07-30 스키마 변경 반영)
------------------------------------------------
data/reel_script/<id>.json은 이제 "scenes"(2~4개, 각각 이미지 1장 + motion)와 "lines"(대사 줄,
scene_index로 장면 참조) 두 배열로 이뤄진다. 이미지 수와 비용을 줄이고 화면을 다이나믹하게
만들기 위해, 장면 하나를 여러 줄이 공유하고 줌인/줌아웃/패닝(motion) 효과로 움직임을 준다
(카드뉴스 렌더처럼 매 줄 새 이미지를 쓰지 않는다).

2단계로 조립한다:
  1) 장면(scene)별로 motion에 맞는 줌/팬 효과를 적용한 무음 비디오 클립을 만든다
     (길이 = 그 장면을 쓰는 줄들의 오디오 길이 합).
  2) 클립들을 순서대로 이어붙이고, 줄별 TTS 오디오를 이어붙인 오디오 트랙(+선택적 배경음악)을
     입힌다.
두 단계로 나눈 이유: ffmpeg의 zoompan 필터는 한 이미지 입력에 대해서만 안정적으로 동작해서,
한 번의 거대한 filter_complex에 다중 이미지 zoompan + concat을 섞는 것보다 장면별로 먼저
렌더링해두는 편이 실패 지점을 줄이고 디버깅하기 쉽다.

data/reel_script/<id>.json의 각 줄이 지목한 장면 이미지는 scenes[i].resolved_image_path(절대
경로 문자열)를 그대로 쓴다 — 릴스 제작 페이지의 「장면 이미지 준비」가 미리 채워둔다.

사전 준비: ffmpeg가 PATH에 있어야 한다.

사용법:
    python3 Render_reel_narrated.py data/reel_script/20260730-01.json data/reel_audio/20260730-01 out.mp4
    python3 Render_reel_narrated.py ... out.mp4 --bgm music/bgm1.mp3 --bgm-volume 0.15
------------------------------------------------
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Windows 콘솔 기본 코드페이지(cp949)는 ✓/✗/⚠ 같은 기호를 인코딩하지 못한다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

FPS = 30
WIDTH, HEIGHT = 1080, 1920
# 위/아래 검은 바 — 위에는 제목(2줄), 아래에는 그 순간 대사(자막, 1~2줄)를 얹는다. 이미지는
# 그 사이 가운데 영역에만 채운다(2026-07-30 사용자 결정 — 이미지를 화면 전체에 크게 쓰지 않는다.
# 자막샘플/ 참고 이미지 스타일 — 제목 2줄(1번째 흰색, 2번째 강조 노란색) + 굵은 자막 1~2줄).
TITLE_BAR_H = 300
SUBTITLE_BAR_H = 320
IMAGE_AREA_H = HEIGHT - TITLE_BAR_H - SUBTITLE_BAR_H
# zoompan은 원본 해상도 그대로 확대하면 계단현상이 보여서, 먼저 2배 캔버스로 키운 뒤 줌/팬한다.
UPSCALE_W, UPSCALE_IMG_H = WIDTH * 2, IMAGE_AREA_H * 2
ZOOM_STEP = 0.0015
PAN_ZOOM = 1.15  # 패닝 중에는 이동할 여백을 두기 위해 약간 확대한 상태를 유지한다
TITLE_FONTSIZE = 56
SUBTITLE_FONTSIZE = 56
LINE_GAP = 18  # 제목·자막이 2줄일 때 줄 사이 여백
SUBTITLE_MAX_CHARS = 16  # 이보다 길면 자막을 공백 기준으로 2줄로 나눈다
# 한글 렌더링을 위해 폰트 파일을 직접 지정한다(fontconfig 이름 매칭에 기대지 않는다 — Windows에서
# libass/drawtext의 폰트 이름 탐색이 불안정할 수 있어서, 항상 있는 폰트 파일 경로를 그대로 쓴다).
# 제목·자막 모두 굵게 써달라는 요청이라 Bold 파일을 쓴다.
FONT_PATH = Path(r"C:\Windows\Fonts\malgunbd.ttf")


def ffmpeg_escape_path(path: Path) -> str:
    """ffmpeg filtergraph 옵션 값 안에 경로를 넣을 때, 드라이브 콜론(:)과 역슬래시를
    이스케이프한다(안 하면 ':'가 필터 옵션 구분자로 오인식된다)."""
    return str(path).replace("\\", "/").replace(":", r"\:")


def wrap_two_lines(text: str, max_chars: int) -> list[str]:
    """자막이 max_chars보다 길면 가운데에 가장 가까운 공백에서 2줄로 나눈다.
    나눌 공백이 없으면(단어 하나로 된 문장 등) 한 줄 그대로 둔다."""
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


def stacked_line_ys(bar_top: int, bar_h: int, n_lines: int, fontsize: int, gap: int) -> list[int]:
    """bar_top~bar_top+bar_h 영역 안에 n_lines줄을 세로 중앙 정렬로 쌓을 때 각 줄의 y좌표."""
    line_h = fontsize + gap
    block_h = n_lines * line_h - gap
    top = bar_top + (bar_h - block_h) // 2
    return [top + i * line_h for i in range(n_lines)]


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        sys.exit(f"오디오 길이 확인 실패: {path}\n{result.stderr}")
    return float(result.stdout.strip())


def find_line_audio(audio_dir: Path, line_no: int) -> Path:
    matches = sorted(audio_dir.glob(f"line_{line_no:02d}.*"))
    if not matches:
        sys.exit(f"오디오 파일 없음: {audio_dir}/line_{line_no:02d}.*")
    return matches[0]


def group_into_shots(lines: list[dict]) -> list[tuple[int, int, int]]:
    """연속된 줄 중 scene_index가 같은 구간을 하나의 샷으로 묶는다.
    (scene_index, 시작 줄 인덱스, 끝 줄 인덱스+1) 튜플 목록을 돌려준다."""
    shots = []
    start = 0
    n = len(lines)
    for i in range(1, n + 1):
        if i == n or lines[i]["scene_index"] != lines[start]["scene_index"]:
            shots.append((lines[start]["scene_index"], start, i))
            start = i
    return shots


def motion_filter_expr(motion: str, frames: int) -> tuple[str, str, str]:
    """motion에 맞는 zoompan의 z(줌)/x/y(팬) 표현식을 돌려준다.
    zoompan의 x/y 표현식 평가 컨텍스트에는 'd'(옵션값) 변수가 없어서, 팬 이동 계산에 필요한
    총 프레임 수는 여기서 리터럴 숫자로 박아 넣는다(on 변수만 프레임마다 바뀐다)."""
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


def render_shot(image_path: Path, motion: str, duration: float, out_path: Path):
    """이미지 한 장에 motion 효과를 적용해 duration 길이의 무음 비디오 클립을 만든다.
    이미지는 화면 전체가 아니라 가운데 IMAGE_AREA_H 영역에만 채우고, 위/아래는 검은 바로
    패딩해서 제목·자막이 얹힐 공간을 만든다."""
    frames = max(1, round(duration * FPS))
    z, x, y = motion_filter_expr(motion, frames)
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
        print(result.stderr[-3000:])
        sys.exit(f"\n✗ 장면 렌더 실패({image_path})")


def build_reel(script_path: Path, audio_dir: Path, out_path: Path, bgm_path: Path | None, bgm_volume: float):
    script = json.loads(script_path.read_text(encoding="utf-8"))
    lines = script.get("lines", [])
    scenes = script.get("scenes", [])
    if len(lines) < 1:
        sys.exit(f"대본에 줄이 없습니다: {script_path}")
    if len(scenes) < 1:
        sys.exit(f"대본에 장면(scenes)이 없습니다: {script_path}")

    audios, durations = [], []
    for i in range(1, len(lines) + 1):
        audio_path = find_line_audio(audio_dir, i)
        audios.append(audio_path)
        durations.append(probe_duration(audio_path))

    shots = group_into_shots(lines)
    total_duration = sum(durations)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        shot_paths = []
        for si, (scene_idx, start, end) in enumerate(shots):
            scene = scenes[scene_idx]
            image_path = scene.get("resolved_image_path")
            if not image_path or not Path(image_path).exists():
                sys.exit(f"장면 {scene_idx + 1}의 이미지가 없습니다 — 먼저 「장면 이미지 준비」를 완료하세요.")
            shot_duration = sum(durations[start:end])
            shot_path = tmp / f"shot_{si:02d}.mp4"
            render_shot(Path(image_path), scene.get("motion", "static"), shot_duration, shot_path)
            shot_paths.append(shot_path)
            print(f"  샷 {si + 1}/{len(shots)}: 장면 {scene_idx + 1} ({scene.get('motion', 'static')}), {shot_duration:.1f}초")

        cmd = ["ffmpeg", "-y"]
        for p in shot_paths:
            cmd += ["-i", str(p)]
        for a in audios:
            cmd += ["-i", str(a)]
        bgm_idx = None
        if bgm_path is not None:
            bgm_idx = len(shot_paths) + len(audios)
            cmd += ["-i", str(bgm_path)]

        filters = []
        v_labels = "".join(f"[{i}:v]" for i in range(len(shot_paths)))
        filters.append(f"{v_labels}concat=n={len(shot_paths)}:v=1:a=0[vconcat]")

        # 제목(상단 고정, 2줄 — 1번째 흰색/2번째 강조 노란색) + 자막(하단, 대사 줄마다 타이밍 맞춰
        # 교체, 길면 2줄) — drawtext를 순서대로 체이닝한다(자막샘플/ 참고 스타일, 2026-07-30).
        font_escaped = ffmpeg_escape_path(FONT_PATH)
        cur_label = "vconcat"

        title_lines = [
            t for t in (script.get("title_line1", ""), script.get("title_line2", "")) if (t or "").strip()
        ]
        title_colors = ["white", "yellow"]
        if title_lines:
            ys = stacked_line_ys(0, TITLE_BAR_H, len(title_lines), TITLE_FONTSIZE, LINE_GAP)
            for idx, (txt, y) in enumerate(zip(title_lines, ys)):
                title_file = tmp / f"title_{idx}.txt"
                title_file.write_text(txt.strip(), encoding="utf-8")
                out_label = f"vtitle{idx}"
                color = title_colors[idx] if idx < len(title_colors) else "white"
                filters.append(
                    f"[{cur_label}]drawtext=fontfile='{font_escaped}':textfile='{ffmpeg_escape_path(title_file)}':"
                    f"fontsize={TITLE_FONTSIZE}:fontcolor={color}:x=(w-text_w)/2:y={y}[{out_label}]"
                )
                cur_label = out_label

        cum_time = 0.0
        for i, line in enumerate(lines):
            start, end = cum_time, cum_time + durations[i]
            cum_time = end
            sublines = wrap_two_lines(line.get("text", ""), SUBTITLE_MAX_CHARS)
            ys = stacked_line_ys(HEIGHT - SUBTITLE_BAR_H, SUBTITLE_BAR_H, len(sublines), SUBTITLE_FONTSIZE, LINE_GAP)
            for j, (txt, y) in enumerate(zip(sublines, ys)):
                line_file = tmp / f"subtitle_{i:02d}_{j}.txt"
                line_file.write_text(txt, encoding="utf-8")
                out_label = f"vsub{i}_{j}"
                filters.append(
                    f"[{cur_label}]drawtext=fontfile='{font_escaped}':textfile='{ffmpeg_escape_path(line_file)}':"
                    f"fontsize={SUBTITLE_FONTSIZE}:fontcolor=white:x=(w-text_w)/2:y={y}:"
                    f"enable='between(t,{start:.3f},{end:.3f})'[{out_label}]"
                )
                cur_label = out_label
        final_video_label = cur_label

        a_labels = "".join(f"[{len(shot_paths) + i}:a]" for i in range(len(audios)))
        filters.append(f"{a_labels}concat=n={len(audios)}:v=0:a=1[narr]")

        if bgm_path is not None:
            filters.append(
                f"[{bgm_idx}:a]aloop=loop=-1:size=2e9,atrim=0:{total_duration:.3f},"
                f"volume={bgm_volume},afade=t=out:st={max(total_duration - 1, 0):.3f}:d=1[bgm]"
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

        print(f"줄 수: {len(lines)}  장면 수: {len(scenes)}  샷 수: {len(shots)}  총 길이: {total_duration:.1f}초")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(result.stderr[-3000:])
            sys.exit("\n✗ ffmpeg 실행 실패 — 위 로그 확인")

    print(f"\n완료 → {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("script_json", help="data/reel_script/<id>.json 경로")
    ap.add_argument("audio_dir", help="data/reel_audio/<id>/ 폴더 경로 (line_01.mp3 등)")
    ap.add_argument("out", help="출력 mp4 경로")
    ap.add_argument("--bgm", default=None, help="배경음악 파일 경로 (선택)")
    ap.add_argument("--bgm-volume", type=float, default=0.15, help="배경음악 상대 볼륨 (기본 0.15)")
    args = ap.parse_args()

    script_path = Path(args.script_json)
    audio_dir = Path(args.audio_dir)
    out_path = Path(args.out)
    bgm_path = Path(args.bgm) if args.bgm else None

    if not script_path.exists():
        sys.exit(f"대본 파일 없음: {script_path}")
    if not audio_dir.exists():
        sys.exit(f"오디오 폴더 없음: {audio_dir}")
    if bgm_path is not None and not bgm_path.exists():
        sys.exit(f"배경음악 파일 없음: {bgm_path}")

    build_reel(script_path, audio_dir, out_path, bgm_path, args.bgm_volume)
