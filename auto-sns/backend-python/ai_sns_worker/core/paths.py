"""파일 저장 경로 정책.

Spring Boot/MySQL 스키마가 정해지기 전까지는 legacy와 같은 파일 기반 저장을 유지하되,
저장 루트를 프로젝트의 storage/ 아래로 통일한다(2026-07-31, 2단계 RSS 기능 이관 시 결정).
storage/assets, storage/outputs, storage/templates와 같은 층위에 하위 폴더를 추가하는
방식이다 — 다른 services 파일이 경로가 필요해지면 이 모듈에 계속 추가한다.

TODO: legacy/pipeline_common.py의 나머지 경로 상수(CAND_DIR, RESEARCH_DIR, CONTENT_DIR,
REEL_* 등)는 해당 기능을 이관할 때 이 모듈에 추가한다.
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
