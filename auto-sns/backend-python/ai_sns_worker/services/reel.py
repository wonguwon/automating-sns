"""릴스 대본 생성 및 장면 계획.

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO를 받고 result DTO를 반환한다.
- 실패는 예외로 알린다. 단, `generate_reel_script`는 실제 GPT 호출(비용 발생)이 필요하다 —
  코드는 이관해뒀지만 실제 실행 전에는 반드시 사용자 확인을 받는다(2026-08-03,
  `wiki/decisions.md` 참고).

legacy 대응: legacy/pipeline_common.py
(build_reel_script_prompt, run_reel_script_prompt, REEL_SCRIPT_SYSTEM_PROMPT,
REEL_SCRIPT_USER_PROMPT)

릴스 사진 라이브러리(assets/reel_photos/ + index.json, legacy: load_reel_photo_index/
add_reel_photo/delete_reel_photo)는 이번 단계에서 이관하지 않았다 — 이 함수는 그 목록을
호출부가 넘겨주는 `photo_library` 인자로만 받는다(파일 저장은 별도 관심사, 필요해지면
services/reel_photos.py 등으로 분리할지 결정한다).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..core.clients import get_openai_client
from ..core.paths import REEL_SCRIPT_DIR
from . import pipeline

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


@dataclass
class GenerateReelScriptRequest:
    content_id: str
    research_note: str
    photo_library: list[dict] = field(default_factory=list)
    direction: str = ""


@dataclass
class GenerateReelScriptResult:
    content_id: str
    script: dict | None
    raw_output: str
    saved_path: Path | None


def _build_reel_script_prompt(request: GenerateReelScriptRequest) -> tuple[str, str]:
    """legacy: pipeline_common.build_reel_script_prompt"""
    if request.photo_library:
        lib_text = "\n".join(f"- {e['file']}: {e['description']}" for e in request.photo_library)
    else:
        lib_text = "(등록된 사진 없음 — 모든 장면을 새로 생성해야 한다)"

    user_prompt = REEL_SCRIPT_USER_PROMPT.format(
        content_id=request.content_id,
        direction=request.direction.strip() or "(없음)",
        photo_library=lib_text,
        research_note=request.research_note,
    )
    return REEL_SCRIPT_SYSTEM_PROMPT, user_prompt


def generate_reel_script(request: GenerateReelScriptRequest) -> GenerateReelScriptResult:
    """조사 노트+방향성 입력으로 나레이션 대본(장면 지정 포함)을 생성한다. 파싱에 성공하면
    저장하고 services/pipeline.py 매니페스트에 reel_script_path를 기록한다. 파싱에 실패하면
    (모델이 스키마를 어긴 JSON을 내놓은 경우) 예외 대신 script=None + 원본 출력을 그대로
    돌려준다 — services/cardnews.py의 generate_content_json과 동일한 의도적 설계다.
    실제 GPT 호출(비용 발생) — 실행 전 사용자 확인 필요(모듈 docstring 참고).
    legacy: pipeline_common.run_reel_script_prompt"""
    system_prompt, user_prompt = _build_reel_script_prompt(request)

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
        script = json.loads(cleaned)
    except json.JSONDecodeError:
        return GenerateReelScriptResult(content_id=request.content_id, script=None, raw_output=raw, saved_path=None)

    script["id"] = request.content_id

    REEL_SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = REEL_SCRIPT_DIR / f"{request.content_id}.json"
    saved_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id=request.content_id, reel_script_path=str(saved_path))
    )

    return GenerateReelScriptResult(
        content_id=request.content_id, script=script, raw_output=raw, saved_path=saved_path
    )


# ============================================================
# 장면 이미지 → 대본 연결 — legacy에 대응 함수 없음(장면 이미지 준비 UI 단계에서만 수행됨,
# 2026-08-03 확인). services/image.py의 generate_scene_image가 만든 이미지 경로를
# services/render.py의 render_reel이 읽는 resolved_image_path에 이어주는 다리 역할.
# ============================================================
@dataclass
class SetSceneResolvedImageRequest:
    content_id: str
    scene_index: int
    image_path: str


@dataclass
class SetSceneResolvedImageResult:
    content_id: str
    scene_index: int
    script: dict


def set_scene_resolved_image(request: SetSceneResolvedImageRequest) -> SetSceneResolvedImageResult:
    """저장된 릴스 대본(services/pipeline.py 매니페스트의 reel_script_path)의
    scenes[scene_index]에 resolved_image_path를 채워 다시 저장한다."""
    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id=request.content_id))
    if not state.reel_script_path:
        raise FileNotFoundError(f"릴스 대본이 아직 생성되지 않았습니다: {request.content_id}")

    script_path = Path(state.reel_script_path)
    if not script_path.exists():
        raise FileNotFoundError(f"대본 파일을 찾을 수 없습니다: {script_path}")

    script = json.loads(script_path.read_text(encoding="utf-8"))
    scenes = script.get("scenes", [])
    if not (0 <= request.scene_index < len(scenes)):
        raise IndexError(f"장면 인덱스가 범위를 벗어났습니다: {request.scene_index}")

    scenes[request.scene_index]["resolved_image_path"] = request.image_path
    script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    return SetSceneResolvedImageResult(content_id=request.content_id, scene_index=request.scene_index, script=script)
