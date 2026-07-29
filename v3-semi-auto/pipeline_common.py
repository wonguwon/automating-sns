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
TEMPLATES_DIR = HERE / "templates"
TEMPLATE_EXAMPLE_DIRNAME = "예시"
TEMPLATE_EXAMPLE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

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

def list_templates() -> list[Path]:
    """
    카드뉴스 템플릿 목록. templates/<템플릿명>/ 폴더 중 template.html과 prompt.md가
    둘 다 있는 것만 템플릿으로 인정한다 — 이 둘은 같은 스키마의 양면(렌더 검증 ↔ 생성 규칙)이라
    한쪽만 있으면 세트가 아니다. 예시 이미지(예시/)는 없어도 된다.
    """
    if not TEMPLATES_DIR.exists():
        return []
    return sorted(
        d for d in TEMPLATES_DIR.iterdir()
        if d.is_dir() and (d / "template.html").exists() and (d / "prompt.md").exists()
    )


def list_template_examples(template_dir: Path) -> list[Path]:
    """템플릿 폴더의 예시/ 안에 있는 이미지 파일 목록 (없으면 빈 리스트)."""
    example_dir = template_dir / TEMPLATE_EXAMPLE_DIRNAME
    if not example_dir.exists():
        return []
    return sorted(
        p for p in example_dir.iterdir()
        if p.is_file() and p.suffix.lower() in TEMPLATE_EXAMPLE_EXTS
    )


CONTENT_JSON_USER_PROMPT = """오늘 채택된 소재 ID: {content_id}

계정 정보 (빈 항목은 스키마 규칙대로 처리한다 — brand/handle이 비어 있으면 빈 문자열로 둔다):
- 계정 이름(brand): {brand}
- 핸들(handle): {handle}
- 독자층: {audience}

콘텐츠 방향 ("(없음)"이면 스토리라인·톤은 소재에 맞게 네가 자유롭게 설계한다):
{direction}

출처 URL 목록 (각 슬라이드의 source는 반드시 이 목록의 URL 중에서 고른다 — 목록에 없는 URL을
만들어내지 않는다):
{sources}

아래는 딥리서치 조사 노트다. 이 노트에 명시된 사실만 사용해서 스키마에 맞는 JSON을 만들어라.

{research_note}
"""


def build_content_json_prompt(
    template_dir: Path, content_id: str, research_note: str, source_urls: list[str],
    brand: str = "", handle: str = "", audience: str = "", direction: str = "",
) -> tuple[str, str]:
    """
    (시스템 프롬프트, 사용자 프롬프트)를 조립한다.
    시스템 프롬프트는 선택된 템플릿의 prompt.md 그대로(수정은 템플릿 관리에서),
    사용자 프롬프트는 계정 정보(생성 시 입력, 저장 안 함) + 출처 URL 목록 + 조사 노트 전문으로
    만들어 화면에서 보여주고 실행 전 수정할 수 있게 한다. pairs 중간 산출물은 쓰지 않는다 —
    노트가 곧 참고자료다(2026-07-29 결정).
    """
    system_prompt = (template_dir / "prompt.md").read_text(encoding="utf-8")
    urls = [u for u in dict.fromkeys(source_urls) if u]
    user_prompt = CONTENT_JSON_USER_PROMPT.format(
        content_id=content_id,
        brand=brand.strip() or "(없음)",
        handle=handle.strip() or "(없음)",
        audience=audience.strip() or "(없음)",
        direction=direction.strip() or "(없음)",
        sources="\n".join(f"- {u}" for u in urls) if urls else "(목록 없음 — 노트의 「출처」 섹션에 있는 URL을 사용)",
        research_note=research_note,
    )
    return system_prompt, user_prompt


INSTA_CAPTION_PROMPT = """아래 딥리서치 조사 노트를 근거로, 인스타그램 업로드용 설명문구(캡션)를 작성하라.

규칙:
- 노트에 명시된 사실만 쓴다 — 숫자·날짜·기관명은 정확히 유지하고, 새 사실을 지어내지 않는다.
- 저작권: 원문·노트의 문장을 그대로(또는 어순만 바꿔) 옮기지 말고 전부 새 문장으로 쓴다.
  직접 인용이 꼭 필요하면 따옴표로 표시하고 누구의 말인지 밝힌다.
- 구성: 첫 줄은 스크롤을 멈추게 하는 훅 문장 → 핵심 내용을 구체적 수치·사실을 살려 상세하게
  (문단을 나눠 읽기 쉽게) → 독자가 바로 활용할 행동 포인트 → 저장·공유를 유도하는 마무리 문장.
- 마지막 줄에 해시태그를 붙인다 (#태그 형식 한 줄, 5~10개, 소재와 직접 관련된 것만).
- 출력은 설명문구 본문과 해시태그만 — 제목, 부가 설명, 코드펜스 없이 그대로 복사해 붙여넣을 수
  있는 텍스트로만 출력한다.

조사 노트:
{research_note}
"""


def run_insta_caption(client: OpenAI, research_note: str) -> str:
    """조사 노트로 인스타 업로드용 설명문구(+해시태그)를 생성해 복붙 가능한 텍스트로 돌려준다."""
    resp = client.chat.completions.create(
        model="gpt-5.5",
        messages=[{"role": "user", "content": INSTA_CAPTION_PROMPT.format(research_note=research_note)}],
    )
    return resp.choices[0].message.content.strip()


def run_content_json_prompt(
    client: OpenAI, system_prompt: str, user_prompt: str, content_id: str
) -> tuple[dict | None, str]:
    """
    카드뉴스 JSON 생성 프롬프트를 실행한다. (파싱된 dict 또는 None, 모델 원본 출력)을 반환한다 —
    파싱 실패 시 호출부가 원본을 화면에 보여줄 수 있게 예외 대신 None을 준다.
    """
    import re

    resp = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    cleaned = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()

    try:
        content = json.loads(cleaned)
    except json.JSONDecodeError:
        return None, raw

    content["id"] = content_id
    return content, raw


OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ARK_API_KEY = os.environ.get("ARK_API_KEY")
# 첫 항목이 셀렉트박스 기본값이 된다 — 기본 모델은 Seedream(2026-07-29 사용자 결정, ARK_API_KEY 필요).
IMAGE_PROVIDERS = {"Doubao-Seedream (Volcengine Ark)": "seedream", "GPT Image 2 (OpenAI)": "openai"}


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
마크다운으로 조사 노트 하나만 작성한다 (배경, 핵심 사실, 왜 지금 다룰 가치가 있는지, 관련 맥락과 함의,
특이사항·주의할 점 등). 원문에 있는 구체적인 숫자·날짜·기관명·발언 내용을 최대한 살려서 쓰되,
문장 자체는 원문을 베끼지 않고 새로 쓴다 — 뭉뚱그리지도, 그대로 옮기지도 않는다. 원문이 여러 건이면
겹치는 사실은 교차 확인된 것으로, 서로 다른 사실은 모두 반영해서 쓴다. 목표는 원문 문장의 요약이나
복사가 아니라, 원문에 있는 사실을 빠짐없이·정확하게·새 문장으로 옮겨 담는 것이다.
이 노트는 다음 단계(카드뉴스 생성)가 참고자료로 그대로 읽는다 — 노트에 없는 사실은 콘텐츠에 쓸 수
없으므로, 확인된 사실은 빠짐없이 담는다. 문서 맨 끝에는 `## 출처` 섹션을 두고 실제로 참고한 원문
URL을 목록으로 적는다 (아래 "출처 목록"에 있는 URL만 쓸 수 있다 — 없는 링크를 만들어내지 않는다).

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


def run_research_prompt(client: OpenAI, prompt: str) -> str:
    """딥리서치 프롬프트를 실행해 마크다운 조사 노트를 돌려준다. 노트가 유일한 산출물이다(2026-07-29,
    pairs 중간 산출물 제거 — 카드뉴스 생성이 노트 전문을 직접 읽는다)."""
    resp = client.chat.completions.create(
        model="gpt-5.5",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


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
