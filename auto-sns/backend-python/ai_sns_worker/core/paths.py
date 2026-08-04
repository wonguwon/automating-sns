"""파일 저장 경로 정책.

Spring Boot/MySQL 스키마가 정해지기 전까지는 legacy와 같은 파일 기반 저장을 유지하되,
저장 루트를 프로젝트의 storage/ 아래로 통일한다(2026-07-31, 2단계 RSS 기능 이관 시 결정).
storage/ 아래에 기능별 하위 폴더를 평평하게(flat) 추가하는 방식이다 — 다른 services 파일이
경로가 필요해지면 이 모듈에 계속 추가한다.

TODO: 이 파일 기반 방식을 MySQL 테이블+객체 스토리지 경로 규칙으로 재설계할지는 3단계
(Spring Boot) 스키마 설계 시점에 다시 판단한다.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STORAGE_ROOT = PROJECT_ROOT / "storage"

# RSS 소스 그룹 관리(services/rss.py) — sources/<group_id>.json, rss_collect/<group_id>/<날짜>.json
SOURCES_DIR = STORAGE_ROOT / "sources"
RSS_COLLECT_DIR = STORAGE_ROOT / "rss_collect"

# 파이프라인 단계 간 연결 매니페스트(services/pipeline.py) — pipeline/<content_id>.json
PIPELINE_DIR = STORAGE_ROOT / "pipeline"

# 카드뉴스 템플릿 세트 관리(services/templates.py) — templates/<템플릿명>/{template.html,prompt.md,예시/}
TEMPLATES_DIR = STORAGE_ROOT / "templates"

# GPT 후보 선별·딥리서치(services/research.py) — candidates/<group_id>/<날짜>.json, research/<content_id>.md
CAND_DIR = STORAGE_ROOT / "candidates"
RESEARCH_DIR = STORAGE_ROOT / "research"

# 카드뉴스 content.json(services/cardnews.py) — content/<content_id>.json
CONTENT_DIR = STORAGE_ROOT / "content"

# 표지 이미지(services/image.py) — assets/cover-<content_id>.png
ASSETS_DIR = STORAGE_ROOT / "assets"

# 릴스 제작(services/reel.py, image.py, tts.py) — 대본/장면 이미지/TTS 오디오 경로
REEL_SCRIPT_DIR = STORAGE_ROOT / "reel_script"
REEL_IMAGES_DIR = STORAGE_ROOT / "reel_images"
REEL_AUDIO_DIR = STORAGE_ROOT / "reel_audio"

# 최종 렌더 산출물(services/render.py) — outputs/cardnews/<content_id>/, outputs/reel/<content_id>.mp4
OUTPUTS_DIR = STORAGE_ROOT / "outputs"
CARDNEWS_OUTPUT_DIR = OUTPUTS_DIR / "cardnews"
REEL_OUTPUT_DIR = OUTPUTS_DIR / "reel"
