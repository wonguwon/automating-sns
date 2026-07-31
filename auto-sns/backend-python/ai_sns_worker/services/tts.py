"""타입캐스트 TTS 음성 목록 조회 및 합성.

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO를 받고 result DTO를 반환한다 (아직 DTO 타입 미정).

legacy 대응: legacy/pipeline_common.py
(list_typecast_voices, synthesize_reel_line, REEL_DEFAULT_VOICE_ID, REEL_EMOTION_PRESETS)
"""

from __future__ import annotations


def list_voices():
    """TODO: 사용 가능한 타입캐스트 음성 목록 조회. legacy: pipeline_common.list_typecast_voices"""
    raise NotImplementedError


def synthesize_line(request):
    """TODO: 대본 한 줄을 음성으로 합성(속도/감정 옵션). legacy: pipeline_common.synthesize_reel_line"""
    raise NotImplementedError
