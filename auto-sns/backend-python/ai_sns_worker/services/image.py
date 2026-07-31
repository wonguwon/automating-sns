"""표지/장면 이미지 생성 (Doubao-Seedream 기본, GPT Image 2 선택).

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO를 받고 result DTO를 반환한다 (아직 DTO 타입 미정).

legacy 대응: legacy/pipeline_common.py
(_generate_image_to_path, generate_cover_image_raw, generate_scene_image_raw)
legacy/Generate.py (generate_cover_image — 구 CLI 경로)
"""

from __future__ import annotations


def generate_cover_image(request):
    """TODO: content.json의 cover.image_concept로 표지 이미지 생성. legacy: pipeline_common.generate_cover_image_raw"""
    raise NotImplementedError


def generate_scene_image(request):
    """TODO: 릴스 장면 이미지 생성(4:3, 릴스 전용 프롬프트). legacy: pipeline_common.generate_scene_image_raw"""
    raise NotImplementedError
