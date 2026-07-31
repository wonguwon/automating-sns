#!/usr/bin/env python3
"""
칼퇴각 릴스 조립기
------------------------------------------------
story/ 폴더의 9:16 PNG 5장을 받아서
  - 첫 장 3초, 나머지 4장 각 2초
  - 전환 0.5초 크로스페이드
  - 배경음악 오버레이 (길면 자르고, 짧으면 반복)
으로 이어붙인 MP4 하나를 만든다.

사전 준비: ffmpeg가 PATH에 있어야 한다.
  Windows: choco install ffmpeg  (또는 ffmpeg.org에서 받아 PATH 등록)
  설치 확인: ffmpeg -version

사용법:
    python3 render_reel.py --images 카드뉴스/20260719-01/story --music assets/bgm1.mp3
    python3 render_reel.py --images ...\\story --music ...\\bgm1.mp3 --out reel.mp4
    python3 render_reel.py --images ...\\story --music ...\\bgm1.mp3 \\
        --first 3.0 --other 2.0 --transition 0.5
------------------------------------------------
"""
import argparse
import subprocess
import sys
from pathlib import Path

# Windows 콘솔 기본 코드페이지(cp949)는 ✓/✗/⚠ 같은 기호를 인코딩하지 못한다.
# CLI로 직접 실행될 때를 대비해 stdout/stderr를 UTF-8로 고정한다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

FPS = 30
WIDTH, HEIGHT = 1080, 1920


def build_reel(images_dir: Path, music_path: Path, out_path: Path,
                first: float, other: float, transition: float):
    images = sorted(images_dir.glob("*.png"))
    if len(images) < 2:
        sys.exit(f"이미지가 2장 미만입니다: {images_dir}")

    n = len(images)
    visible = [first] + [other] * (n - 1)

    # 각 입력 클립의 실제 길이 계산 (전환에 쓰이는 만큼 여유를 더한다)
    clip_len = []
    for i in range(n):
        extra = 0.0
        if i > 0:            # 이전 클립과의 전환을 받는 쪽
            extra += transition
        if i < n - 1:         # 다음 클립과의 전환을 내보내는 쪽
            extra += transition
        clip_len.append(visible[i] + extra)

    # ---- ffmpeg 입력 구성 ----
    cmd = ["ffmpeg", "-y"]
    for img, dur in zip(images, clip_len):
        cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(img)]
    cmd += ["-i", str(music_path)]

    # ---- filter_complex: 포맷 통일 후 순차 xfade ----
    filters = []
    for i in range(n):
        filters.append(f"[{i}:v]fps={FPS},format=yuv420p,setsar=1[v{i}]")

    cum_label = "v0"
    cum_duration = clip_len[0]
    for i in range(1, n):
        offset = cum_duration - transition
        out_label = f"vx{i}"
        filters.append(
            f"[{cum_label}][v{i}]xfade=transition=fade:duration={transition:.3f}:"
            f"offset={offset:.3f}[{out_label}]"
        )
        cum_duration = cum_duration + clip_len[i] - transition
        cum_label = out_label

    total_duration = cum_duration

    # ---- 오디오: 길면 자르고 짧으면 반복, 끝에 페이드아웃 ----
    audio_idx = n
    filters.append(
        f"[{audio_idx}:a]aloop=loop=-1:size=2e9,"
        f"atrim=0:{total_duration:.3f},"
        f"afade=t=out:st={max(total_duration - 1, 0):.3f}:d=1[aout]"
    )

    filter_complex = ";".join(filters)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", f"[{cum_label}]",
        "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(FPS),
        "-s", f"{WIDTH}x{HEIGHT}",
        "-t", f"{total_duration:.3f}",
        str(out_path),
    ]

    print(f"클립 길이: {[round(x,2) for x in clip_len]}  (초)")
    print(f"예상 총 길이: {total_duration:.1f}초")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(result.stderr[-3000:])
        sys.exit("\n✗ ffmpeg 실행 실패 — 위 로그 확인")

    print(f"\n완료 → {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True, help="story/ 폴더 경로 (9:16 PNG 5장)")
    ap.add_argument("--music", required=True, help="배경음악 파일 경로 (mp3 등)")
    ap.add_argument("--out", default=None, help="출력 mp4 경로 (기본: images 폴더 옆 reel.mp4)")
    ap.add_argument("--first", type=float, default=3.0, help="첫 장 노출 시간(초)")
    ap.add_argument("--other", type=float, default=2.0, help="나머지 장 노출 시간(초)")
    ap.add_argument("--transition", type=float, default=0.5, help="전환 시간(초)")
    args = ap.parse_args()

    images_dir = Path(args.images)
    music_path = Path(args.music)
    out_path = Path(args.out) if args.out else images_dir.parent / "reel.mp4"

    if not images_dir.exists():
        sys.exit(f"이미지 폴더 없음: {images_dir}")
    if not music_path.exists():
        sys.exit(f"음악 파일 없음: {music_path}")

    build_reel(images_dir, music_path, out_path, args.first, args.other, args.transition)