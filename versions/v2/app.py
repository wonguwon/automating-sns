#!/usr/bin/env python3
"""
칼퇴각 파이프라인 앱 (app2) — Streamlit UI
------------------------------------------------
후보 가져오기 → 후보 선택 → 딥리서치 → content.json → 표지 이미지 → 콘텐츠 렌더(PNG) → 릴스 렌더(MP4)
를 한 페이지에서 세로로 흐르는 단계별 버튼 UI로 처리한다.

이 폴더(app2) 하나로 독립 실행되도록 Research.py/Generate.py/Render.py/Render_reel.py/
card-template.html/prompt-content-json.md/sources.json/data/music를 모두 이 폴더 안에 둔다.
다른 폴더를 참조하지 않는다 — app2 폴더 전체만 복사해도 그대로 실행된다.

실행:
    cd app2
    streamlit run app.py

사전 준비:
    이 폴더의 .env 파일에 OPENAI_API_KEY=sk-... 작성 (코드에 키를 직접 쓰지 않는다)
    pip install -r requirements.txt 실행 후, playwright install chromium 한 번 실행
------------------------------------------------
"""
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import requests
import streamlit as st
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

# 이 폴더 자체가 Research.py/Generate.py/Render.py/Render_reel.py가 있는 곳이다.
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
load_dotenv(HERE / ".env")  # OPENAI_API_KEY

from Generate import ARK_BASE_URL, SEEDREAM_MODEL, generate_content_json, IMAGE_PROMPT_TEMPLATE  # noqa: E402

DATA = HERE / "data"
CAND_DIR = DATA / "candidates"
RESEARCH_DIR = DATA / "research"
CONTENT_DIR = DATA / "content"
HISTORY = DATA / "history.json"
ASSETS_DIR = HERE / "assets"
MUSIC_DIR = HERE / "music"
MUSIC_EXTS = ("*.mp3", "*.m4a", "*.wav", "*.aac")
OUT_ROOT = HERE / "카드뉴스"

for d in (DATA, CAND_DIR, RESEARCH_DIR, CONTENT_DIR, ASSETS_DIR):
    d.mkdir(parents=True, exist_ok=True)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ARK_API_KEY = os.environ.get("ARK_API_KEY")
IMAGE_PROVIDERS = {"GPT Image 2 (OpenAI)": "openai", "Doubao-Seedream (Volcengine Ark)": "seedream"}

st.set_page_config(page_title="칼퇴각 파이프라인", layout="centered")


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


RESEARCH_NOTE_PROMPT = """아래 후보를 근거로 카드뉴스 제작용 조사 노트를 작성하라.
아래 "기사 원문"과 "후보 요약"에 담긴 사실만 쓰고, 없는 사실은 지어내지 마라. 웹 검색은 하지 않는다
(이미 주어진 원문/요약 밖의 새로운 정보를 찾으러 나가지 않는다는 뜻).

출력 형식:
1. 마크다운으로 조사 노트를 작성한다 (배경, 핵심 사실, 왜 지금 다룰 가치가 있는지, 카드뉴스에 쓸 만한
   포인트 등). 원문에 있는 구체적인 숫자·날짜·기관명·인용을 최대한 살려서 쓴다 — 뭉뚱그리지 않는다.
2. 문서 맨 끝에 `---PAIRS---` 구분선을 넣고, 그 뒤에 (내용, 출처) 쌍의 JSON 배열을 붙인다:
   [{{"content": "...", "source": "..."}}, ...]
   각 content는 노트에서 실제로 쓴 구체적인 사실 하나(서로 다른 내용으로 최소 3개 이상 뽑는다 —
   같은 사실을 표현만 바꿔 중복으로 넣지 않는다). source는 그 사실의 근거 URL이다. 이 URL은 아래
   후보의 source 하나만 쓸 수 있다 (없는 링크를 만들어내지 않는다).

후보:
- 제목: {title}
- 한 줄 요약: {one_line}
- 카드 각도: {angle}
- 출처: {source}

기사 원문(참고용, 없으면 "없음"):
{article_text}
"""


def run_deep_research(client: OpenAI, candidate: dict) -> tuple[str, list[dict] | None, bool]:
    article_text = fetch_article_text(candidate.get("source", ""))
    prompt = RESEARCH_NOTE_PROMPT.format(
        title=candidate.get("title", ""),
        one_line=candidate.get("one_line", ""),
        angle=candidate.get("angle", ""),
        source=candidate.get("source", ""),
        article_text=article_text or "없음",
    )
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

    return md_part, pairs, article_text is not None


@st.dialog("딥리서치 결과", width="large")
def show_research_dialog():
    st.markdown(st.session_state.research_md)


@st.dialog("content.json 편집", width="large")
def show_json_dialog():
    text = json.dumps(st.session_state.content, ensure_ascii=False, indent=2)
    edited = st.text_area("JSON", value=text, height=480, key="content_json_edit_area")
    if st.button("적용", type="primary"):
        try:
            parsed = json.loads(edited)
        except json.JSONDecodeError as e:
            st.error(f"JSON 파싱 실패: {e} — 기존 값을 유지합니다.")
        else:
            st.session_state.content = parsed
            st.success("적용됨")
            st.rerun()


# ============================================================
# 세션 상태 초기화
# ============================================================
DEFAULTS = {
    "candidates": [],
    "selected": None,
    "research_md": None,
    "research_pairs": None,
    "content": None,
    "image_path": None,
    "out_dir": None,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

st.session_state.setdefault("content_id", f"{date.today().isoformat().replace('-', '')}-01")

st.title("칼퇴각 파이프라인")
content_id = st.text_input("콘텐츠 ID", key="content_id")
st.divider()

# ============================================================
# 1단계 — 후보 가져오기
# ============================================================
st.header("1단계 — 후보 가져오기")

if st.button("후보 가져오기", type="primary"):
    with st.spinner("최근 24시간 수집 및 GPT-5.5 선별 중... (몇 분 걸릴 수 있습니다)"):
        result = subprocess.run(
            [sys.executable, str(HERE / "Research.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    if result.stderr:
        with st.expander("실행 로그 (stderr)"):
            st.code(result.stderr)
    if result.returncode != 0:
        st.error("후보 가져오기 실패")
    else:
        files = sorted(CAND_DIR.glob("*.json"))
        if files:
            st.session_state.candidates = json.loads(files[-1].read_text(encoding="utf-8"))
            st.session_state.selected = None
            st.success(f"후보 {len(st.session_state.candidates)}개 로드")
        else:
            st.warning("후보 파일을 찾지 못했습니다.")

if not st.session_state.candidates:
    st.info("후보 없음 — 위에서 가져오기를 실행하거나 과거 파일을 선택하세요.")
    past_files = sorted(CAND_DIR.glob("*.json"), reverse=True)
    if past_files:
        picked = st.selectbox("과거 후보 파일", past_files, format_func=lambda p: p.stem, key="past_cand_pick")
        if st.button("이 파일 불러오기"):
            st.session_state.candidates = json.loads(picked.read_text(encoding="utf-8"))
            st.session_state.selected = None
else:
    labels = [
        f"{c.get('id', '?')} · {c.get('title', '(제목 없음)')} · {c.get('angle', '')}"
        for c in st.session_state.candidates
    ]
    idx = st.radio(
        "후보 선택",
        options=range(len(st.session_state.candidates)),
        format_func=lambda i: labels[i],
        key="cand_radio",
    )
    st.session_state.selected = st.session_state.candidates[idx]

    with st.expander("상세 보기"):
        c = st.session_state.selected
        st.markdown(f"**one_line**: {c.get('one_line', '')}")
        st.markdown(f"**why_now**: {c.get('why_now', '')}")
        st.markdown(f"**source**: {c.get('source', '')}")
        st.markdown(f"**visual**: {c.get('visual', '')}")

st.divider()

# ============================================================
# 2단계 — 딥리서치
# ============================================================
st.header("2단계 — 딥리서치")

if not st.session_state.selected:
    st.info("먼저 1단계에서 후보를 선택하세요.")
else:
    if st.button("딥리서치 실행", type="primary"):
        try:
            client = get_client()
            with st.spinner("원문 조회 및 딥리서치 중..."):
                md_part, pairs, fetched = run_deep_research(client, st.session_state.selected)
            st.session_state.research_md = md_part
            st.session_state.research_pairs = pairs

            RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
            (RESEARCH_DIR / f"{content_id}.md").write_text(md_part, encoding="utf-8")

            if not fetched:
                st.caption("원문을 가져오지 못해 후보 요약만으로 진행했습니다.")

            if pairs is None:
                st.error("PAIRS JSON 파싱 실패 — 「딥리서치 결과 보기」에서 원문을 확인하세요.")
            else:
                st.success(f"딥리서치 완료 — 근거 {len(pairs)}개 확보")
        except Exception as e:
            st.error(f"딥리서치 실패: {e}")

    if st.session_state.research_md:
        if st.button("딥리서치 결과 보기"):
            show_research_dialog()

st.divider()

# ============================================================
# 3단계 — content.json 생성 + 편집
# ============================================================
st.header("3단계 — 콘텐츠 JSON")

if not st.session_state.research_pairs:
    st.info("먼저 2단계에서 딥리서치를 완료하세요 (근거가 1개 이상 있어야 합니다).")
else:
    if st.button("콘텐츠 JSON 생성", type="primary"):
        try:
            client = get_client()
            with st.spinner("content.json 생성 중..."):
                content = generate_content_json(client, st.session_state.research_pairs, content_id)
            st.session_state.content = content
            st.success("생성 완료")
        except Exception as e:
            st.error(f"생성 실패: {e}")

    if st.session_state.content:
        if st.button("JSON 보기/편집"):
            show_json_dialog()

st.divider()

# ============================================================
# 4단계 — 표지 이미지 생성
# ============================================================
st.header("4단계 — 표지 이미지 생성")

if not st.session_state.content:
    st.info("먼저 3단계에서 콘텐츠 JSON을 생성하세요.")
else:
    concept = st.session_state.content.get("cover", {}).get("headline", "").replace("\n", " ")
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
            if path:
                st.session_state.image_path = path
                st.session_state.content["cover"]["image"] = path
            else:
                st.session_state.content["cover"]["image"] = None
                st.warning("폴백: 단색 배경으로 진행됩니다.")
        except Exception as e:
            st.error(f"이미지 생성 실패: {e}")

    if st.session_state.image_path:
        st.image(to_local_path(st.session_state.image_path), width=320)

st.divider()

# ============================================================
# 5단계 — 콘텐츠 렌더 (PNG)
# ============================================================
st.header("5단계 — 콘텐츠 렌더")

if not st.session_state.content:
    st.info("먼저 3~4단계를 완료하세요.")
else:
    if st.button("콘텐츠 생성", type="primary"):
        try:
            CONTENT_DIR.mkdir(parents=True, exist_ok=True)
            (CONTENT_DIR / f"{content_id}.json").write_text(
                json.dumps(st.session_state.content, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            out_dir = OUT_ROOT / content_id
            out_dir.mkdir(parents=True, exist_ok=True)
            content_json_path = out_dir / "content.json"
            content_json_path.write_text(
                json.dumps(st.session_state.content, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            with st.spinner("렌더 중..."):
                result = subprocess.run(
                    [sys.executable, str(HERE / "Render.py"), str(content_json_path), str(out_dir)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )

            if result.returncode != 0:
                st.error("렌더 실패")
                st.code(result.stderr or result.stdout)
            else:
                st.success("렌더 완료")
                st.session_state.out_dir = out_dir

                history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
                headline = st.session_state.content.get("cover", {}).get("headline", "").split("\n")[0]
                slides = st.session_state.content.get("slides", [])
                source = slides[0].get("source", "") if slides else ""
                entry = {
                    "id": content_id,
                    "date": date.today().isoformat(),
                    "title": headline,
                    "source": source,
                    "posted": False,
                }
                history = [h for h in history if h.get("id") != content_id]
                history.append(entry)
                HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            st.error(f"렌더 실패: {e}")

    if st.session_state.out_dir:
        out_dir = st.session_state.out_dir
        carousel_dir = out_dir / "carousel"
        story_dir = out_dir / "story"
        if carousel_dir.exists():
            imgs = sorted(carousel_dir.glob("*.png"))
            if imgs:
                st.caption(f"캐러셀 (4:5) · {len(imgs)}장")
                for col, img in zip(st.columns(len(imgs)), imgs):
                    col.image(str(img))
        if story_dir.exists():
            imgs = sorted(story_dir.glob("*.png"))
            if imgs:
                st.caption(f"스토리 (9:16) · {len(imgs)}장")
                for col, img in zip(st.columns(len(imgs)), imgs):
                    col.image(str(img))

st.divider()

# ============================================================
# 6단계 — 릴스 렌더 (MP4)
# ============================================================
st.header("6단계 — 릴스 렌더")

if not st.session_state.out_dir:
    st.info("먼저 5단계에서 콘텐츠를 렌더하세요.")
else:
    music_files = []
    if MUSIC_DIR.exists():
        for pattern in MUSIC_EXTS:
            music_files.extend(MUSIC_DIR.glob(pattern))
    music_files = sorted(music_files)

    if not music_files:
        st.warning(f"`{MUSIC_DIR.name}/` 폴더에 배경음악 파일이 없습니다.")
    else:
        picked_music = st.selectbox("배경음악", music_files, format_func=lambda p: p.name, key="reel_music_pick")
        if st.button("릴스 생성", type="primary"):
            out_dir = st.session_state.out_dir
            story_dir = out_dir / "story"
            reel_path = out_dir / "reel.mp4"
            try:
                with st.spinner("릴스 생성 중... (ffmpeg)"):
                    result = subprocess.run(
                        [
                            sys.executable, str(HERE / "Render_reel.py"),
                            "--images", str(story_dir),
                            "--music", str(picked_music),
                            "--out", str(reel_path),
                        ],
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                    )
                if result.returncode != 0:
                    st.error("릴스 생성 실패")
                    st.code(result.stderr or result.stdout)
                else:
                    st.success("완료")
                    st.video(str(reel_path))
            except Exception as e:
                st.error(f"릴스 생성 실패: {e}")

st.divider()
st.caption("업로드는 인스타 앱에서 직접 진행하세요.")
