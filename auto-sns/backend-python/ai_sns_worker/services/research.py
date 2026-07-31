"""GPT 후보 선별 + 딥리서치(원문 근거 보강) 실행.

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO를 받고 result DTO를 반환한다 (아직 DTO 타입 미정).

legacy 대응:
- legacy/sources_store.py (select_candidates_from_items, save_candidates,
  list_candidate_files, load_candidates, load_select_prompt_state,
  save_select_prompt_state)
- legacy/pipeline_common.py (fetch_article_text, build_research_prompt,
  run_research_prompt, RESEARCH_NOTE_PROMPT)
- legacy/Research.py (구 CLI 경로 — 참고용)
"""

from __future__ import annotations


def select_candidates(request):
    """TODO: RSS 원본 중 선택 항목을 GPT로 카드뉴스 후보로 정리. legacy: sources_store.select_candidates_from_items"""
    raise NotImplementedError


def run_deep_research(request):
    """TODO: 후보의 출처 링크를 원문으로 읽어 조사 노트 생성. legacy: pipeline_common.build_research_prompt/run_research_prompt"""
    raise NotImplementedError


def get_research_note(request):
    """TODO: 저장된 조사 노트 조회. legacy: 파일 시스템 data/research/*.md 직접 읽기 대응"""
    raise NotImplementedError
