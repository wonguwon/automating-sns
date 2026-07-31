"""카드뉴스 PNG 렌더 및 릴스 mp4 조립.

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO를 받고 result DTO를 반환한다 (아직 DTO 타입 미정).

legacy 대응:
- legacy/Render.py (render — playwright로 template.html + content.json → PNG)
- legacy/Render_reel_narrated.py (build_reel — ffmpeg로 대본/장면/오디오 → mp4)
"""

from __future__ import annotations


def render_cardnews(request):
    """TODO: content.json + 템플릿으로 카드뉴스 PNG 세트 렌더. legacy: Render.render"""
    raise NotImplementedError


def render_reel(request):
    """TODO: 대본+장면 이미지+TTS 오디오로 릴스 mp4 조립. legacy: Render_reel_narrated.build_reel"""
    raise NotImplementedError
