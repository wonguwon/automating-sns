#!/usr/bin/env python3
"""3단계 — 콘텐츠 JSON 생성/편집. 매니페스트의 research_pairs 또는 .pairs.json 파일, 없으면 수동 입력."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json

import streamlit as st

from pipeline_common import CONTENT_DIR, RESEARCH_DIR, content_id_widget, generate_content_json, get_client, show_json_dialog
from pipeline_state import load_state, save_state

st.title("3단계 — 콘텐츠 JSON")

content_id = content_id_widget()
manifest = load_state(content_id)

content_key = f"content_json::{content_id}"
content_path = CONTENT_DIR / f"{content_id}.json"

if content_key not in st.session_state:
    st.session_state[content_key] = (
        json.loads(content_path.read_text(encoding="utf-8")) if content_path.exists() else None
    )

pairs = manifest.get("research_pairs")
pairs_path = RESEARCH_DIR / f"{content_id}.pairs.json"
if not pairs and pairs_path.exists():
    pairs = json.loads(pairs_path.read_text(encoding="utf-8"))

if not pairs:
    st.info("이 콘텐츠 ID에는 딥리서치 근거(pairs)가 없습니다. 2단계를 먼저 실행하거나, 아래에 (content, source) 쌍 JSON을 직접 붙여넣으세요.")
    manual = st.text_area(
        'pairs JSON 직접 입력 — 예: [{"content": "...", "source": "https://..."}]',
        height=200, key="manual_pairs_input",
    )
    if st.button("이 pairs 사용"):
        try:
            parsed = json.loads(manual)
        except json.JSONDecodeError as e:
            st.error(f"JSON 파싱 실패: {e}")
        else:
            save_state(content_id, research_pairs=parsed)
            st.rerun()
else:
    st.caption(f"근거 {len(pairs)}개 확보됨")

    if st.button("콘텐츠 JSON 생성", type="primary"):
        try:
            client = get_client()
            with st.spinner("content.json 생성 중..."):
                content = generate_content_json(client, pairs, content_id)
            st.session_state[content_key] = content
            CONTENT_DIR.mkdir(parents=True, exist_ok=True)
            content_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
            save_state(content_id, content_path=str(content_path))
            st.success("생성 완료 — 4단계로 이동하세요.")
        except Exception as e:
            st.error(f"생성 실패: {e}")

if st.session_state.get(content_key):
    if st.button("JSON 보기/편집"):
        show_json_dialog(st.session_state[content_key], content_key)

    # 편집 다이얼로그에서 적용을 누르면 session_state[content_key]가 갱신되고 rerun된다.
    # data/content/<id>.json이 원본(canonical)이므로 여기서 매번 그대로 반영해 동기화를 유지한다.
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    content_path.write_text(
        json.dumps(st.session_state[content_key], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    save_state(content_id, content_path=str(content_path))
