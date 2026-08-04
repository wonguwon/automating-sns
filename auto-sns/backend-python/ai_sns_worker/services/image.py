"""표지/장면 이미지 생성 (Doubao-Seedream 기본, GPT Image 2 선택).

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO를 받고 result DTO를 반환한다.
- API 키가 없으면 예외(ValueError, core/clients.py)로 알린다 — 설정 문제이므로 즉시 실패한다.
- 하지만 실제 이미지 생성 API 호출 자체가 실패하면(네트워크/응답 형식 등) 예외를 던지지
  않고 `image_uri=None` + `error` 메시지를 결과에 담아 돌려준다 — legacy도 이미지 생성
  실패를 "단색 폴백으로 진행 가능한" 조건으로 다뤘다(전체 파이프라인을 막지 않기 위함).
  실제 실행 전에는 반드시 사용자 확인을 받는다(2026-08-03, `wiki/decisions.md` 참고).

legacy 대응: legacy/pipeline_common.py
(_generate_image_to_path, generate_cover_image_raw, generate_scene_image_raw,
REEL_IMAGE_PROMPT_TEMPLATE, REEL_SCENE_SIZE_SEEDREAM/OPENAI)
legacy/Generate.py (IMAGE_PROMPT_TEMPLATE, SEEDREAM_MODEL — generate_cover_image은 구
CLI 경로라 함수 자체는 이관 대상이 아니고 상수만 가져옴)
"""

from __future__ import annotations

import base64
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ..core.clients import ARK_BASE_URL, get_ark_client, get_openai_client  # noqa: F401 (ARK_BASE_URL 참고용)
from ..core.paths import ASSETS_DIR, REEL_IMAGES_DIR
from . import pipeline

# Volcengine Ark(Doubao-Seedream) 모델 문자열. legacy/Generate.py에서 그대로 옮김.
SEEDREAM_MODEL = "seedream-5-0-260128"

# 표지는 세로형(2:3), 릴스 장면은 가로형(4:3에 가까운 프리셋)을 쓴다 — legacy 실측 확인값 그대로.
COVER_SIZE_SEEDREAM = "1664x2496"
COVER_SIZE_OPENAI = "1024x1536"
REEL_SCENE_SIZE_SEEDREAM = "2280x1710"
REEL_SCENE_SIZE_OPENAI = "1536x1024"


def _generate_image_to_path(
    prompt: str, out_path: Path, quality: str, provider: str, size_seedream: str, size_openai: str
) -> tuple[str | None, str | None]:
    """실제 이미지 생성 API를 호출해 out_path에 저장한다. (image_uri, error) 튜플을 돌려준다 —
    성공하면 (file:// URI, None), 실패하면 (None, 에러 메시지). API 키가 없으면 여기서 잡지
    않고 get_*_client()의 ValueError가 그대로 올라간다(설정 문제는 즉시 실패).
    legacy: pipeline_common._generate_image_to_path"""
    client = get_ark_client() if provider == "seedream" else get_openai_client()

    try:
        if provider == "seedream":
            resp = client.images.generate(
                model=SEEDREAM_MODEL,
                prompt=prompt,
                size=size_seedream,
                # watermark는 openai SDK의 images.generate()가 아는 파라미터가 아니라
                # (Ark 전용 필드) extra_body로 넘겨야 요청 바디에 실제로 포함된다.
                extra_body={"watermark": False},
            )
        else:
            resp = client.images.generate(model="gpt-image-2", prompt=prompt, size=size_openai, quality=quality)

        item = resp.data[0]
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if getattr(item, "url", None):
            urllib.request.urlretrieve(item.url, out_path)
        elif getattr(item, "b64_json", None):
            out_path.write_bytes(base64.b64decode(item.b64_json))
        else:
            return None, "이미지 응답 형식을 인식하지 못했습니다."

        return out_path.resolve().as_uri(), None
    except Exception as e:
        return None, f"이미지 생성 실패: {e}"


# ============================================================
# 표지 이미지 — legacy/Generate.py: IMAGE_PROMPT_TEMPLATE
# ============================================================
IMAGE_PROMPT_TEMPLATE = """한국 디지털 뉴스 매체의 세로형 썸네일에 사용할 사실적인 보도사진을 만들어주세요.

주제: {concept}

구도: 아래 주제에 가장 잘 어울리는 소재를 자유롭게 고릅니다 — 사람의 뒷모습·옆모습·실루엣, 손이나 도구의 클로즈업, 장소나 건물의 풍경, 화면·차트·서류 같은 사물, 여러 사람이 있는 현장 등. 매번 같은 인물 뒷모습 구도로 고정하지 말고 주제마다 다르게 선택합니다. 사람이 등장할 경우 얼굴이 정면으로 또렷하게 드러나지 않게 합니다. 화면 하단부는 나중에 자동으로 어둡게 처리되어 글자가 얹히므로, 특정 위치에 여백을 미리 비워둘 필요는 없습니다. 이미지 안에는 실제 글자나 로고를 넣지 마세요.

스타일: 한국에서 실제 기자가 촬영한 보도사진처럼 자연스럽고 신뢰감 있게 표현합니다. 흐린 날의 부드러운 자연광, 낮은 채도, 절제된 색감, 35mm 다큐멘터리 사진, 현실적인 인체와 건축물, 과장되지 않은 긴장감을 사용합니다.

제외: 영화 포스터, 스톡사진 포즈, 정면 얼굴, 과도한 보케, SF 인터페이스, 일러스트, 3D 렌더링, 글자, 워터마크를 제외합니다."""


def build_cover_image_prompt(concept: str, extra_direction: str = "") -> str:
    """legacy: Generate.py의 IMAGE_PROMPT_TEMPLATE.replace(...) + extra_direction 부착 로직"""
    prompt = IMAGE_PROMPT_TEMPLATE.replace("{concept}", concept)
    if extra_direction.strip():
        prompt += f"\n\n추가 지시: {extra_direction.strip()}"
    return prompt


@dataclass
class GenerateCoverImageRequest:
    content_id: str
    concept: str
    extra_direction: str = ""
    provider: str = "openai"
    quality: str = "high"


@dataclass
class GenerateCoverImageResult:
    content_id: str
    image_path: Path | None
    image_uri: str | None
    error: str | None = None


def generate_cover_image(request: GenerateCoverImageRequest) -> GenerateCoverImageResult:
    """content.json의 cover.image_concept로 표지 이미지를 생성한다. 성공하면
    services/pipeline.py 매니페스트에 cover_image_path를 기록한다.
    legacy: pipeline_common.generate_cover_image_raw"""
    prompt = build_cover_image_prompt(request.concept, request.extra_direction)
    out_path = ASSETS_DIR / f"cover-{request.content_id}.png"

    image_uri, error = _generate_image_to_path(
        prompt, out_path, request.quality, request.provider,
        size_seedream=COVER_SIZE_SEEDREAM, size_openai=COVER_SIZE_OPENAI,
    )
    if image_uri is None:
        return GenerateCoverImageResult(content_id=request.content_id, image_path=None, image_uri=None, error=error)

    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id=request.content_id, cover_image_path=str(out_path))
    )
    return GenerateCoverImageResult(content_id=request.content_id, image_path=out_path, image_uri=image_uri)


# ============================================================
# 릴스 장면 이미지 — legacy/pipeline_common.py: REEL_IMAGE_PROMPT_TEMPLATE
# ============================================================
REEL_IMAGE_PROMPT_TEMPLATE = """한국 뉴스 릴스(쇼츠) 영상의 배경 장면으로 쓸 사실적인 보도사진을 만들어주세요.

장면: {concept}

스타일: 한국에서 실제 기자가 촬영한 보도사진처럼 자연스럽고 신뢰감 있게 표현합니다. 흐린 날의 부드러운 자연광, 낮은 채도, 절제된 색감, 35mm 다큐멘터리 사진, 현실적인 인체와 건축물, 과장되지 않은 긴장감을 사용합니다. 화면 비율은 가로로 넓은 4:3 구도입니다.

제외: 영화 포스터, 스톡사진 포즈, SF 인터페이스, 일러스트, 3D 렌더링, 글자, 워터마크를 제외합니다."""


def build_scene_image_prompt(concept: str) -> str:
    """legacy: pipeline_common.REEL_IMAGE_PROMPT_TEMPLATE.format(concept=...)"""
    return REEL_IMAGE_PROMPT_TEMPLATE.format(concept=concept)


@dataclass
class GenerateSceneImageRequest:
    content_id: str
    scene_index: int
    concept: str
    provider: str = "openai"
    quality: str = "high"


@dataclass
class GenerateSceneImageResult:
    content_id: str
    scene_index: int
    image_path: Path | None
    image_uri: str | None
    error: str | None = None


def generate_scene_image(request: GenerateSceneImageRequest) -> GenerateSceneImageResult:
    """릴스 장면 이미지를 생성한다(4:3, 릴스 전용 프롬프트). 장면 하나를 여러 대사 줄이
    공유하므로 줄이 아니라 장면 인덱스 기준으로 저장한다. 성공하면 services/pipeline.py
    매니페스트에 reel_images_dir(장면 이미지들이 모이는 폴더)을 기록한다.
    legacy: pipeline_common.generate_scene_image_raw"""
    prompt = build_scene_image_prompt(request.concept)
    images_dir = REEL_IMAGES_DIR / request.content_id
    out_path = images_dir / f"scene_{request.scene_index:02d}.png"

    image_uri, error = _generate_image_to_path(
        prompt, out_path, request.quality, request.provider,
        size_seedream=REEL_SCENE_SIZE_SEEDREAM, size_openai=REEL_SCENE_SIZE_OPENAI,
    )
    if image_uri is None:
        return GenerateSceneImageResult(
            content_id=request.content_id, scene_index=request.scene_index,
            image_path=None, image_uri=None, error=error,
        )

    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id=request.content_id, reel_images_dir=str(images_dir))
    )
    return GenerateSceneImageResult(
        content_id=request.content_id, scene_index=request.scene_index, image_path=out_path, image_uri=image_uri
    )
