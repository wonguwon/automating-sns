#!/usr/bin/env python3
"""
칼퇴각 파이프라인 앱 — Streamlit UI (진입점)
------------------------------------------------
컨텐츠 수집 → 딥리서치 → 카드뉴스 제작(→ 이후 릴스 제작 예정)을 상단 네비게이션의
별도 페이지로 분리했다. 각 페이지는 data/pipeline/<content_id>.json 매니페스트와
각 단계의 canonical 파일(data/candidates, data/research, data/content, 카드뉴스/<id>/)을
디스크에서 직접 읽고 쓰므로, 이전 단계를 같은 세션에서 이어서 실행하지 않아도
원하는 단계부터 바로 진행할 수 있다.

기존 V2 이관분(3~6단계: 콘텐츠 JSON·표지 이미지·콘텐츠 렌더·릴스 렌더 페이지)은
2026-07-29에 제거했다 — 딥리서치 결과를 입력으로 받는 "카드뉴스 제작"·"릴스 제작"
페이지로 다시 구성하는 중이다. Generate.py/Render.py/Render_reel.py 로직은 새 페이지에서
재사용할 수 있어 남겨두었다.

이 파일 자체는 페이지 등록과 상단 네비게이션 구성만 담당한다 — 단계별 로직은 pages/*.py에,
공용 헬퍼/경로는 pipeline_common.py에 있다.

실행:
    streamlit run app.py

사전 준비:
    이 폴더의 .env 파일에 OPENAI_API_KEY=sk-... 작성 (코드에 키를 직접 쓰지 않는다)
    pip install -r requirements.txt 실행 후, playwright install chromium 한 번 실행
------------------------------------------------
"""
import streamlit as st

st.set_page_config(page_title="인스타 자동화 파이프라인", layout="centered")

pages = [
    st.Page("pages/1_컨텐츠_수집.py", title="컨텐츠 수집", default=True),
    st.Page("pages/2_딥리서치.py", title="딥리서치"),
    st.Page("pages/3_카드뉴스_제작.py", title="카드뉴스 제작"),
]

st.navigation(pages, position="top").run()
