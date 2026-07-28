#!/usr/bin/env python3
"""컨텐츠 수집. 소스 그룹 관리(sources/*.json) + RSS 수집. GPT 선별은 딥리서치 단계에서 한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from pipeline_common import get_client
from sources_store import (
    DEFAULT_FEED_PROMPT,
    add_feed,
    collect_group_items,
    create_group,
    generate_feeds_from_prompt,
    group_label,
    health_check_group,
    list_groups,
    list_rss_collections,
    load_group,
    load_rss_collection,
    remove_feed,
    save_group,
    save_rss_collection,
    set_feed_enabled,
    update_feed,
)

st.title("컨텐츠 수집")


@st.dialog("새 그룹 만들기")
def new_group_dialog():
    new_name = st.text_input("새 그룹 이름", key="new_group_name_input")
    use_gpt = st.checkbox("GPT로 피드 자동 채우기", value=True, key="new_group_use_gpt")
    prompt = None
    if use_gpt:
        st.session_state.setdefault("new_group_prompt_input", DEFAULT_FEED_PROMPT)
        prompt = st.text_area("피드 수집 프롬프트", height=220, key="new_group_prompt_input")
        st.caption("GPT-5.5 호출 1회(과금)가 발생합니다. 실제로 존재하는 URL만 쓰도록 프롬프트에 명시되어 있지만, 만들어진 피드는 자동으로 헬스체크까지 돌려 결과를 표시합니다.")

    if st.button("만들기", type="primary"):
        if not new_name.strip():
            st.error("그룹 이름을 입력하세요.")
        else:
            new_path = create_group(new_name)
            st.session_state["group_select_override"] = new_path
            st.session_state["open_group"] = str(new_path)

            if not use_gpt:
                st.session_state.pop("new_group_name_input", None)
                st.session_state.pop("new_group_prompt_input", None)
                st.rerun()
            else:
                try:
                    client = get_client()
                    with st.spinner("GPT로 피드 조사 중..."):
                        feeds = generate_feeds_from_prompt(client, prompt)
                    data = load_group(new_path)
                    data["feeds"] = feeds
                    save_group(new_path, data)
                    with st.spinner("헬스체크 중..."):
                        health_check_group(new_path)
                except Exception as e:
                    st.error(f"GPT 피드 생성 실패: {e} — 그룹은 빈 채로 만들어졌습니다. 아래에서 수동으로 추가하거나 다시 시도하세요.")
                else:
                    st.session_state.pop("new_group_name_input", None)
                    st.session_state.pop("new_group_prompt_input", None)
                    st.rerun()


@st.dialog("리소스 추가")
def add_feed_dialog(group_path: Path):
    f_name = st.text_input("name *")
    f_url = st.text_input("url *")
    f_tier = st.text_input("tier * (예: 1, newsletter, kr, yt)")
    f_note = st.text_input("note (선택)")
    f_enabled = st.checkbox("enabled", value=True)
    if st.button("추가", type="primary"):
        if not (f_name.strip() and f_url.strip() and f_tier.strip()):
            st.error("name, url, tier는 필수입니다.")
        else:
            add_feed(group_path, f_name, f_url, f_tier, f_enabled, f_note)
            st.rerun()


@st.dialog("리소스 수정")
def edit_feed_dialog(group_path: Path, index: int, feed: dict):
    f_name = st.text_input("name *", value=feed.get("name", ""))
    f_url = st.text_input("url *", value=feed.get("url", ""))
    f_tier = st.text_input("tier * (예: 1, newsletter, kr, yt)", value=str(feed.get("tier", "")))
    f_note = st.text_input("note (선택)", value=feed.get("note", ""))
    f_enabled = st.checkbox("enabled", value=feed.get("enabled", True))
    if st.button("저장", type="primary"):
        if not (f_name.strip() and f_url.strip() and f_tier.strip()):
            st.error("name, url, tier는 필수입니다.")
        else:
            update_feed(group_path, index, f_name, f_url, f_tier, f_enabled, f_note)
            st.rerun()


# ============================================================
# 리소스 그룹 관리
# ============================================================
title_row = st.columns([4, 1], vertical_alignment="center")
title_row[0].subheader("리소스 그룹")
with title_row[1]:
    if st.button("+ 새 그룹 만들기"):
        new_group_dialog()

if "group_select_override" in st.session_state:
    st.session_state["group_select"] = st.session_state.pop("group_select_override")

groups = list_groups()

if not groups:
    st.info("리소스 그룹이 없습니다. 위에서 새 그룹을 만드세요.")
else:
    select_row = st.columns([3, 1], vertical_alignment="bottom")
    with select_row[0]:
        picked_path = st.selectbox(
            "그룹 선택", groups, format_func=group_label, key="group_select", filter_mode=None
        )
    with select_row[1]:
        if st.button("가져오기"):
            st.session_state["open_group"] = str(picked_path)

open_group_str = st.session_state.get("open_group")
if open_group_str:
    open_path = Path(open_group_str)
    if not open_path.exists():
        st.warning("로드된 그룹 파일을 찾을 수 없습니다 — 다시 가져오세요.")
        st.session_state.pop("open_group", None)
    else:
        data = load_group(open_path)
        info_row = st.columns([3, 1, 1], vertical_alignment="center")
        info_row[0].markdown(f"**{data.get('name', open_path.stem)}** · 피드 {len(data['feeds'])}개")
        with info_row[1]:
            if st.button("+ 리소스 추가"):
                add_feed_dialog(open_path)
        with info_row[2]:
            if st.button("헬스체크"):
                with st.spinner("피드 상태 확인 중..."):
                    health_check_group(open_path)
                st.success("헬스체크 완료")
        if data.get("_last_health_check"):
            st.caption(f"마지막 헬스체크: {data['_last_health_check']}")

        if not data["feeds"]:
            st.caption("이 그룹에는 아직 피드가 없습니다.")
        else:
            header = st.columns([3, 1, 1, 1, 1])
            header[0].markdown("**name**")
            header[1].markdown("**tier**")
            header[2].markdown("**enabled**")
            header[3].markdown("**수정**")
            header[4].markdown("**제거**")
            for i, feed in enumerate(data["feeds"]):
                row = st.columns([3, 1, 1, 1, 1])
                row[0].markdown(feed["name"])
                verified = feed.get("verified")
                if verified:
                    row[0].caption(f"{verified.get('status')} · {verified.get('checked', '')}")
                row[1].write(feed.get("tier", ""))

                enabled_key = f"enabled_{open_path.stem}_{i}"

                def _on_toggle(p=open_path, idx=i, k=enabled_key):
                    set_feed_enabled(p, idx, st.session_state[k])

                row[2].checkbox(
                    "enabled", value=feed.get("enabled", False), key=enabled_key,
                    label_visibility="collapsed", on_change=_on_toggle,
                )
                if row[3].button("수정", key=f"edit_{open_path.stem}_{i}"):
                    edit_feed_dialog(open_path, i, feed)
                if row[4].button("제거", key=f"remove_{open_path.stem}_{i}"):
                    remove_feed(open_path, i)
                    st.rerun()

st.divider()

# ============================================================
# RSS 수집 (위 리소스 그룹의 enabled 피드에서 원본 그대로 수집)
# GPT 선별은 여기서 하지 않는다 — 딥리서치 단계로 넘어간다.
# ============================================================
st.subheader("RSS 수집")

loaded_group_path = None
enabled_count = 0
if open_group_str and Path(open_group_str).exists():
    loaded_group_path = Path(open_group_str)
    loaded_group_data = load_group(loaded_group_path)
    enabled_count = sum(1 for f in loaded_group_data["feeds"] if f.get("enabled", False))

if not loaded_group_path:
    st.info("위에서 리소스 그룹을 '가져오기'로 먼저 불러오세요.")
elif enabled_count == 0:
    st.info("불러온 그룹에 활성화된(enabled) 피드가 없습니다 — 위 목록에서 최소 1개를 켜세요.")

if st.button("RSS 수집", type="primary", disabled=enabled_count == 0):
    with st.spinner(f"활성 피드 {enabled_count}개에서 최근 24시간 수집 중..."):
        items = collect_group_items(loaded_group_path)
        out_path = save_rss_collection(loaded_group_path, items)
    st.session_state["rss_items"] = items
    st.session_state["rss_items_path"] = str(out_path)
    st.success(f"{len(items)}건 수집 — {out_path.name}에 저장됨")

if loaded_group_path:
    past_collections = list_rss_collections(loaded_group_path)
    if past_collections:
        load_row = st.columns([3, 1], vertical_alignment="bottom")
        with load_row[0]:
            picked_collection = st.selectbox(
                "이 그룹의 과거 수집 결과",
                past_collections,
                format_func=lambda p: f"{p.stem} · {len(load_rss_collection(p))}건",
                key="rss_collection_pick",
                filter_mode=None,
            )
        with load_row[1]:
            if st.button("불러오기", key="load_rss_collection_btn"):
                st.session_state["rss_items"] = load_rss_collection(picked_collection)
                st.session_state["rss_items_path"] = str(picked_collection)

if st.session_state.get("rss_items"):
    st.caption(f"저장 위치: {st.session_state.get('rss_items_path')}")
    st.dataframe(st.session_state["rss_items"], width="stretch")
