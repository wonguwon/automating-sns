#!/usr/bin/env python3
"""2단계 — 딥리서치. 선택된 후보(매니페스트) 또는 과거 candidates 파일에서 직접 골라 실행."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json

import streamlit as st

from pipeline_common import (
    CAND_DIR,
    RESEARCH_DIR,
    content_id_widget,
    get_client,
    run_deep_research,
    show_research_dialog,
)
from pipeline_state import load_state, save_state

st.title("2단계 — 딥리서치")

content_id = content_id_widget()
manifest = load_state(content_id)
candidate = manifest.get("candidate")

if not candidate:
    st.info("이 콘텐츠 ID에는 저장된 후보가 없습니다. 1단계에서 진행했거나, 아래에서 과거 후보 파일을 직접 골라 시작할 수 있습니다.")
    past_files = sorted(CAND_DIR.glob("*.json"), reverse=True)
    if not past_files:
        st.warning("data/candidates/에 후보 파일이 없습니다. 먼저 1단계를 실행하세요.")
    else:
        picked_file = st.selectbox("후보 파일", past_files, format_func=lambda p: p.stem, key="research_cand_file")
        items = json.loads(picked_file.read_text(encoding="utf-8")) if picked_file else []
        if items:
            labels = [f"{c.get('id', '?')} · {c.get('title', '(제목 없음)')}" for c in items]
            idx = st.radio("후보 선택", options=range(len(items)), format_func=lambda i: labels[i], key="research_cand_idx")
            picked_candidate = items[idx]
            if st.button("이 후보로 진행", type="primary"):
                save_state(content_id, candidate=picked_candidate)
                st.rerun()
else:
    st.markdown(f"**선택된 후보**: {candidate.get('title', '(제목 없음)')}")
    with st.expander("후보 상세"):
        st.markdown(f"**one_line**: {candidate.get('one_line', '')}")
        st.markdown(f"**angle**: {candidate.get('angle', '')}")
        st.markdown(f"**source**: {candidate.get('source', '')}")

    st.divider()

    if st.button("딥리서치 실행", type="primary"):
        try:
            client = get_client()
            with st.spinner("원문 조회 및 딥리서치 중..."):
                md_part, pairs, fetched = run_deep_research(client, candidate)

            RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
            note_path = RESEARCH_DIR / f"{content_id}.md"
            note_path.write_text(md_part, encoding="utf-8")

            pairs_path = RESEARCH_DIR / f"{content_id}.pairs.json"
            if pairs is not None:
                pairs_path.write_text(json.dumps(pairs, ensure_ascii=False, indent=2), encoding="utf-8")

            save_state(
                content_id,
                research_pairs=pairs,
                research_note_path=str(note_path),
            )
            st.session_state["research_md"] = md_part

            if not fetched:
                st.caption("원문을 가져오지 못해 후보 요약만으로 진행했습니다.")

            if pairs is None:
                st.error("PAIRS JSON 파싱 실패 — 「딥리서치 결과 보기」에서 원문을 확인하세요. (pairs 파일은 저장되지 않았습니다)")
            else:
                st.success(f"딥리서치 완료 — 근거 {len(pairs)}개 확보. 3단계로 이동하세요.")
        except Exception as e:
            st.error(f"딥리서치 실패: {e}")

    note_path = RESEARCH_DIR / f"{content_id}.md"
    if manifest.get("research_note_path") or st.session_state.get("research_md") or note_path.exists():
        if st.button("딥리서치 결과 보기"):
            md_text = st.session_state.get("research_md") or note_path.read_text(encoding="utf-8")
            show_research_dialog(md_text)
