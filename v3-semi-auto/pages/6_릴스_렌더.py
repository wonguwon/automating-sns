#!/usr/bin/env python3
"""6단계 — 릴스 렌더 (MP4). 5단계 out_dir(story/)와 배경음악을 Render_reel.py로 합성."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import subprocess

import streamlit as st

from pipeline_common import HERE, MUSIC_DIR, MUSIC_EXTS, OUT_ROOT, content_id_widget
from pipeline_state import load_state, save_state

st.title("6단계 — 릴스 렌더")

content_id = content_id_widget()
manifest = load_state(content_id)

out_dir_str = manifest.get("render_out_dir")
out_dir = Path(out_dir_str) if out_dir_str else (OUT_ROOT / content_id)
story_dir = out_dir / "story"

if not story_dir.exists():
    st.info(f"이 콘텐츠 ID의 story 폴더를 찾지 못했습니다 ({story_dir}). 먼저 5단계에서 콘텐츠를 렌더하세요.")
else:
    music_files = []
    if MUSIC_DIR.exists():
        for pattern in MUSIC_EXTS:
            music_files.extend(MUSIC_DIR.glob(pattern))
    music_files = sorted(music_files)

    if not music_files:
        st.warning(f"`{MUSIC_DIR.name}/` 폴더에 배경음악 파일이 없습니다.")
    else:
        picked_music = st.selectbox("배경음악", music_files, format_func=lambda p: p.name, key="reel_music_pick")
        if st.button("릴스 생성", type="primary"):
            reel_path = out_dir / "reel.mp4"
            try:
                with st.spinner("릴스 생성 중... (ffmpeg)"):
                    result = subprocess.run(
                        [
                            sys.executable, str(HERE / "Render_reel.py"),
                            "--images", str(story_dir),
                            "--music", str(picked_music),
                            "--out", str(reel_path),
                        ],
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                    )
                if result.returncode != 0:
                    st.error("릴스 생성 실패")
                    st.code(result.stderr or result.stdout)
                else:
                    st.success("완료")
                    save_state(content_id, reel_path=str(reel_path))
                    st.video(str(reel_path))
            except Exception as e:
                st.error(f"릴스 생성 실패: {e}")

    reel_path_str = manifest.get("reel_path")
    if reel_path_str and Path(reel_path_str).exists():
        st.video(reel_path_str)

st.divider()
st.caption("업로드는 인스타 앱에서 직접 진행하세요.")
