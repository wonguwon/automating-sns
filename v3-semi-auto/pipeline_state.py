#!/usr/bin/env python3
"""
칼퇴각 파이프라인 — 단계 간 연결 문서(매니페스트)
------------------------------------------------
각 단계 페이지는 서로 다른 스크립트 실행이라 st.session_state만으로는 이어지지 않는다.
content_id 하나당 data/pipeline/<content_id>.json 파일 하나에 "지금까지 저장할 곳이
없던 것"(선택된 후보)과 각 단계 산출물의 경로만 얇게 기록해 다음 단계가
디스크에서 그대로 이어받을 수 있게 한다.

content(=카드뉴스 JSON) 본문 자체는 이 매니페스트에 복사하지 않는다 — data/content/<id>.json이
계속 원본(canonical)이고, 여기서는 그 경로(content_path)만 가리킨다. 두 곳에 같은 내용을
따로 들고 있으면 어느 쪽이 최신인지 어긋나는 문제가 생기기 때문이다.
------------------------------------------------
"""
import json
from datetime import datetime, timezone

from pipeline_common import PIPELINE_DIR

FIELDS = (
    "candidate",
    # research_pairs는 더 이상 쓰지 않는다(2026-07-29, 노트 단일 산출물로 전환) —
    # 과거 매니페스트와의 호환을 위해 필드 이름만 유지한다.
    "research_pairs",
    "research_note_path",
    "content_path",
    "cover_image_path",
    "render_out_dir",
    "reel_path",
)


def _path(content_id: str):
    return PIPELINE_DIR / f"{content_id}.json"


def load_state(content_id: str) -> dict:
    """content_id에 해당하는 매니페스트를 읽는다. 없으면 모든 필드가 None인 빈 상태를 준다."""
    state = {field: None for field in FIELDS}
    p = _path(content_id)
    if p.exists():
        state.update(json.loads(p.read_text(encoding="utf-8")))
    return state


def save_state(content_id: str, **updates) -> dict:
    """
    기존 매니페스트를 읽어 updates에 들어있는 필드만 덮어쓰고 다시 저장한다.
    updates에 없는 필드는 기존 값을 그대로 유지한다.
    """
    unknown = set(updates) - set(FIELDS)
    if unknown:
        raise ValueError(f"알 수 없는 매니페스트 필드: {unknown}")

    state = load_state(content_id)
    state.update(updates)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()

    PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
    _path(content_id).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state
