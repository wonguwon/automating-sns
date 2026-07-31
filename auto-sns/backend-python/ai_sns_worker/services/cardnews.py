"""카드뉴스 content.json 생성 + 인스타 캡션 생성.

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO를 받고 result DTO를 반환한다 (아직 DTO 타입 미정).

legacy 대응:
- legacy/pipeline_common.py (build_content_json_prompt, run_content_json_prompt,
  run_insta_caption)
- legacy/Generate.py (generate_content_json — 구 CLI 경로)

미해결: 템플릿 세트(template.html/prompt.md/예시) 관리 함수
(legacy/pipeline_common.py의 list_templates/create_template/update_template_files/
add_template_examples/delete_template*)는 아직 어느 services 파일에도 매핑하지
않았다 — 필요 시 templates.py를 별도로 만들지 결정한다.
"""

from __future__ import annotations


def generate_content_json(request):
    """TODO: 조사 노트+템플릿+계정정보로 카드뉴스 JSON 생성. legacy: pipeline_common.run_content_json_prompt"""
    raise NotImplementedError


def get_content_json(request):
    """TODO: 저장된 content.json 조회. legacy: 파일 시스템 data/content/*.json 직접 읽기 대응"""
    raise NotImplementedError


def generate_insta_caption(request):
    """TODO: 조사 노트로부터 인스타 업로드용 캡션 생성. legacy: pipeline_common.run_insta_caption"""
    raise NotImplementedError
