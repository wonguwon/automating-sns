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
import shutil
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

# 릴스 제작(2026-07-30~) — 대본/장면 이미지/TTS 오디오/최종 mp4 경로.
REEL_SCRIPT_DIR = DATA / "reel_script"
REEL_IMAGES_DIR = DATA / "reel_images"
REEL_AUDIO_DIR = DATA / "reel_audio"
REEL_OUT_ROOT = HERE / "릴스"
REEL_PHOTOS_DIR = ASSETS_DIR / "reel_photos"
REEL_PHOTOS_INDEX = REEL_PHOTOS_DIR / "index.json"
REEL_PHOTO_EXTS = (".png", ".jpg", ".jpeg", ".webp")

for d in (
    DATA, CAND_DIR, RESEARCH_DIR, CONTENT_DIR, PIPELINE_DIR, RSS_COLLECT_DIR, ASSETS_DIR, SOURCES_DIR,
    REEL_SCRIPT_DIR, REEL_IMAGES_DIR, REEL_AUDIO_DIR, REEL_OUT_ROOT, REEL_PHOTOS_DIR,
):
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


def is_valid_template_name(name: str) -> bool:
    """템플릿 폴더명으로 안전한지 검사한다 — 경로 조작 문자(`/`, `\\`, `..`)와 빈 값을 막는다."""
    name = name.strip()
    if not name or name in (".", ".."):
        return False
    return not any(c in name for c in ("/", "\\", "\0"))


def create_template(name: str, html_bytes: bytes, prompt_bytes: bytes) -> Path:
    """
    새 템플릿 폴더(templates/<name>/)를 만들고 template.html·prompt.md를 저장한다.
    템플릿 관리 페이지는 이 둘을 화면에서 새로 작성해주지 않는다 — 이미 만들어둔 파일을
    업로드해서 세트로 저장하는 파일 관리 UI다(2026-07-30 사용자 결정, LIMITS 검증 로직이
    있는 template.html을 직접 만드는 건 이 UI 범위 밖).
    """
    name = name.strip()
    if not is_valid_template_name(name):
        raise ValueError(f"템플릿 이름으로 쓸 수 없습니다: {name!r}")
    template_dir = TEMPLATES_DIR / name
    if template_dir.exists():
        raise ValueError(f"이미 같은 이름의 템플릿이 있습니다: {name}")
    template_dir.mkdir(parents=True)
    (template_dir / "template.html").write_bytes(html_bytes)
    (template_dir / "prompt.md").write_bytes(prompt_bytes)
    return template_dir


def update_template_files(
    template_dir: Path, html_bytes: bytes | None = None, prompt_bytes: bytes | None = None
):
    """기존 템플릿의 template.html·prompt.md를 덮어쓴다 — 인자로 넘긴 것만 갱신한다."""
    if html_bytes is not None:
        (template_dir / "template.html").write_bytes(html_bytes)
    if prompt_bytes is not None:
        (template_dir / "prompt.md").write_bytes(prompt_bytes)


def add_template_examples(template_dir: Path, files: list[tuple[str, bytes]]) -> list[str]:
    """
    예시 이미지를 템플릿의 예시/ 폴더에 저장한다. 같은 파일명이 이미 있으면 조용히 덮어써서
    기존 예시를 잃지 않도록 "이름(1).png"처럼 번호를 붙여 저장한다.
    실제로 저장된 파일명 목록을 돌려준다(허용 확장자가 아닌 파일은 건너뛴다).
    """
    example_dir = template_dir / TEMPLATE_EXAMPLE_DIRNAME
    example_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for filename, data in files:
        p = Path(filename)
        if p.suffix.lower() not in TEMPLATE_EXAMPLE_EXTS:
            continue
        dest = example_dir / p.name
        n = 1
        while dest.exists():
            dest = example_dir / f"{p.stem}({n}){p.suffix}"
            n += 1
        dest.write_bytes(data)
        saved.append(dest.name)
    return saved


def delete_template_example(example_path: Path):
    """예시 이미지 한 장을 삭제한다."""
    example_path.unlink(missing_ok=True)


def delete_template(template_dir: Path):
    """템플릿 폴더 전체(template.html·prompt.md·예시/)를 삭제한다. 되돌릴 수 없다."""
    shutil.rmtree(template_dir)


# ============================================================
# 릴스 사진 라이브러리 — assets/reel_photos/ + index.json(파일명↔설명).
# 대본 생성 시 이 목록(파일명+설명)을 GPT에 함께 넘겨, 장면마다 기존 사진을 재사용할지
# 새로 생성할지 GPT가 직접 고르게 한다(2026-07-30 사용자 결정 — 짤 이미지도 미리 넣어두고
# 설명을 함께 관리).
# ============================================================
def load_reel_photo_index() -> list[dict]:
    """index.json을 읽는다. 파일이 실제로 존재하는 항목만 돌려준다(목록과 실제 파일이
    어긋나는 걸 방지)."""
    if not REEL_PHOTOS_INDEX.exists():
        return []
    entries = json.loads(REEL_PHOTOS_INDEX.read_text(encoding="utf-8"))
    return [e for e in entries if (REEL_PHOTOS_DIR / e["file"]).exists()]


def _save_reel_photo_index(entries: list[dict]):
    REEL_PHOTOS_INDEX.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def add_reel_photo(filename: str, data: bytes, description: str) -> str:
    """사진 한 장을 라이브러리에 추가한다. 같은 파일명이 있으면 번호를 붙여 저장한다
    (템플릿 예시 이미지 저장 방식과 동일). 실제로 저장된 파일명을 돌려준다."""
    p = Path(filename)
    if p.suffix.lower() not in REEL_PHOTO_EXTS:
        raise ValueError(f"지원하지 않는 이미지 형식입니다: {p.suffix}")
    dest = REEL_PHOTOS_DIR / p.name
    n = 1
    while dest.exists():
        dest = REEL_PHOTOS_DIR / f"{p.stem}({n}){p.suffix}"
        n += 1
    dest.write_bytes(data)

    entries = load_reel_photo_index()
    entries.append({"file": dest.name, "description": description.strip()})
    _save_reel_photo_index(entries)
    return dest.name


def delete_reel_photo(filename: str):
    """사진 한 장과 index.json의 해당 항목을 삭제한다."""
    (REEL_PHOTOS_DIR / filename).unlink(missing_ok=True)
    entries = [e for e in load_reel_photo_index() if e["file"] != filename]
    _save_reel_photo_index(entries)


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


# ============================================================
# 릴스 대본 생성 — 딥리서치 조사 노트 + 사진 라이브러리 목록 + 사용자 방향성(의견)을 참고해
# 줄 단위(화자·대사·장면) JSON 대본을 만든다(2026-07-30 개정).
# 대화체(캐릭터1/캐릭터2)와 대본 예시 참고는 제거했다 — 처음부터 대화형은 무리였고, 예시로
# 스타일을 흉내내기보다 "사실(조사 노트) + 의견(사용자가 입력하는 방향성)"을 결합해 쓰게 하는
# 편이 내용도 더 명확하고 저작권도 안전하다는 판단(사용자 결정).
# ============================================================
REEL_SCRIPT_SYSTEM_PROMPT = """당신은 짧고 명료한 인스타그램 릴스(쇼츠) 대본을 쓰는 작가다.

목표: 딥리서치 조사 노트에 있는 사실을 바탕으로, 소리 내어 읽었을 때 20~30초 분량의 대본을
쓴다. 화자는 항상 나레이션 1명이다(대화체·캐릭터 구분 없음).

분량 기준 (가장 중요 — 반드시 지켜라. 실측: 이 프로젝트 타입캐스트 TTS 기준 약 4.5~5자/초):
- 모든 줄의 대사(text)를 합친 글자 수(공백 포함)가 100~150자를 넘지 않게 쓴다.
- 줄 수는 6~10줄 내외, 각 줄은 10~20자 정도의 한 호흡 길이로 쓴다.
- 분량 기준과 아래 규칙이 충돌하면 분량 기준을 우선한다 — 조사 노트의 내용을 다 담으려 하지
  말고, 가장 임팩트 있는 사실 2~3개만 골라 압축해서 전달한다.

내용 구성:
- 이 소재에서 가장 중요한 부분(핵심 사실·왜 중요한지)만 골라 명확하게 전달한다. 군더더기
  설명이나 배경 설명은 과감히 생략한다.
- "방향성/의견"이 주어지면, 사실(조사 노트)은 그대로 유지하되 그 방향성이 제안하는 관점·논조를
  반영해서 문장을 새로 쓴다 — 사실과 의견을 결합해 쓰면 원문을 그대로 옮기는 게 아니므로
  저작권 문제로부터도 안전하다. 방향성이 없으면 소재에 맞는 논조를 스스로 정한다.

규칙:
- 사실(숫자·날짜·기관명)은 조사 노트에 있는 것만 쓰고 새로 지어내지 않는다.
- 저작권: 원문 문장을 그대로 옮기지 않고 새로 쓴다. 직접 인용이 필요하면 따옴표로 표시하고
  화자를 밝힌다.

제목(title): 화면 상단에 고정으로 표시할 제목을 두 줄로 만든다 — 1번째 줄은 상황·맥락을 짧게
던지고, 2번째 줄은 그 핵심·한방을 강조하는 문구로 쓴다(각 줄 6~14자 내외, 두 줄이 자연스럽게
이어지는 한 문장이거나 앞뒤 호응이 되게 쓴다). 2번째 줄은 화면에서 강조색(노란색)으로 표시되니
가장 임팩트 있는 부분을 2번째 줄에 배치한다.

장면(scene) 구성 — 이미지 생성 비용과 화면 산만함을 줄이기 위해, 장면은 대사 줄보다 훨씬 적게
잡는다:
- 전체 장면은 2~4개로 제한한다. 비슷한 맥락의 여러 줄은 같은 장면 하나를 공유해서, 그 줄들이
  재생되는 동안 같은 이미지가 유지되게 한다.
- 각 장면에는 화면을 다이나믹하게 만들 카메라 움직임(motion)을 하나 지정한다: "zoom_in"(서서히
  확대), "zoom_out"(서서히 축소), "pan_left"(좌로 서서히 이동), "pan_right"(우로 서서히 이동),
  "static"(움직임 없음) 중 하나.
- "보유 사진 목록"에 어울리는 사진이 있으면 그 파일명을 그대로 골라 쓰고(목록에 없는 파일명을
  만들어내지 않는다), 없으면 새로 생성할 이미지 컨셉을 문장으로 쓴다.

출력은 아래 스키마의 JSON 하나만 — 설명이나 코드펜스 없이 그대로 출력한다:
{
  "title_line1": "...",
  "title_line2": "...",
  "scenes": [
    {
      "visual_concept": "...",
      "image_source": "existing 또는 generate",
      "image_file": "보유 사진 목록에 있는 파일명 또는 null",
      "motion": "zoom_in, zoom_out, pan_left, pan_right, static 중 하나"
    }
  ],
  "lines": [
    {"speaker": "나레이션", "text": "...", "scene_index": 0}
  ]
}
scene_index는 scenes 배열의 0부터 시작하는 인덱스다. speaker는 모든 줄에서 "나레이션"으로
통일한다.
"""

REEL_SCRIPT_USER_PROMPT = """오늘 채택된 소재 ID: {content_id}

방향성/의견 ("(없음)"이면 소재에 맞는 논조를 자유롭게 정한다):
{direction}

보유 사진 목록 (기존 파일 재사용 시 이 중에서만 골라라 — 목록에 없는 파일명을 만들어내지 않는다):
{photo_library}

아래는 딥리서치 조사 노트다. 이 안에 있는 사실만 사용해서 대본을 써라.

{research_note}
"""


def build_reel_script_prompt(
    content_id: str, research_note: str, photo_library: list[dict], direction: str = "",
) -> tuple[str, str]:
    """(시스템 프롬프트, 사용자 프롬프트)를 조립한다. 사용자 프롬프트는 화면에서 보여주고
    실행 전 수정할 수 있게 한다(카드뉴스 JSON 생성과 동일한 패턴)."""
    if photo_library:
        lib_text = "\n".join(f"- {e['file']}: {e['description']}" for e in photo_library)
    else:
        lib_text = "(등록된 사진 없음 — 모든 장면을 새로 생성해야 한다)"

    user_prompt = REEL_SCRIPT_USER_PROMPT.format(
        content_id=content_id,
        direction=direction.strip() or "(없음)",
        photo_library=lib_text,
        research_note=research_note,
    )
    return REEL_SCRIPT_SYSTEM_PROMPT, user_prompt


def run_reel_script_prompt(
    client: OpenAI, system_prompt: str, user_prompt: str, content_id: str
) -> tuple[dict | None, str]:
    """릴스 대본 생성 프롬프트를 실행한다. (파싱된 dict 또는 None, 모델 원본 출력)을 반환한다."""
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
        script = json.loads(cleaned)
    except json.JSONDecodeError:
        return None, raw

    script["id"] = content_id
    return script, raw


OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ARK_API_KEY = os.environ.get("ARK_API_KEY")
TYPECAST_API_KEY = os.environ.get("TYPECAST_API_KEY")
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


def _generate_image_to_path(
    client: OpenAI, prompt: str, out_path: Path, quality: str, provider: str = "openai",
    size_seedream: str = "1664x2496", size_openai: str = "1024x1536",
) -> str | None:
    """
    화면에서 편집한 프롬프트를 그대로 이미지 생성 API에 보내 out_path에 저장한다.
    표지 이미지(generate_cover_image_raw)와 릴스 장면 이미지(generate_scene_image_raw)가
    저장 경로와 목표 비율만 다르고 나머지 로직은 같아 공용으로 뺐다 — 크기는 호출자가 지정한다
    (표지는 2:3 세로, 릴스 장면은 4:3 가로 — 2026-07-31).

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
                # Seedream은 최소 3,686,400픽셀 이상을 요구한다 — 호출자가 넘기는 size가 이를
                # 만족하는지는 호출자 책임(표지 1664x2496, 릴스 장면 2280x1710 모두 실측으로 확인됨).
                size=size_seedream,
                # watermark는 openai SDK의 images.generate()가 아는 파라미터가 아니라
                # (Ark 전용 필드) extra_body로 넘겨야 요청 바디에 실제로 포함된다.
                extra_body={"watermark": False},
            )
        else:
            resp = client.images.generate(
                model="gpt-image-2",
                prompt=prompt,
                size=size_openai,
                quality=quality,
            )
        item = resp.data[0]
        out_path.parent.mkdir(parents=True, exist_ok=True)

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


def generate_cover_image_raw(
    client: OpenAI, prompt: str, content_id: str, quality: str, provider: str = "openai"
) -> str | None:
    """카드뉴스 표지 이미지를 assets/cover-<id>.png에 생성한다."""
    out_path = ASSETS_DIR / f"cover-{content_id}.png"
    return _generate_image_to_path(client, prompt, out_path, quality, provider)


# 릴스 화면은 이미지를 4:3 가로형으로 중앙에 배치한다(2026-07-31 레터박스 개편). Seedream은
# 최소 3,686,400픽셀 요구를 넉넉히 넘기는 4:3 크기(2280x1710, 실측 확인됨), GPT Image 2는 4:3
# 프리셋이 없어 가장 가까운 가로형 프리셋(1536x1024, 3:2, 실측 확인됨)을 쓴다.
REEL_SCENE_SIZE_SEEDREAM = "2280x1710"
REEL_SCENE_SIZE_OPENAI = "1536x1024"

# 카드뉴스 표지용 IMAGE_PROMPT_TEMPLATE(세로형 썸네일 전제, 하단 어둡게 처리 언급)을 그대로 쓰면
# 릴스의 4:3 가로 이미지와 맞지 않아 릴스 전용으로 따로 둔다 — 카드뉴스 쪽 특정 구도 지시(인물
# 뒷모습·클로즈업 등 다양화, 하단 여백 확보)도 릴스에는 굳이 강제하지 않는다(2026-07-31, 사용자 판단).
REEL_IMAGE_PROMPT_TEMPLATE = """한국 뉴스 릴스(쇼츠) 영상의 배경 장면으로 쓸 사실적인 보도사진을 만들어주세요.

장면: {concept}

스타일: 한국에서 실제 기자가 촬영한 보도사진처럼 자연스럽고 신뢰감 있게 표현합니다. 흐린 날의 부드러운 자연광, 낮은 채도, 절제된 색감, 35mm 다큐멘터리 사진, 현실적인 인체와 건축물, 과장되지 않은 긴장감을 사용합니다. 화면 비율은 가로로 넓은 4:3 구도입니다.

제외: 영화 포스터, 스톡사진 포즈, SF 인터페이스, 일러스트, 3D 렌더링, 글자, 워터마크를 제외합니다."""


def generate_scene_image_raw(
    client: OpenAI, prompt: str, content_id: str, scene_index: int, quality: str, provider: str = "openai"
) -> str | None:
    """릴스 장면 이미지를 data/reel_images/<id>/scene_<NN>.png에 생성한다. 장면 하나를 여러 줄이
    공유하므로(2026-07-30 스키마 변경) 줄이 아니라 장면 인덱스 기준으로 저장한다."""
    out_path = REEL_IMAGES_DIR / content_id / f"scene_{scene_index:02d}.png"
    return _generate_image_to_path(
        client, prompt, out_path, quality, provider,
        size_seedream=REEL_SCENE_SIZE_SEEDREAM, size_openai=REEL_SCENE_SIZE_OPENAI,
    )


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


# ============================================================
# 타입캐스트(Typecast) TTS — 릴스 대본 한 줄을 오디오로 합성한다(2026-07-30).
# emotion_type="smart"로 앞/뒤 줄 텍스트를 문맥으로 넘겨 감정을 자동으로 바꾼다 —
# 대본 예시들의 "문장마다 감정이 바뀌는" 리듬을 코드로 재현하기 위한 선택.
# ============================================================
TYPECAST_BASE_URL = "https://api.typecast.ai"


def list_typecast_voices() -> list[dict] | None:
    """GET /v2/voices로 사용 가능한 음성 목록을 조회한다. 키가 없거나 호출이 실패하면 None을
    돌려주고 화면에 에러를 보여준다 — 이 경우 화자별 voice_id는 직접 입력해야 한다."""
    if not TYPECAST_API_KEY:
        st.error("TYPECAST_API_KEY가 없습니다. 이 폴더의 .env 파일에 TYPECAST_API_KEY=...를 추가하세요.")
        return None
    try:
        resp = requests.get(
            f"{TYPECAST_BASE_URL}/v2/voices",
            headers={"X-API-KEY": TYPECAST_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        # 공식 문서에 정확한 응답 스키마가 명시돼 있지 않아, 리스트 자체이거나
        # {"voices": [...]} / {"data": [...]} 형태일 가능성을 모두 처리한다.
        if isinstance(data, list):
            return data
        return data.get("voices") or data.get("data") or []
    except Exception as e:
        st.error(f"음성 목록 조회 실패: {e}")
        return None


# 목소리는 우선 "민욱"(Minuk, 남성/중년, ssfm-v30 감정 7종 전부 지원)으로 고정한다 — 여러
# 목소리 중 고르는 셀렉트박스는 추후에 붙인다(2026-07-30 사용자 결정).
REEL_DEFAULT_VOICE_ID = "tc_68f0727fd62a5934102f7ec0"
REEL_EMOTION_PRESETS = ["normal", "happy", "sad", "angry", "whisper", "toneup", "tonedown"]


def synthesize_reel_line(
    text: str, voice_id: str, out_path: Path,
    previous_text: str = "", next_text: str = "",
    model: str = "ssfm-v30", audio_format: str = "mp3",
    audio_tempo: float = 1.0,
    emotion_type: str = "smart",
    emotion_preset: str = "normal",
    emotion_intensity: float = 1.0,
) -> bool:
    """
    대본 한 줄을 타입캐스트 TTS로 합성해 out_path에 저장한다. 성공하면 True, 실패하면
    False를 돌려주고 화면에 에러를 보여준다.

    emotion_type: "smart"(문맥 기반 자동 — previous_text/next_text로 감정을 정함) 또는
    "preset"(emotion_preset/emotion_intensity로 감정을 직접 고정).
    audio_tempo: 0.5~2.0 배속(1.0 기본).
    """
    if not TYPECAST_API_KEY:
        st.error("TYPECAST_API_KEY가 없습니다. 이 폴더의 .env 파일에 TYPECAST_API_KEY=...를 추가하세요.")
        return False
    if emotion_type == "preset":
        prompt = {"emotion_type": "preset", "emotion_preset": emotion_preset, "emotion_intensity": emotion_intensity}
    else:
        prompt = {"emotion_type": "smart", "previous_text": previous_text, "next_text": next_text}
    body = {
        "voice_id": voice_id,
        "text": text,
        "model": model,
        "prompt": prompt,
        "output": {"audio_format": audio_format, "audio_tempo": audio_tempo},
    }
    try:
        resp = requests.post(
            f"{TYPECAST_BASE_URL}/v1/text-to-speech",
            headers={"X-API-KEY": TYPECAST_API_KEY, "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        if resp.status_code != 200:
            st.error(f"TTS 실패({resp.status_code}): {resp.text[:300]}")
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
        return True
    except Exception as e:
        st.error(f"TTS 요청 실패: {e}")
        return False
