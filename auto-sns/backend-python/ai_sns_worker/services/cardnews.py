"""카드뉴스 content.json 생성 + 인스타 캡션 생성.

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO를 받고 result DTO를 반환한다.
- 실패는 예외로 알린다. 단, `generate_content_json`/`generate_insta_caption`은 실제 GPT
  호출(비용 발생)이 필요하다 — 코드는 이관해뒀지만 실제 실행 전에는 반드시 사용자 확인을
  받는다(2026-08-03, `wiki/decisions.md` 참고).

legacy 대응:
- legacy/pipeline_common.py (build_content_json_prompt, run_content_json_prompt,
  run_insta_caption, CONTENT_JSON_USER_PROMPT, INSTA_CAPTION_PROMPT)
- legacy/Generate.py (generate_content_json — 구 CLI 경로, pairs 기반이라 이관 대상 아님.
  실제 화면에서 쓰인 건 pipeline_common의 build_content_json_prompt/run_content_json_prompt다)

템플릿 세트(template.html/prompt.md/예시) 관리 함수는 services/templates.py로 이관했다
(2026-08-03, wiki/decisions.md 참고) — generate_content_json의 시스템 프롬프트는 그
services/templates.py의 `get_template`이 돌려주는 prompt.md 내용을 그대로 쓴다.

`get_content_json`은 저장된 파일을 읽기만 하므로 GPT 호출 없이 이미 이관 완료했다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..core.clients import get_openai_client
from ..core.paths import CONTENT_DIR
from . import pipeline, templates


@dataclass
class GetContentJsonRequest:
    content_id: str


@dataclass
class GetContentJsonResult:
    content_id: str
    content_path: Path
    content_text: str


def get_content_json(request: GetContentJsonRequest) -> GetContentJsonResult:
    """저장된 content.json을 조회한다. 경로는 services/pipeline.py 매니페스트의
    `content_path`를 그대로 따른다(그쪽이 canonical) — services/research.py의
    get_research_note와 동일한 패턴.
    legacy: 파일 시스템 data/content/*.json 직접 읽기 대응"""
    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id=request.content_id))
    if not state.content_path:
        raise FileNotFoundError(f"카드뉴스 content.json이 아직 생성되지 않았습니다: {request.content_id}")

    path = Path(state.content_path)
    if not path.exists():
        raise FileNotFoundError(f"content.json 파일을 찾을 수 없습니다: {path}")

    return GetContentJsonResult(
        content_id=request.content_id, content_path=path, content_text=path.read_text(encoding="utf-8")
    )


# ============================================================
# 카드뉴스 content.json 생성 — legacy: pipeline_common.build_content_json_prompt/
# run_content_json_prompt/CONTENT_JSON_USER_PROMPT
# ============================================================
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


@dataclass
class GenerateContentJsonRequest:
    content_id: str
    template_name: str
    research_note: str
    source_urls: list[str] = field(default_factory=list)
    brand: str = ""
    handle: str = ""
    audience: str = ""
    direction: str = ""


@dataclass
class GenerateContentJsonResult:
    content_id: str
    content: dict | None
    raw_output: str
    saved_path: Path | None


def _build_content_json_prompt(request: GenerateContentJsonRequest, system_prompt: str) -> str:
    urls = [u for u in dict.fromkeys(request.source_urls) if u]
    return CONTENT_JSON_USER_PROMPT.format(
        content_id=request.content_id,
        brand=request.brand.strip() or "(없음)",
        handle=request.handle.strip() or "(없음)",
        audience=request.audience.strip() or "(없음)",
        direction=request.direction.strip() or "(없음)",
        sources="\n".join(f"- {u}" for u in urls) if urls else "(목록 없음 — 노트의 「출처」 섹션에 있는 URL을 사용)",
        research_note=request.research_note,
    )


def generate_content_json(request: GenerateContentJsonRequest) -> GenerateContentJsonResult:
    """조사 노트+템플릿+계정정보로 카드뉴스 JSON을 생성한다. 파싱에 성공하면 저장하고
    services/pipeline.py 매니페스트에 content_path를 기록한다. 파싱에 실패하면(모델이 스키마를
    어긴 JSON을 내놓은 경우) 예외를 던지지 않고 content=None + 원본 출력을 그대로 돌려준다 —
    legacy와 동일하게, 사용자가 원본을 보고 프롬프트를 고쳐 재시도할 수 있게 하기 위한 의도적인
    설계다(무엇을 실패로 볼지의 판단이라 예외로 감추지 않는다).
    실제 GPT 호출(비용 발생) — 실행 전 사용자 확인 필요(모듈 docstring 참고).
    legacy: pipeline_common.build_content_json_prompt/run_content_json_prompt"""
    template = templates.get_template(templates.GetTemplateRequest(name=request.template_name))
    system_prompt = template.prompt
    user_prompt = _build_content_json_prompt(request, system_prompt)

    client = get_openai_client()
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
        return GenerateContentJsonResult(
            content_id=request.content_id, content=None, raw_output=raw, saved_path=None
        )

    content["id"] = request.content_id

    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = CONTENT_DIR / f"{request.content_id}.json"
    saved_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")

    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id=request.content_id, content_path=str(saved_path))
    )

    return GenerateContentJsonResult(
        content_id=request.content_id, content=content, raw_output=raw, saved_path=saved_path
    )


# ============================================================
# 표지 이미지 → content.json 연결 — legacy에 대응 함수 없음(카드뉴스 제작 UI 단계에서만
# 수행됨, 2026-08-03 실제 스모크 테스트 중 발견: generate_cover_image가 만든 이미지가
# content.json의 cover.image에 반영되지 않으면 render_cardnews가 null로 렌더해 표지
# 이미지 없이 단색 폴백으로 나온다). services/reel.py의 set_scene_resolved_image와 같은
# 역할의 다리 함수.
# ============================================================
@dataclass
class SetCoverImageRequest:
    content_id: str
    image_uri: str


@dataclass
class SetCoverImageResult:
    content_id: str
    content: dict


def set_cover_image(request: SetCoverImageRequest) -> SetCoverImageResult:
    """저장된 content.json(services/pipeline.py 매니페스트의 content_path)의 cover.image를
    채워 다시 저장한다 — services/image.py의 generate_cover_image 결과와 content.json을
    잇는 다리."""
    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id=request.content_id))
    if not state.content_path:
        raise FileNotFoundError(f"카드뉴스 content.json이 아직 생성되지 않았습니다: {request.content_id}")

    path = Path(state.content_path)
    if not path.exists():
        raise FileNotFoundError(f"content.json 파일을 찾을 수 없습니다: {path}")

    content = json.loads(path.read_text(encoding="utf-8"))
    content.setdefault("cover", {})["image"] = request.image_uri
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")

    return SetCoverImageResult(content_id=request.content_id, content=content)


# ============================================================
# 인스타 캡션 생성 — legacy: pipeline_common.run_insta_caption/INSTA_CAPTION_PROMPT
# ============================================================
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


@dataclass
class GenerateInstaCaptionRequest:
    research_note: str


@dataclass
class GenerateInstaCaptionResult:
    caption: str


def generate_insta_caption(request: GenerateInstaCaptionRequest) -> GenerateInstaCaptionResult:
    """조사 노트로 인스타 업로드용 설명문구(+해시태그)를 생성한다. 파일로 저장하지 않는다 —
    legacy도 caption은 content.json 편집 화면에서 사용자가 직접 붙여넣도록 텍스트만 돌려준다.
    실제 GPT 호출(비용 발생) — 실행 전 사용자 확인 필요(모듈 docstring 참고).
    legacy: pipeline_common.run_insta_caption"""
    client = get_openai_client()
    resp = client.chat.completions.create(
        model="gpt-5.5",
        messages=[{"role": "user", "content": INSTA_CAPTION_PROMPT.format(research_note=request.research_note)}],
    )
    return GenerateInstaCaptionResult(caption=resp.choices[0].message.content.strip())
