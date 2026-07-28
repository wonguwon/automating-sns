#!/usr/bin/env python3
"""4단계 — 표지 이미지 생성. data/content/<id>.json을 읽고 cover.image를 채운 뒤 다시 저장한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json

import streamlit as st

from pipeline_common import (
    ARK_API_KEY,
    CONTENT_DIR,
    IMAGE_PROMPT_TEMPLATE,
    IMAGE_PROVIDERS,
    content_id_widget,
    generate_cover_image_raw,
    get_client,
    to_local_path,
)
from pipeline_state import load_state, save_state

st.title("4단계 — 표지 이미지 생성")

content_id = content_id_widget()
content_path = CONTENT_DIR / f"{content_id}.json"

if not content_path.exists():
    st.info("이 콘텐츠 ID에는 content.json이 없습니다. 먼저 3단계에서 콘텐츠 JSON을 생성하세요.")
else:
    content = json.loads(content_path.read_text(encoding="utf-8"))
    concept = content.get("cover", {}).get("headline", "").replace("\n", " ")
    default_prompt = IMAGE_PROMPT_TEMPLATE.replace("{concept}", concept)
    prompt_key = f"cover_prompt_{content_id}"
    st.session_state.setdefault(prompt_key, default_prompt)

    edited_prompt = st.text_area(
        "표지 이미지 프롬프트 (직접 수정 가능 — 이 내용 그대로 이미지 생성에 쓰입니다)",
        height=260,
        key=prompt_key,
    )

    provider_label = st.selectbox("이미지 생성 API", list(IMAGE_PROVIDERS.keys()), key="cover_image_provider_label")
    image_provider = IMAGE_PROVIDERS[provider_label]
    if image_provider == "seedream" and not ARK_API_KEY:
        st.warning("ARK_API_KEY가 없습니다. 이 폴더의 .env 파일에 ARK_API_KEY=...를 추가하세요.")

    quality_label = st.radio("품질", ["테스트 (medium)", "최종 (high)"], horizontal=True, key="cover_quality")
    quality_value = "medium" if quality_label.startswith("테스트") else "high"
    if image_provider == "seedream":
        st.caption("품질 토글은 GPT Image 2 전용입니다 — Seedream 선택 시에는 적용되지 않습니다.")

    if st.button("이미지 생성", type="primary"):
        try:
            client = get_client() if image_provider == "openai" else None
            with st.spinner("이미지 생성 중..."):
                path = generate_cover_image_raw(
                    client, edited_prompt, content_id, quality_value, provider=image_provider
                )
            content["cover"]["image"] = path
            content_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
            save_state(content_id, content_path=str(content_path), cover_image_path=path)
            if path:
                st.success("이미지 생성 완료")
            else:
                st.warning("폴백: 단색 배경으로 진행됩니다.")
        except Exception as e:
            st.error(f"이미지 생성 실패: {e}")

    image_path = content.get("cover", {}).get("image")
    if image_path:
        st.image(to_local_path(image_path), width=320)
