"""릴스 대본 생성 및 장면 계획.

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO를 받고 result DTO를 반환한다 (아직 DTO 타입 미정).

legacy 대응: legacy/pipeline_common.py
(build_reel_script_prompt, run_reel_script_prompt, REEL_SCRIPT_SYSTEM_PROMPT)
"""

from __future__ import annotations


def generate_reel_script(request):
    """TODO: 조사 노트+방향성 입력으로 나레이션 대본(장면 지정 포함) 생성. legacy: pipeline_common.run_reel_script_prompt"""
    raise NotImplementedError
