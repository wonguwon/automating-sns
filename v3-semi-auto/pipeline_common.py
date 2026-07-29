#!/usr/bin/env python3
"""
칼퇴각 파이프라인 — 페이지 공용 모듈
------------------------------------------------
pages/*.py는 각자 별도의 __file__을 가지므로(st.navigation으로 실행됨),
경로 계산은 반드시 이 모듈에서만 하고 페이지 스크립트는 여기서 가져다 쓴다.

app.py(구 버전)에 있던 공용 헬퍼(OpenAI 클라이언트, 이미지 생성, 기사 본문 fetch,
딥리서치 프롬프트/실행, 다이얼로그)를 그대로 옮긴 것 — 로직 변경 없음.
------------------------------------------------
"""
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import requests
import streamlit as st
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

import os

from Generate import ARK_BASE_URL, SEEDREAM_MODEL, generate_content_json, IMAGE_PROMPT_TEMPLATE  # noqa: F401

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")  # OPENAI_API_KEY

DATA = HERE / "data"
CAND_DIR = DATA / "candidates"
RESEARCH_DIR = DATA / "research"
CONTENT_DIR = DATA / "content"
PIPELINE_DIR = DATA / "pipeline"
RSS_COLLECT_DIR = DATA / "rss_collect"
HISTORY = DATA / "history.json"
ASSETS_DIR = HERE / "assets"
MUSIC_DIR = HERE / "music"
MUSIC_EXTS = ("*.mp3", "*.m4a", "*.wav", "*.aac")
OUT_ROOT = HERE / "카드뉴스"
SOURCES_DIR = HERE / "sources"

for d in (DATA, CAND_DIR, RESEARCH_DIR, CONTENT_DIR, PIPELINE_DIR, RSS_COLLECT_DIR, ASSETS_DIR, SOURCES_DIR):
    d.mkdir(parents=True, exist_ok=True)


def list_research_notes() -> list[Path]:
    """
    저장된 딥리서치 결과(.md) 파일 목록. 특정 후보를 지금 선택해둔 상태가 아니어도
    파일만 있으면 언제든 골라서 열람할 수 있게 하기 위함 — 이 파이프라인은 단계를 순서대로
    거쳐야 하는 게 아니라 파일로 연결되므로, 조회는 "현재 선택된 후보"에 묶이지 않는다.
    """
    if not RESEARCH_DIR.exists():
        return []
    return sorted(RESEARCH_DIR.glob("*.md"), reverse=True)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ARK_API_KEY = os.environ.get("ARK_API_KEY")
IMAGE_PROVIDERS = {"GPT Image 2 (OpenAI)": "openai", "Doubao-Seedream (Volcengine Ark)": "seedream"}


# ============================================================
# 공용 헬퍼
# ============================================================
@st.cache_resource
def get_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY가 없습니다. 이 폴더의 .env 파일에 OPENAI_API_KEY=sk-...를 추가하세요.")
    return OpenAI(api_key=OPENAI_API_KEY)


def to_local_path(file_uri: str) -> str:
    if not file_uri.startswith("file://"):
        return file_uri
    return url2pathname(urlparse(file_uri).path)


def content_id_widget() -> str:
    """
    모든 단계 페이지 상단에서 공통으로 쓰는 콘텐츠 ID 입력란.
    다른 단계에서 set_content_id()로 값을 예약해두면 다음 렌더에서 그 값을 기본으로 반영한다
    (위젯이 이미 그려진 뒤에는 st.session_state["content_id"]를 직접 덮어쓸 수 없어
    한 단계 거쳐 반영하는 방식을 쓴다).
    """
    if "content_id_override" in st.session_state:
        st.session_state["content_id"] = st.session_state.pop("content_id_override")
    st.session_state.setdefault("content_id", f"{date.today().isoformat().replace('-', '')}-01")
    return st.text_input("콘텐츠 ID", key="content_id")


def set_content_id(content_id: str):
    """다음 rerun에서 content_id_widget()이 이 값을 반영하도록 예약한다."""
    st.session_state["content_id_override"] = content_id


def generate_cover_image_raw(
    client: OpenAI, prompt: str, content_id: str, quality: str, provider: str = "openai"
) -> str | None:
    """
    화면에서 편집한 프롬프트를 그대로 이미지 생성 API에 보낸다.
    generate.py의 generate_cover_image()는 내부에서 프롬프트를 다시 조립하므로 여기서는 쓰지 않는다.

    provider: "openai"(기본, GPT Image 2) 또는 "seedream"(Volcengine Ark, Doubao-Seedream).
    seedream을 쓰려면 ARK_API_KEY가 .env에 있어야 한다 — 인자로 받은 client(OPENAI_API_KEY로 만든 것)는
    이 경로에서는 쓰지 않고 Ark용 클라이언트를 새로 만든다.
    """
    try:
        if provider == "seedream":
            if not ARK_API_KEY:
                st.error("ARK_API_KEY가 없습니다. 이 폴더의 .env 파일에 ARK_API_KEY=...를 추가하세요.")
                return None
            ark_client = OpenAI(api_key=ARK_API_KEY, base_url=ARK_BASE_URL)
            resp = ark_client.images.generate(
                model=SEEDREAM_MODEL,
                prompt=prompt,
                # Seedream은 최소 3,686,400픽셀 이상을 요구해 1024x1536(2:3)로는 400 에러가 난다.
                # 1664x2496도 2:3 비율을 유지하면서 최소 픽셀 수를 넘긴다.
                size="1664x2496",
                # watermark는 openai SDK의 images.generate()가 아는 파라미터가 아니라
                # (Ark 전용 필드) extra_body로 넘겨야 요청 바디에 실제로 포함된다.
                extra_body={"watermark": False},
            )
        else:
            resp = client.images.generate(
                model="gpt-image-2",
                prompt=prompt,
                size="1024x1536",
                quality=quality,
            )
        item = resp.data[0]
        ASSETS_DIR.mkdir(exist_ok=True)
        out_path = ASSETS_DIR / f"cover-{content_id}.png"

        if getattr(item, "url", None):
            import urllib.request
            urllib.request.urlretrieve(item.url, out_path)
        elif getattr(item, "b64_json", None):
            import base64
            out_path.write_bytes(base64.b64decode(item.b64_json))
        else:
            st.warning("이미지 응답 형식을 인식하지 못함 — 단색 폴백으로 진행됩니다.")
            return None

        return out_path.resolve().as_uri()
    except Exception as e:
        st.error(f"이미지 생성 실패: {e}")
        return None


ARTICLE_FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) kaltoegak-research"}
ARTICLE_STRIP_TAGS = ("script", "style", "nav", "header", "footer", "aside", "form", "iframe")


def fetch_article_text(url: str, max_chars: int = 6000) -> str | None:
    """
    후보의 source URL을 열어 기사 본문 텍스트를 뽑아온다.
    "웹 검색"이 아니라 이미 알고 있는 URL 하나를 그대로 읽는 것뿐이다.
    실패(타임아웃/비-200/본문 없음)하면 None을 반환한다 — 예외를 밖으로 던지지 않는다.
    """
    def paragraph_text(container) -> str:
        paragraphs = [p.get_text(" ", strip=True) for p in container.find_all("p")]
        return "\n".join(p for p in paragraphs if p)

    try:
        resp = requests.get(url, timeout=10, headers=ARTICLE_FETCH_HEADERS)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(ARTICLE_STRIP_TAGS):
            tag.decompose()

        # 뉴스 사이트는 본문 외에도 "관련기사"·"인기기사" 위젯 등에 <article>을 여러 개 쓴다.
        # 그중 <p> 글자수가 가장 많은 것을 실제 본문으로 간주한다. 이 방식이 부실하면(예: <article>을
        # 아예 안 쓰는 사이트) <body> 전체의 <p>로 폴백한다.
        text = max((paragraph_text(a) for a in soup.find_all("article")), key=len, default="")
        if len(text) < 200 and soup.body is not None:
            body_text = paragraph_text(soup.body)
            if len(body_text) > len(text):
                text = body_text
        text = text.strip()
        if not text:
            return None
        return text[:max_chars]
    except Exception:
        return None


RESEARCH_NOTE_PROMPT = """아래 후보에 대해, 소스를 최대한 상세하게 분석하는 조사 노트를 작성하라.
아래 "기사 원문"들과 "후보 요약"에 담긴 사실만 쓰고, 없는 사실은 지어내지 마라. 웹 검색은 하지 않는다
(이미 주어진 원문/요약 밖의 새로운 정보를 찾으러 나가지 않는다는 뜻).

저작권: 원문은 뉴스 기사이므로, 숫자·날짜·기관명·발언의 요지 같은 **사실**은 정확히 유지하되 **문장은
원문을 그대로(또는 어순만 살짝 바꿔) 옮기지 말고 새로 써라.** 원문 문장을 그대로 인용해야만 하는
경우가 아니면 verbatim 문장을 쓰지 않는다 — 직접 인용이 꼭 필요하면 따옴표로 표시하고 누구의 말인지
밝힌다.

출력 형식:
1. 마크다운으로 조사 노트를 작성한다 (배경, 핵심 사실, 왜 지금 다룰 가치가 있는지, 관련 맥락과 함의,
   특이사항·주의할 점 등). 원문에 있는 구체적인 숫자·날짜·기관명·발언 내용을 최대한 살려서 쓰되,
   문장 자체는 원문을 베끼지 않고 새로 쓴다 — 뭉뚱그리지도, 그대로 옮기지도 않는다. 원문이 여러 건이면
   겹치는 사실은 교차 확인된 것으로, 서로 다른 사실은 모두 반영해서 쓴다. 목표는 원문 문장의 요약이나
   복사가 아니라, 원문에 있는 사실을 빠짐없이·정확하게·새 문장으로 옮겨 담는 것이다.
2. 문서 맨 끝에 `---PAIRS---` 구분선을 넣고, 그 뒤에 (내용, 출처) 쌍의 JSON 배열을 붙인다:
   [{{"content": "...", "source": "..."}}, ...]
   각 content는 노트에서 실제로 쓴 구체적인 사실 하나다 — 이것도 원문 문장을 그대로 복사한 것이 아니라
   사실을 새 문장으로 쓴 것이어야 한다. 원문에 있는 서로 다른 구체적 사실(숫자·날짜·기관명·발언 요지
   등)은 개수 제한 없이 빠짐없이 다 뽑는다 — 개수를 맞추려고 적게 뽑거나 억지로 채우지 않는다. 같은
   사실을 표현만 바꿔 중복으로 넣지 않는다. source는 그 사실이 실제로 나온 원문의 URL이다. 아래
   "출처 목록"에 있는 URL만 쓸 수 있다 (없는 링크를 만들어내지 않는다).

후보:
- 제목: {title}
- 한 줄 요약: {one_line}
- 카드 각도: {angle}

출처 목록:
{sources}

기사 원문(참고용, 없으면 "없음" — 여러 건이면 [출처: URL]로 구분됨):
{article_text}
"""


def build_research_prompt(candidate: dict) -> tuple[str, bool]:
    """
    후보의 source URL 하나만이 아니라, GPT 선별 단계에서 같은 사건으로 병합된 모든 링크
    (candidate["sources"])를 전부 읽어와 딥리서치 프롬프트를 조립한다 — 실제 웹 검색 없이도
    "이미 같은 소재로 확인된 여러 기사"를 근거로 쓸 수 있게 하기 위함이다(2026-07-29 결정,
    실제 웹 검색은 뉴스 정확성 리스크가 있어 채택하지 않음).
    구 버전 후보 파일처럼 sources 필드가 없으면 source 하나만 쓴다.
    화면에서 이 프롬프트를 그대로 보여주고 사용자가 수정할 수 있게 한 뒤,
    실제 GPT 호출은 run_research_prompt()가 그 (수정됐을 수 있는) 텍스트를 그대로 받아 수행한다.
    """
    urls = candidate.get("sources") or [candidate.get("source", "")]
    urls = [u for u in dict.fromkeys(urls) if u]

    fetched = [(url, text) for url in urls if (text := fetch_article_text(url))]
    if fetched:
        article_text = "\n\n".join(f"[출처: {url}]\n{text}" for url, text in fetched)
    else:
        article_text = "없음"

    prompt = RESEARCH_NOTE_PROMPT.format(
        title=candidate.get("title", ""),
        one_line=candidate.get("one_line", ""),
        angle=candidate.get("angle", ""),
        sources="\n".join(urls) if urls else "(없음)",
        article_text=article_text,
    )
    return prompt, bool(fetched)


def run_research_prompt(client: OpenAI, prompt: str) -> tuple[str, list[dict] | None]:
    resp = client.chat.completions.create(
        model="gpt-5.5",
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.choices[0].message.content.strip()

    if "---PAIRS---" in raw:
        md_part, pairs_part = raw.split("---PAIRS---", 1)
    else:
        md_part, pairs_part = raw, "[]"

    md_part = md_part.strip()
    pairs_part = pairs_part.strip()
    pairs_part = pairs_part.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        pairs = json.loads(pairs_part)
    except json.JSONDecodeError:
        pairs = None

    return md_part, pairs


@st.dialog("딥리서치 결과", width="large")
def show_research_dialog(research_md: str):
    st.markdown(research_md)


@st.dialog("content.json 편집", width="large")
def show_json_dialog(content: dict, state_key: str):
    """
    적용을 누르면 st.session_state[state_key]에 파싱된 dict를 넣고 rerun한다.
    호출부는 st.session_state[state_key]를 읽어 저장 로직을 이어가면 된다.
    """
    text = json.dumps(content, ensure_ascii=False, indent=2)
    edited = st.text_area("JSON", value=text, height=480, key=f"{state_key}_edit_area")
    if st.button("적용", type="primary"):
        try:
            parsed = json.loads(edited)
        except json.JSONDecodeError as e:
            st.error(f"JSON 파싱 실패: {e} — 기존 값을 유지합니다.")
        else:
            st.session_state[state_key] = parsed
            st.success("적용됨")
            st.rerun()
