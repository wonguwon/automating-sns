#!/usr/bin/env python3
"""카드뉴스 제작. 저장된 딥리서치 결과(파일)를 골라 카드뉴스를 만든다 — 템플릿 선택·JSON 생성·렌더는 이후 단계에서 붙인다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import subprocess

import streamlit as st

from pipeline_common import (
    CONTENT_DIR,
    HERE,
    OUT_ROOT,
    IMAGE_PROMPT_TEMPLATE,
    IMAGE_PROVIDERS,
    RESEARCH_DIR,
    TEMPLATES_DIR,
    build_content_json_prompt,
    generate_cover_image_raw,
    get_client,
    list_research_notes,
    list_template_examples,
    list_templates,
    run_content_json_prompt,
    run_insta_caption,
    show_json_dialog,
    show_research_dialog,
    to_local_path,
)
from pipeline_state import load_state, save_state

st.title("카드뉴스 제작")


@st.dialog("템플릿 예시", width="large")
def show_template_examples_dialog(template_dir: Path):
    st.markdown(f"**템플릿**: `{template_dir.name}`")
    examples = list_template_examples(template_dir)
    if not examples:
        st.info("예시 이미지가 아직 없습니다 — 이 템플릿으로 렌더한 결과를 예시 폴더에 넣으면 여기서 보입니다.")
    else:
        # 카드뉴스 이미지는 세로로 길어서 원본 폭 그대로 보여주면 한 장이 화면을 다 차지한다.
        # 한 줄에 3장씩 격자로 줄여서 훑어볼 수 있게 한다.
        per_row = 3
        for start in range(0, len(examples), per_row):
            row = examples[start : start + per_row]
            for col, img in zip(st.columns(per_row), row):
                col.image(str(img), caption=img.name)

# ============================================================
# 딥리서치 결과 선택 — 파일 기반: data/research/*.md 중에서 고른다.
# 딥리서치 페이지에서 "지금" 무엇을 선택해뒀는지와 무관하게, 파일만 있으면
# 언제든 여기서 골라 진행할 수 있다 (파일 기반 독립 실행 원칙).
# ============================================================
st.subheader("딥리서치 결과 선택")

notes = list_research_notes()

if not notes:
    st.info("저장된 딥리서치 결과가 없습니다. 딥리서치 페이지에서 먼저 실행하세요.")
else:
    def _note_label(p: Path) -> str:
        try:
            first_line = next((ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()), "")
        except Exception:
            first_line = ""
        preview = (first_line[:50] + "…") if len(first_line) > 50 else first_line
        return f"{p.stem} · {preview}" if preview else p.stem

    pick_row = st.columns([3, 1], vertical_alignment="bottom")
    with pick_row[0]:
        picked_note = st.selectbox(
            "결과 파일", notes, format_func=_note_label, key="cardnews_note_pick"
        )
    with pick_row[1]:
        if st.button("선택", type="primary", key="cardnews_note_select"):
            st.session_state["cardnews_id"] = picked_note.stem
            st.rerun()

st.divider()

# ============================================================
# 선택된 리서치 확인 — 조사 노트 전문이 곧 생성 참고자료다(pairs 중간 산출물 제거, 2026-07-29).
# 슬라이드 출처용 URL 목록은 매니페스트의 후보(candidate) 정보에서 가져온다.
# ============================================================
st.subheader("선택된 리서치")

selected_id = st.session_state.get("cardnews_id")
# 아래 생성 섹션에서 쓰는 페이지 수준 변수 — 조사 노트 전문이 생성 입력이고,
# 출처 URL 목록은 매니페스트의 후보(candidate) 정보에서 가져와 슬라이드 출처로 쓴다.
research_note = None
research_sources: list[str] = []

if not selected_id:
    st.info("위에서 딥리서치 결과 파일을 고르고 「선택」을 누르세요.")
else:
    note_path = RESEARCH_DIR / f"{selected_id}.md"
    if not note_path.exists():
        st.error(f"{note_path.name} 파일이 없습니다 — 선택 후 파일이 이동/삭제된 것 같습니다. 위에서 다시 선택하세요.")
    else:
        research_note = note_path.read_text(encoding="utf-8")
        candidate = load_state(selected_id).get("candidate") or {}
        research_sources = candidate.get("sources") or (
            [candidate["source"]] if candidate.get("source") else []
        )

        info_row = st.columns([3, 1], vertical_alignment="center")
        with info_row[0]:
            st.markdown(f"**선택된 리서치**: `{selected_id}`")
            st.caption("이 조사 노트 전문이 카드뉴스 JSON 생성의 참고자료로 그대로 사용됩니다.")
        with info_row[1]:
            if st.button("조사 노트 보기", key="cardnews_show_note"):
                show_research_dialog(research_note)

        if research_sources:
            with st.expander(f"출처 URL 목록 ({len(research_sources)}건 — 슬라이드 출처로 사용됨)"):
                for u in research_sources:
                    st.markdown(f"- {u}")
        else:
            st.warning("매니페스트에서 출처 URL 목록을 찾지 못했습니다 — 슬라이드 출처는 노트의 「출처」 섹션에 의존합니다.")

st.divider()

# ============================================================
# 템플릿 선택 — templates/<템플릿명>/ 폴더가 템플릿 하나다(template.html + prompt.md + 예시/).
# html은 렌더·검증, prompt.md는 같은 스키마로 JSON을 생성시키는 규칙이라 반드시 세트로 움직인다.
# 템플릿 추가/관리 페이지는 카드뉴스 제작 흐름 완성 후 별도로 만든다(2026-07-29 사용자 결정).
# ============================================================
st.subheader("템플릿 선택")

templates = list_templates()

if not templates:
    st.warning(f"사용할 수 있는 템플릿이 없습니다 — {TEMPLATES_DIR} 아래에 template.html + prompt.md 세트 폴더가 필요합니다.")
else:
    tpl_row = st.columns([3, 1, 1], vertical_alignment="bottom")
    with tpl_row[0]:
        picked_template = st.selectbox(
            "카드뉴스 템플릿", templates, format_func=lambda p: p.name, key="cardnews_template_pick"
        )
    with tpl_row[1]:
        if st.button("예시", key="cardnews_template_examples"):
            show_template_examples_dialog(picked_template)
    with tpl_row[2]:
        if st.button("선택", type="primary", key="cardnews_template_select"):
            st.session_state["cardnews_template"] = picked_template.name
            st.rerun()

selected_template_name = st.session_state.get("cardnews_template")
selected_template_dir = TEMPLATES_DIR / selected_template_name if selected_template_name else None

if not selected_template_name:
    st.info("템플릿을 고르고 「선택」을 누르세요.")
elif selected_template_dir is None or not (selected_template_dir / "template.html").exists() or not (selected_template_dir / "prompt.md").exists():
    st.error(f"템플릿 「{selected_template_name}」 세트(template.html + prompt.md)를 찾을 수 없습니다 — 폴더가 이동/삭제된 것 같습니다. 위에서 다시 선택하세요.")
else:
    st.markdown(f"**선택된 템플릿**: `{selected_template_name}`")
    with st.expander("JSON 생성 프롬프트 미리보기 (읽기 전용)"):
        st.code((selected_template_dir / "prompt.md").read_text(encoding="utf-8"), language=None)

st.divider()

# ============================================================
# 카드뉴스 JSON 생성 — 선택된 리서치의 조사 노트 전문 + 출처 URL 목록 + 선택된 템플릿의 prompt.md(시스템 프롬프트)로
# 프롬프트를 조립해 실행한다. 계정 정보는 저장하지 않고 생성할 때마다 입력한다(2026-07-29 사용자 결정).
# 결과는 data/content/<id>.json이 원본(canonical)이고 매니페스트에는 경로만 기록한다.
# ============================================================
st.subheader("카드뉴스 JSON 생성")

template_ready = (
    selected_template_dir is not None
    and (selected_template_dir / "prompt.md").exists()
)

if not selected_id or research_note is None:
    st.info("먼저 위에서 딥리서치 결과를 선택하세요.")
elif not template_ready:
    st.info("먼저 위에서 템플릿을 선택하세요.")
else:
    acc_cols = st.columns(3)
    brand = acc_cols[0].text_input("계정 이름 (brand)", key="cardnews_brand")
    handle = acc_cols[1].text_input("핸들 (handle)", key="cardnews_handle")
    audience = acc_cols[2].text_input("독자층", key="cardnews_audience")
    direction = st.text_input(
        "콘텐츠 방향 (선택)",
        key="cardnews_direction",
        placeholder="비워두면 GPT가 스토리라인·톤을 소재에 맞게 알아서 설계합니다 — 예: 공포 소구 말고 실용 체크리스트 톤으로",
    )
    st.caption("계정 정보·콘텐츠 방향은 파일로 저장되지 않습니다 — 생성할 때 입력한 값이 그대로 프롬프트에 들어가고, 계정 정보를 비워두면 카드에 브랜드/핸들이 표시되지 않습니다.")

    prompt_key = f"cardnews_user_prompt::{selected_id}::{selected_template_name}"
    ver_key = f"{prompt_key}::ver"
    version = st.session_state.get(ver_key, 0)

    def _rebuild_user_prompt():
        _, user_prompt = build_content_json_prompt(
            selected_template_dir, selected_id, research_note, research_sources,
            brand=brand, handle=handle, audience=audience, direction=direction,
        )
        st.session_state[prompt_key] = user_prompt

    if prompt_key not in st.session_state:
        _rebuild_user_prompt()

    edited_user_prompt = st.text_area(
        "생성 프롬프트 (수정 가능) — 시스템 프롬프트는 위 「JSON 생성 프롬프트 미리보기」의 prompt.md가 그대로 사용됩니다",
        value=st.session_state[prompt_key],
        height=280,
        key=f"{prompt_key}::edit::{version}",
    )

    btn_row = st.columns([1, 1])
    with btn_row[0]:
        # text_area는 같은 key로는 value 변경이 반영되지 않아, 위젯 key에 버전을 붙여
        # 새로고침 때마다 새 위젯으로 다시 그린다 (딥리서치 페이지의 전체 선택/해제와 같은 방식).
        if st.button("프롬프트 새로고침 (계정 정보·방향 반영)"):
            _rebuild_user_prompt()
            st.session_state[ver_key] = version + 1
            st.rerun()
    with btn_row[1]:
        run_clicked = st.button("카드뉴스 JSON 생성", type="primary")

    if run_clicked:
        try:
            client = get_client()
            system_prompt = (selected_template_dir / "prompt.md").read_text(encoding="utf-8")
            with st.spinner("카드뉴스 JSON 생성 중..."):
                content, raw = run_content_json_prompt(client, system_prompt, edited_user_prompt, selected_id)
            if content is None:
                st.error("모델 출력이 JSON으로 파싱되지 않았습니다 — 아래 원본을 확인하세요. (파일은 저장되지 않았습니다)")
                with st.expander("모델 원본 출력"):
                    st.code(raw, language=None)
            else:
                content_path = CONTENT_DIR / f"{selected_id}.json"
                CONTENT_DIR.mkdir(parents=True, exist_ok=True)
                content_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
                save_state(selected_id, content_path=str(content_path))
                st.session_state[f"cardnews_content::{selected_id}"] = content
                st.success(f"생성 완료 — {content_path.name} 저장됨. 아래 「카드뉴스 JSON 선택」에서 확인·수정하세요.")
        except Exception as e:
            st.error(f"생성 실패: {e}")

st.divider()

# ============================================================
# 카드뉴스 JSON 선택 — 파일 기반: data/content/*.json 중에서 고른다. 방금 생성한 것이든
# 과거에 만든 것이든 파일만 있으면 골라서 확인·수정하고, 아래 표지 이미지 생성으로 잇는다.
# ============================================================
st.subheader("카드뉴스 JSON 선택")

content_files = sorted(CONTENT_DIR.glob("*.json"), reverse=True)
picked_content = None
picked_content_path = None

if not content_files:
    st.info("저장된 카드뉴스 JSON이 없습니다 — 위에서 먼저 생성하세요.")
else:
    def _content_label(p: Path) -> str:
        try:
            headline = json.loads(p.read_text(encoding="utf-8")).get("cover", {}).get("headline", "")
            headline = headline.replace("\n", " ")
        except Exception:
            headline = ""
        return f"{p.stem} · {headline}" if headline else p.stem

    crow = st.columns([3, 1, 1], vertical_alignment="bottom")
    with crow[0]:
        picked_content_path = st.selectbox(
            "content.json 파일", content_files, format_func=_content_label, key="cardnews_content_pick"
        )
    ck = f"cardnews_content::{picked_content_path.stem}"
    if st.session_state.get(ck) is None:
        try:
            st.session_state[ck] = json.loads(picked_content_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            st.error(f"{picked_content_path.name} 파싱 실패: {e}")
    with crow[1]:
        if st.button("보기/편집", key="cardnews_content_edit_btn", disabled=st.session_state.get(ck) is None):
            show_json_dialog(st.session_state[ck], ck)
    with crow[2]:
        # 셀렉트박스 값이 바뀌는 것만으로는 아래 표지 이미지 섹션에 반영하지 않는다 —
        # 「선택」을 눌러 확정한 파일만 사용한다(리서치/템플릿 선택과 같은 명시적 확정 방식).
        if st.button("선택", type="primary", key="cardnews_content_select", disabled=st.session_state.get(ck) is None):
            st.session_state["cardnews_confirmed_content"] = picked_content_path.stem
            st.rerun()

    picked_content = st.session_state.get(ck)
    if picked_content:
        # 편집 다이얼로그에서 적용된 내용을 파일(canonical)에 반영 — 실제로 달라졌을 때만 쓴다.
        serialized = json.dumps(picked_content, ensure_ascii=False, indent=2)
        if picked_content_path.read_text(encoding="utf-8") != serialized:
            picked_content_path.write_text(serialized, encoding="utf-8")
            save_state(picked_content_path.stem, content_path=str(picked_content_path))

st.divider()

# ============================================================
# 표지 이미지 생성 — 선택된 content.json의 cover.image_concept로 프롬프트를 조립해
# 실행 전 수정할 수 있게 보여준다. 결과는 assets/cover-<id>.png로 저장되고
# content.json의 cover.image가 그 파일을 가리키게 갱신된다.
# ============================================================
st.subheader("표지 이미지 생성")

confirmed_content_id = st.session_state.get("cardnews_confirmed_content")

if (
    not picked_content
    or picked_content_path is None
    or confirmed_content_id != picked_content_path.stem
):
    st.info("먼저 위에서 카드뉴스 JSON을 고르고 「선택」을 누르세요.")
else:
    cid = picked_content_path.stem
    cover = picked_content.get("cover") or {}
    concept = (cover.get("image_concept") or cover.get("headline", "").replace("\n", " ")).strip()

    img_prompt_key = f"cardnews_img_prompt::{cid}"
    img_ver_key = f"{img_prompt_key}::ver"
    img_version = st.session_state.get(img_ver_key, 0)

    if img_prompt_key not in st.session_state:
        st.session_state[img_prompt_key] = IMAGE_PROMPT_TEMPLATE.replace("{concept}", concept)

    edited_img_prompt = st.text_area(
        "이미지 생성 프롬프트 (수정 가능) — 주제 부분은 content.json의 cover.image_concept에서 채워집니다",
        value=st.session_state[img_prompt_key],
        height=220,
        key=f"{img_prompt_key}::edit::{img_version}",
    )

    opt_row = st.columns([2, 1, 1], vertical_alignment="bottom")
    with opt_row[0]:
        provider_label = st.selectbox("이미지 생성 API", list(IMAGE_PROVIDERS), key="cardnews_img_provider")
    with opt_row[1]:
        # 품질 옵션은 GPT Image 2 전용 — Seedream은 품질 파라미터를 받지 않으므로 비활성화한다.
        quality = st.selectbox(
            "품질 (GPT Image 2)",
            ["high", "medium", "low"],
            key="cardnews_img_quality",
            disabled=IMAGE_PROVIDERS[provider_label] == "seedream",
        )
    with opt_row[2]:
        if st.button("프롬프트 새로고침", key="cardnews_img_prompt_refresh"):
            st.session_state[img_prompt_key] = IMAGE_PROMPT_TEMPLATE.replace("{concept}", concept)
            st.session_state[img_ver_key] = img_version + 1
            st.rerun()

    if st.button("표지 이미지 생성", type="primary", key="cardnews_img_generate"):
        try:
            client = get_client()
            with st.spinner("표지 이미지 생성 중... (수십 초 걸릴 수 있습니다)"):
                image_uri = generate_cover_image_raw(
                    client, edited_img_prompt, cid, quality, provider=IMAGE_PROVIDERS[provider_label]
                )
            if image_uri:
                picked_content.setdefault("cover", {})["image"] = image_uri
                st.session_state[ck] = picked_content
                picked_content_path.write_text(
                    json.dumps(picked_content, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                save_state(cid, content_path=str(picked_content_path), cover_image_path=to_local_path(image_uri))
                st.success("표지 이미지 생성 완료 — content.json의 cover.image에 반영됐습니다.")
        except Exception as e:
            st.error(f"이미지 생성 실패: {e}")

    current_image = (picked_content.get("cover") or {}).get("image")
    if current_image:
        local_path = Path(to_local_path(current_image))
        if local_path.exists():
            st.caption("현재 표지 이미지")
            st.image(str(local_path), width=320)
        else:
            st.warning(f"cover.image가 가리키는 파일이 없습니다: {local_path}")

st.divider()

# ============================================================
# 카드뉴스 렌더 — 확정된 content.json + 선택된 템플릿 HTML을 Render.py(Playwright)로
# 한 장씩 캡처해 카드뉴스/<id>/에 캐러셀(4:5)·스토리(9:16) PNG를 만든다.
# ============================================================
st.subheader("카드뉴스 렌더")

content_confirmed = (
    picked_content
    and picked_content_path is not None
    and confirmed_content_id == picked_content_path.stem
)

if not content_confirmed:
    st.info("먼저 위에서 카드뉴스 JSON을 고르고 「선택」을 누르세요.")
elif not template_ready:
    st.info("먼저 위에서 템플릿을 선택하세요.")
else:
    render_id = picked_content_path.stem
    out_dir = OUT_ROOT / render_id
    st.caption(f"템플릿 「{selected_template_name}」 + {picked_content_path.name} → 카드뉴스/{render_id}/")

    if st.button("카드뉴스 렌더", type="primary", key="cardnews_render_btn"):
        try:
            with st.spinner("렌더 중... (슬라이드를 한 장씩 캡처합니다)"):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(HERE / "Render.py"),
                        str(picked_content_path),
                        str(out_dir),
                        str(selected_template_dir / "template.html"),
                    ],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
            if result.returncode != 0:
                st.error("렌더 실패 — 글자수 상한 위반이나 텍스트 넘침이면 위 「보기/편집」으로 내용을 줄인 뒤 다시 시도하세요.")
                st.code(result.stderr or result.stdout)
            else:
                save_state(render_id, render_out_dir=str(out_dir))
                st.success(f"렌더 완료 → {out_dir}")
        except Exception as e:
            st.error(f"렌더 실패: {e}")

    if out_dir.exists():
        for folder, label in (("carousel", "캐러셀 (4:5)"), ("story", "스토리 (9:16)")):
            imgs = sorted((out_dir / folder).glob("*.png"))
            if imgs:
                st.caption(f"{label} · {len(imgs)}장")
                for col, img in zip(st.columns(len(imgs)), imgs):
                    col.image(str(img))

st.divider()

# ============================================================
# 인스타 업로드 설명문구 — 딥리서치 결과를 따로 골라(위 선택과 무관, 파일 기반 독립 실행)
# 상세 캡션 + 해시태그를 생성하고 그대로 복사해 붙여넣을 수 있게 보여준다.
# ============================================================
st.subheader("인스타 업로드 설명문구")

if not notes:
    st.info("저장된 딥리서치 결과가 없습니다 — 딥리서치 페이지에서 먼저 실행하세요.")
else:
    cap_row = st.columns([3, 1], vertical_alignment="bottom")
    with cap_row[0]:
        caption_note = st.selectbox(
            "딥리서치 결과", notes, format_func=_note_label, key="cardnews_caption_note_pick"
        )
    with cap_row[1]:
        caption_clicked = st.button("생성", type="primary", key="cardnews_caption_generate")

    cap_key = f"cardnews_caption::{caption_note.stem}"

    if caption_clicked:
        try:
            client = get_client()
            with st.spinner("설명문구 생성 중..."):
                st.session_state[cap_key] = run_insta_caption(
                    client, caption_note.read_text(encoding="utf-8")
                )
        except Exception as e:
            st.error(f"설명문구 생성 실패: {e}")

    if st.session_state.get(cap_key):
        st.caption("오른쪽 위 복사 버튼으로 그대로 복사해 인스타그램에 붙여넣으세요.")
        st.code(st.session_state[cap_key], language=None)
