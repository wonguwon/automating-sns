#!/usr/bin/env python3
"""5단계 — 콘텐츠 렌더 (PNG). data/content/<id>.json → 카드뉴스/<id>/ 에 Render.py로 캐러셀·스토리 PNG 생성."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import subprocess

import streamlit as st

from pipeline_common import CONTENT_DIR, HERE, OUT_ROOT, content_id_widget
from pipeline_state import load_state, save_state

st.title("5단계 — 콘텐츠 렌더")

content_id = content_id_widget()
content_path = CONTENT_DIR / f"{content_id}.json"

if not content_path.exists():
    st.info("이 콘텐츠 ID에는 content.json이 없습니다. 먼저 3~4단계를 완료하세요.")
else:
    content = json.loads(content_path.read_text(encoding="utf-8"))

    if st.button("콘텐츠 렌더", type="primary"):
        try:
            out_dir = OUT_ROOT / content_id
            out_dir.mkdir(parents=True, exist_ok=True)
            render_content_path = out_dir / "content.json"
            render_content_path.write_text(
                json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            with st.spinner("렌더 중..."):
                result = subprocess.run(
                    [sys.executable, str(HERE / "Render.py"), str(render_content_path), str(out_dir)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )

            if result.returncode != 0:
                st.error("렌더 실패")
                st.code(result.stderr or result.stdout)
            else:
                st.success("렌더 완료 — 6단계로 이동하세요.")
                save_state(content_id, render_out_dir=str(out_dir))
                # history.json 기록은 이번 구조 개편 범위에서 의도적으로 껐다 —
                # V3 데이터 구조가 다시 잡힐 때 함께 재설계하기로 함(사용자 결정, 2026-07-28).
        except Exception as e:
            st.error(f"렌더 실패: {e}")

    manifest = load_state(content_id)
    out_dir_str = manifest.get("render_out_dir")
    out_dir = Path(out_dir_str) if out_dir_str else (OUT_ROOT / content_id)
    if out_dir.exists():
        carousel_dir = out_dir / "carousel"
        story_dir = out_dir / "story"
        if carousel_dir.exists():
            imgs = sorted(carousel_dir.glob("*.png"))
            if imgs:
                st.caption(f"캐러셀 (4:5) · {len(imgs)}장")
                for col, img in zip(st.columns(len(imgs)), imgs):
                    col.image(str(img))
        if story_dir.exists():
            imgs = sorted(story_dir.glob("*.png"))
            if imgs:
                st.caption(f"스토리 (9:16) · {len(imgs)}장")
                for col, img in zip(st.columns(len(imgs)), imgs):
                    col.image(str(img))
