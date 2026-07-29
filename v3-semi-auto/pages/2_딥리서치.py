#!/usr/bin/env python3
"""딥리서치. RSS 수집 데이터에서 체크한 항목을 GPT로 선별(그룹별 저장) → 후보 선택 → 딥리서치 실행·저장."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json

import streamlit as st

from pipeline_common import (
    RESEARCH_DIR,
    build_research_prompt,
    get_client,
    list_research_notes,
    run_research_prompt,
    show_research_dialog,
)
from pipeline_state import load_state, save_state
from sources_store import (
    SELECT_OUTPUT_SCHEMA,
    group_label,
    list_candidate_files,
    list_groups,
    list_rss_collections,
    load_candidates,
    load_rss_collection,
    load_select_prompt_state,
    save_candidates,
    save_select_prompt_state,
    select_candidates_from_items,
)

st.title("딥리서치")


@st.dialog("GPT 선별 프롬프트", width="large")
def gpt_select_dialog(group_path: Path, items: list[dict]):
    if "select_persona_input" not in st.session_state:
        saved = load_select_prompt_state()
        st.session_state["select_persona_input"] = saved["persona"]
        st.session_state["select_rules_input"] = saved["rules"]

    persona = st.text_area("계정/독자 프롬프트 (수정 가능)", height=100, key="select_persona_input")
    st.caption("이 계정의 성격과 독자에 맞게 자유롭게 작성하세요 — 계정이 바뀌지 않는 한 보통 그대로 재사용합니다.")

    rules = st.text_area("선별 기준 (수정 가능)", height=220, key="select_rules_input")
    st.caption("병합·중복 제거·우선순위 등 선별 기준만 적으면 됩니다 — 아래 출력 형식은 고정으로 항상 자동 적용됩니다.")

    with st.expander("출력 형식 (고정 — 코드에서 관리, 항상 자동 적용됨)"):
        st.code(SELECT_OUTPUT_SCHEMA, language=None)

    st.caption(f"위 내용을 모두 합친 것 + 체크한 {len(items)}건이 GPT-5.5에 전달됩니다. 마지막으로 성공한 선별 기준은 자동으로 다음에도 이어서 채워집니다.")

    if st.button("선별 실행", type="primary"):
        combined_prompt = f"{persona}\n\n{rules}\n\n{SELECT_OUTPUT_SCHEMA}"
        try:
            client = get_client()
            with st.spinner("GPT로 선별 중..."):
                new_candidates = select_candidates_from_items(client, items, system_prompt=combined_prompt)
            out_path = save_candidates(group_path, new_candidates)
        except Exception as e:
            st.error(f"GPT 선별 실패: {e}")
        else:
            save_select_prompt_state(persona, rules)
            st.session_state["gpt_select_toast"] = f"후보 {len(new_candidates)}개 생성 — {out_path.name}에 저장됨"
            st.rerun()

if "gpt_select_toast" in st.session_state:
    st.toast(st.session_state.pop("gpt_select_toast"))

# 콘텐츠 ID를 사람이 직접 입력하지 않는다 — 후보 자체가 GPT 선별 단계에서 이미 고유 id(YYYYMMDD-NN)를
# 받으므로, 「이 후보로 진행」을 누른 후보의 id를 그대로 매니페스트·딥리서치 산출물 파일명으로 쓴다.
active_id = st.session_state.get("active_candidate_id")
manifest = load_state(active_id) if active_id else {}
candidate = manifest.get("candidate")

groups = list_groups()

# ============================================================
# 섹션 1 — RSS 데이터에서 GPT 선별 (그룹별로 저장)
# ============================================================
st.subheader("RSS 데이터에서 GPT 선별")

if not groups:
    st.info("리소스 그룹이 없습니다. 먼저 컨텐츠 수집 페이지에서 그룹을 만드세요.")
else:
    pick_row = st.columns([1, 1])
    with pick_row[0]:
        group_path_1 = st.selectbox(
            "그룹 선택", groups, format_func=group_label, key="dr_group_select_1", filter_mode=None
        )
    collections = list_rss_collections(group_path_1) if group_path_1 else []
    with pick_row[1]:
        picked_collection = st.selectbox(
            "RSS 수집 결과",
            collections,
            format_func=lambda p: f"{p.stem} · {len(load_rss_collection(p))}건",
            key="dr_rss_collection_pick",
            filter_mode=None,
            disabled=not collections,
        )

    if not collections:
        st.info("이 그룹의 RSS 수집 결과가 없습니다. 컨텐츠 수집 페이지에서 먼저 RSS 수집을 실행하세요.")
    else:
        rss_items = load_rss_collection(picked_collection) if picked_collection else []

        if not rss_items:
            st.caption("이 수집 결과에는 항목이 없습니다.")
        else:
            # data_editor는 이미 그려진 위젯의 체크 상태를 st.session_state로 직접 덮어쓸 수 없다
            # (Streamlit 정책 위반 에러) — 그래서 "전체 선택/해제"는 기본값과 위젯 key의 버전을 함께
            # 바꿔 매번 새 위젯으로 다시 그리는 방식으로 구현한다.
            default_key = f"dr_select_default_{picked_collection.stem}"
            version_key = f"dr_select_version_{picked_collection.stem}"
            default_selected = st.session_state.get(default_key, False)
            version = st.session_state.get(version_key, 0)
            editor_key = f"dr_select_editor_{picked_collection.stem}_{version}"
            items_for_edit = [{"선택": default_selected, **it} for it in rss_items]

            toolbar = st.columns([4, 1, 1])
            toolbar[0].caption(f"{len(rss_items)}건 — 카드뉴스 소재로 쓸 항목을 체크하세요")
            if toolbar[1].button("전체 선택", key=f"select_all_{picked_collection.stem}"):
                st.session_state[default_key] = True
                st.session_state[version_key] = version + 1
                st.rerun()
            if toolbar[2].button("전체 해제", key=f"select_none_{picked_collection.stem}"):
                st.session_state[default_key] = False
                st.session_state[version_key] = version + 1
                st.rerun()

            edited_items = st.data_editor(
                items_for_edit,
                width="stretch",
                hide_index=True,
                column_config={"선택": st.column_config.CheckboxColumn("선택")},
                disabled=[k for k in items_for_edit[0].keys() if k != "선택"],
                key=editor_key,
            )
            selected_items = [
                {k: v for k, v in it.items() if k != "선택"} for it in edited_items if it.get("선택")
            ]

            if st.button(
                f"GPT로 선별 ({len(selected_items)}건 선택됨)",
                type="primary",
                disabled=not selected_items,
            ):
                gpt_select_dialog(group_path_1, selected_items)

st.divider()

# ============================================================
# 섹션 2 — 추천 후보에서 선택
# ============================================================
st.subheader("추천 후보에서 선택")

if not groups:
    st.info("리소스 그룹이 없습니다.")
else:
    group_path_2 = st.selectbox(
        "그룹 선택", groups, format_func=group_label, key="dr_group_select_2", filter_mode=None
    )
    cand_files = list_candidate_files(group_path_2) if group_path_2 else []

    if not cand_files:
        st.info("이 그룹의 후보 파일이 없습니다. 위 「RSS 데이터에서 GPT 선별」에서 먼저 실행하세요.")
    else:
        picked_cand_file = st.selectbox(
            "추천 후보 파일",
            cand_files,
            format_func=lambda p: f"{p.stem} · {len(load_candidates(p))}건",
            key="dr_cand_file_pick",
            filter_mode=None,
        )
        cand_items = load_candidates(picked_cand_file) if picked_cand_file else []

        if cand_items:
            labels = [f"{c.get('id', '?')} · {c.get('title', '(제목 없음)')}" for c in cand_items]
            idx = st.radio(
                "후보 선택", options=range(len(cand_items)), format_func=lambda i: labels[i], key="dr_cand_idx"
            )
            picked_candidate = cand_items[idx]
            with st.expander("후보 상세"):
                st.markdown(f"**one_line**: {picked_candidate.get('one_line', '')}")
                st.markdown(f"**why_now**: {picked_candidate.get('why_now', '')}")
                st.markdown(f"**angle**: {picked_candidate.get('angle', '')}")
                cand_sources = picked_candidate.get("sources") or [picked_candidate.get("source", "")]
                st.markdown(f"**sources** (딥리서치 근거로 전부 사용됨, {len(cand_sources)}건):")
                for u in cand_sources:
                    st.markdown(f"- {u}")
            if st.button("이 후보로 진행", type="primary"):
                picked_id = picked_candidate.get("id")
                save_state(picked_id, candidate=picked_candidate)
                st.session_state["active_candidate_id"] = picked_id
                st.session_state.pop(f"research_prompt_{picked_id}", None)
                st.rerun()

st.divider()

# ============================================================
# 섹션 3 — 딥리서치 실행 (후보가 선택된 경우에만)
# ============================================================
st.subheader("딥리서치 실행")

if not candidate:
    st.info("아직 선택된 후보가 없습니다. 위 「추천 후보에서 선택」에서 후보를 골라 「이 후보로 진행」을 누르세요.")
else:
    st.markdown(f"**선택된 후보**: {candidate.get('title', '(제목 없음)')} ({active_id})")
    with st.expander("후보 상세"):
        st.markdown(f"**one_line**: {candidate.get('one_line', '')}")
        st.markdown(f"**angle**: {candidate.get('angle', '')}")
        cand_sources = candidate.get("sources") or [candidate.get("source", "")]
        st.markdown(f"**sources** (딥리서치 근거로 전부 사용됨, {len(cand_sources)}건):")
        for u in cand_sources:
            st.markdown(f"- {u}")

    prompt_key = f"research_prompt_{active_id}"
    warn_key = f"{prompt_key}_fetch_warning"
    note_path = RESEARCH_DIR / f"{active_id}.md"

    def _rebuild_research_prompt():
        prompt_text, fetched = build_research_prompt(candidate)
        st.session_state[prompt_key] = prompt_text
        st.session_state[warn_key] = not fetched

    if prompt_key not in st.session_state:
        with st.spinner("기사 원문 조회 및 프롬프트 준비 중..."):
            _rebuild_research_prompt()

    if st.session_state.get(warn_key):
        st.caption("원문을 가져오지 못해 후보 요약만으로 프롬프트를 구성했습니다.")

    edited_prompt = st.text_area(
        "딥리서치 프롬프트 (수정 가능)", value=st.session_state[prompt_key], height=320, key=f"{prompt_key}_edit"
    )

    btn_row = st.columns([1, 1])
    with btn_row[0]:
        if st.button("프롬프트 새로고침 (원문 재조회)"):
            with st.spinner("기사 원문 재조회 중..."):
                _rebuild_research_prompt()
            st.rerun()
    with btn_row[1]:
        run_clicked = st.button("딥리서치 실행", type="primary")

    if run_clicked:
        try:
            client = get_client()
            with st.spinner("딥리서치 중..."):
                note_md = run_research_prompt(client, edited_prompt)

            RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
            note_path.write_text(note_md, encoding="utf-8")

            # 조사 노트가 유일한 산출물이다 — pairs 중간 산출물은 만들지 않는다(2026-07-29 결정,
            # 카드뉴스 생성 단계가 노트 전문 + 후보의 출처 URL 목록을 직접 읽는다).
            save_state(active_id, research_note_path=str(note_path))

            st.session_state["research_result_msg"] = (
                "success",
                f"딥리서치 완료 — {note_path.name} 저장됨. 카드뉴스 제작 페이지에서 이 노트를 선택해 진행하세요.",
            )
            st.rerun()
        except Exception as e:
            st.error(f"딥리서치 실패: {e}")

    result_msg = st.session_state.pop("research_result_msg", None)
    if result_msg:
        level, text = result_msg
        (st.success if level == "success" else st.error)(text)

st.divider()

# ============================================================
# 저장된 딥리서치 결과 열람 — 파일로 연결되는 구조라 지금 선택된 후보와 무관하게,
# data/research/*.md 파일만 있으면 언제든 골라서 볼 수 있다.
# ============================================================
st.subheader("저장된 딥리서치 결과")

research_notes = list_research_notes()

if not research_notes:
    st.caption("아직 저장된 딥리서치 결과가 없습니다.")
else:
    def _note_label(p: Path) -> str:
        try:
            first_line = next((ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()), "")
        except Exception:
            first_line = ""
        preview = (first_line[:50] + "…") if len(first_line) > 50 else first_line
        return f"{p.stem} · {preview}" if preview else p.stem

    note_row = st.columns([3, 1], vertical_alignment="bottom")
    with note_row[0]:
        picked_note = st.selectbox(
            "결과 파일", research_notes, format_func=_note_label, key="dr_research_note_pick"
        )
    with note_row[1]:
        if st.button("결과 보기", key="dr_show_research_note"):
            show_research_dialog(picked_note.read_text(encoding="utf-8"))
