#!/usr/bin/env python3
"""템플릿 관리. templates/<이름>/ 폴더(template.html+prompt.md+예시/) 세트를 추가·편집·삭제한다.

이 페이지는 템플릿(특히 LIMITS 검증 로직이 있는 template.html)을 화면에서 새로 만들어주지
않는다 — 이미 만들어둔 파일을 업로드해서 세트로 저장/교체하는 파일 관리 UI다
(2026-07-30 사용자 결정). 편집은 기존 파일을 덮어쓰는 방식, 삭제는 파일/폴더를 지우는 방식이다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from pipeline_common import (
    TEMPLATE_EXAMPLE_EXTS,
    TEMPLATES_DIR,
    add_template_examples,
    create_template,
    delete_template,
    delete_template_example,
    is_valid_template_name,
    list_template_examples,
    list_templates,
    update_template_files,
)

st.title("템플릿 관리")
st.caption(
    "템플릿은 template.html(렌더·글자수 검증) + prompt.md(JSON 생성 규칙) + 예시/(예시 이미지) "
    "세트로 관리합니다. 이미 만들어둔 파일을 업로드해서 추가·교체합니다."
)

EXAMPLE_TYPES = [ext.lstrip(".") for ext in TEMPLATE_EXAMPLE_EXTS]


def _example_grid(examples: list[Path], per_row: int = 4):
    for start in range(0, len(examples), per_row):
        row = examples[start : start + per_row]
        for col, img in zip(st.columns(per_row), row):
            col.image(str(img), caption=img.name)


@st.dialog("템플릿 예시", width="large")
def _show_examples_dialog(template_dir: Path):
    st.markdown(f"**템플릿**: `{template_dir.name}`")
    examples = list_template_examples(template_dir)
    if not examples:
        st.info("예시 이미지가 아직 없습니다.")
    else:
        _example_grid(examples)


@st.dialog("생성 프롬프트", width="large")
def _show_prompt_dialog(template_dir: Path):
    st.markdown(f"**템플릿**: `{template_dir.name}`")
    st.code((template_dir / "prompt.md").read_text(encoding="utf-8"), language=None)


# ============================================================
# 템플릿 목록 — 셀렉트박스로 고르고, 예시/프롬프트는 모달로 확인한다.
# ============================================================
st.subheader("템플릿 목록")

templates = list_templates()

if not templates:
    st.info(f"아직 템플릿이 없습니다 — 아래 「새 템플릿 추가」에서 만드세요. ({TEMPLATES_DIR})")
else:
    list_row = st.columns([3, 1, 1], vertical_alignment="bottom")
    with list_row[0]:
        listed_template = st.selectbox(
            "템플릿", templates, format_func=lambda p: p.name, key="template_list_pick"
        )
    with list_row[1]:
        if st.button("예시", key="template_list_examples_btn"):
            _show_examples_dialog(listed_template)
    with list_row[2]:
        if st.button("프롬프트", key="template_list_prompt_btn"):
            _show_prompt_dialog(listed_template)

st.divider()

# ============================================================
# 새 템플릿 추가 — template.html/prompt.md/예시 이미지를 업로드해서 세트로 저장한다.
# ============================================================
st.subheader("새 템플릿 추가")

with st.form("template_create_form", clear_on_submit=True):
    new_name = st.text_input("템플릿 이름 (폴더명)")
    new_html = st.file_uploader("template.html", type=["html"], key="template_create_html")
    new_prompt = st.file_uploader("prompt.md", type=["md", "txt"], key="template_create_prompt")
    new_examples = st.file_uploader(
        "예시 이미지 (선택, 여러 장 가능)",
        type=EXAMPLE_TYPES,
        accept_multiple_files=True,
        key="template_create_examples",
    )
    submitted = st.form_submit_button("템플릿 추가", type="primary")

if submitted:
    if not new_name.strip():
        st.error("템플릿 이름을 입력하세요.")
    elif not is_valid_template_name(new_name):
        st.error("템플릿 이름에 `/`, `\\`, `..` 같은 문자는 쓸 수 없습니다.")
    elif new_html is None or new_prompt is None:
        st.error("template.html과 prompt.md는 필수입니다.")
    else:
        try:
            template_dir = create_template(new_name, new_html.getvalue(), new_prompt.getvalue())
            if new_examples:
                add_template_examples(template_dir, [(f.name, f.getvalue()) for f in new_examples])
            st.success(f"템플릿 「{new_name}」 추가됨.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))

st.divider()

# ============================================================
# 기존 템플릿 편집 — template.html/prompt.md는 재업로드하면 덮어쓰고, 예시 이미지는
# 추가 업로드하거나 개별 삭제할 수 있다.
# ============================================================
st.subheader("기존 템플릿 편집")

if not templates:
    st.info("편집할 템플릿이 없습니다.")
else:
    edit_target = st.selectbox(
        "편집할 템플릿", templates, format_func=lambda p: p.name, key="template_edit_pick"
    )

    st.markdown(f"**`{edit_target.name}`** 편집")

    edit_html = st.file_uploader(
        "template.html 교체 (선택 — 올리면 덮어씁니다)", type=["html"], key="template_edit_html"
    )
    edit_prompt = st.file_uploader(
        "prompt.md 교체 (선택 — 올리면 덮어씁니다)", type=["md", "txt"], key="template_edit_prompt"
    )
    if st.button(
        "파일 저장",
        key="template_edit_save",
        disabled=edit_html is None and edit_prompt is None,
    ):
        update_template_files(
            edit_target,
            html_bytes=edit_html.getvalue() if edit_html else None,
            prompt_bytes=edit_prompt.getvalue() if edit_prompt else None,
        )
        st.success("저장됨.")
        st.rerun()

    st.markdown("**예시 이미지 추가**")
    add_examples = st.file_uploader(
        "이미지 업로드 (여러 장 가능)",
        type=EXAMPLE_TYPES,
        accept_multiple_files=True,
        key="template_edit_add_examples",
    )
    if st.button(
        "예시 이미지 추가", key="template_edit_add_examples_btn", disabled=not add_examples
    ):
        saved = add_template_examples(edit_target, [(f.name, f.getvalue()) for f in add_examples])
        st.success(f"{len(saved)}장 추가됨: {', '.join(saved)}")
        st.rerun()

    st.markdown("**예시 이미지 삭제**")
    edit_examples = list_template_examples(edit_target)
    if not edit_examples:
        st.caption("예시 이미지 없음")
    else:
        for img in edit_examples:
            row = st.columns([1, 3, 1], vertical_alignment="center")
            row[0].image(str(img), width=100)
            row[1].caption(img.name)
            if row[2].button(
                "삭제", key=f"template_edit_del_example::{edit_target.name}::{img.name}"
            ):
                delete_template_example(img)
                st.rerun()

st.divider()

# ============================================================
# 템플릿 삭제 — 되돌릴 수 없으므로 이름을 다시 입력해야 삭제 버튼이 활성화된다.
# ============================================================
st.subheader("템플릿 삭제")

if not templates:
    st.info("삭제할 템플릿이 없습니다.")
else:
    delete_target = st.selectbox(
        "삭제할 템플릿", templates, format_func=lambda p: p.name, key="template_delete_pick"
    )
    st.warning(
        f"「{delete_target.name}」 폴더 전체(template.html·prompt.md·예시/)가 삭제되며 "
        "되돌릴 수 없습니다."
    )
    confirm_name = st.text_input(
        f"삭제하려면 템플릿 이름 `{delete_target.name}`을 그대로 입력하세요",
        key="template_delete_confirm",
    )
    if st.button(
        "템플릿 삭제",
        type="primary",
        key="template_delete_btn",
        disabled=confirm_name != delete_target.name,
    ):
        delete_template(delete_target)
        st.success(f"템플릿 「{delete_target.name}」 삭제됨.")
        st.rerun()
