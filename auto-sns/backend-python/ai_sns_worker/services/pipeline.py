"""파이프라인 단계 간 연결 매니페스트(content_id별 진행 상태) 관리.

각 단계(후보 선택 → 딥리서치 → 카드뉴스 생성 → 렌더 → 릴스 제작)는 서로 다른 job 실행이라
호출부 상태만으로는 이어지지 않는다. content_id 하나당 매니페스트 파일 하나에 그때까지의
각 단계 산출물 "경로"만 얇게 기록해 다음 단계가 이어받을 수 있게 한다.

content(카드뉴스 JSON) 본문 자체는 이 매니페스트에 복사하지 않는다 — services/cardnews.py가
다루는 content.json이 계속 원본(canonical)이고, 여기서는 그 경로(content_path)만 가리킨다.

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO(dataclass)를 받고 result DTO(dataclass)를 반환한다.
- 실패는 예외로 알린다.

legacy 대응: legacy/pipeline_state.py (load_state, save_state)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from ..core.paths import PIPELINE_DIR

FIELDS = (
    "candidate",
    # research_pairs는 더 이상 쓰지 않는다(legacy 결정, 노트 단일 산출물로 전환) — 과거
    # 매니페스트와의 호환을 위해 필드 이름만 유지한다.
    "research_pairs",
    "research_note_path",
    "content_path",
    "cover_image_path",
    "render_out_dir",
    "reel_script_path",
    "reel_images_dir",
    "reel_audio_dir",
    "reel_path",
)


# ============================================================
# DTO
# ============================================================
@dataclass
class PipelineState:
    content_id: str
    candidate: dict | None = None
    research_pairs: object | None = None
    research_note_path: str | None = None
    content_path: str | None = None
    cover_image_path: str | None = None
    render_out_dir: str | None = None
    reel_script_path: str | None = None
    reel_images_dir: str | None = None
    reel_audio_dir: str | None = None
    reel_path: str | None = None
    updated_at: str | None = None


@dataclass
class LoadPipelineStateRequest:
    content_id: str


@dataclass
class SavePipelineStateRequest:
    """None인 필드는 기존 값을 유지한다 — legacy save_state(**updates)의 부분 갱신 방식과
    같다(services/rss.py의 UpdateFeedRequest와 동일한 패턴)."""

    content_id: str
    candidate: dict | None = None
    research_pairs: object | None = None
    research_note_path: str | None = None
    content_path: str | None = None
    cover_image_path: str | None = None
    render_out_dir: str | None = None
    reel_script_path: str | None = None
    reel_images_dir: str | None = None
    reel_audio_dir: str | None = None
    reel_path: str | None = None


# ============================================================
# 내부 헬퍼 — PIPELINE_DIR/<content_id>.json 파일 하나가 매니페스트 하나다.
# ============================================================
def _path(content_id: str):
    return PIPELINE_DIR / f"{content_id}.json"


# ============================================================
# 공개 함수
# ============================================================
def load_pipeline_state(request: LoadPipelineStateRequest) -> PipelineState:
    """content_id에 해당하는 매니페스트를 읽는다. 없으면 모든 필드가 None인 빈 상태를 준다.
    legacy: pipeline_state.load_state"""
    data = {field: None for field in FIELDS}
    path = _path(request.content_id)
    if path.exists():
        data.update(json.loads(path.read_text(encoding="utf-8")))
    updated_at = data.pop("updated_at", None)
    return PipelineState(content_id=request.content_id, updated_at=updated_at, **data)


def save_pipeline_state(request: SavePipelineStateRequest) -> PipelineState:
    """request에서 None이 아닌 필드만 기존 매니페스트에 덮어써 저장한다.
    legacy: pipeline_state.save_state"""
    current = load_pipeline_state(LoadPipelineStateRequest(content_id=request.content_id))
    merged = asdict(current)
    merged.pop("content_id", None)
    merged.pop("updated_at", None)
    for name in FIELDS:
        value = getattr(request, name)
        if value is not None:
            merged[name] = value
    merged["updated_at"] = datetime.now(timezone.utc).isoformat()

    PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
    _path(request.content_id).write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    return PipelineState(content_id=request.content_id, **merged)
