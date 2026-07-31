"""RSS 소스 그룹 관리 및 수집.

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO(dataclass)를 받고 result DTO(dataclass)를 반환한다.
- 실패는 st.error 대신 예외(ValueError/FileNotFoundError/IndexError)로 알린다 —
  worker.py가 잡아서 job 실패로 기록하는 걸 전제로 한다.

legacy 대응: legacy/sources_store.py
(list_groups, load_group, save_group, create_group, add_feed, remove_feed,
set_feed_enabled, update_feed, health_check_group, collect_group_items,
save_rss_collection, list_rss_collections, load_rss_collection)

이번 단계에서 제외한 것:
- GPT 피드 후보 제안(legacy: generate_feeds_from_prompt) — OpenAI 클라이언트/API 키 로딩
  정책(core/config.py)이 아직 결정되지 않아 create_feed_group은 "빈 그룹 생성"까지만
  담당한다. 정책이 정해지면 이 파일에 추가한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import feedparser

from ..core.paths import RSS_COLLECT_DIR, SOURCES_DIR

_HEALTHCHECK_AGENT = "Mozilla/5.0 (auto-sns rss healthcheck)"
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


# ============================================================
# DTO
# ============================================================
@dataclass
class FeedEntry:
    name: str
    url: str
    tier: str
    enabled: bool = True
    note: str = ""
    verified: dict | None = None


@dataclass
class FeedGroupSummary:
    id: str
    name: str
    feed_count: int
    last_health_check: str | None


@dataclass
class CreateFeedGroupRequest:
    name: str


@dataclass
class CreateFeedGroupResult:
    id: str
    name: str


@dataclass
class AddFeedRequest:
    group_id: str
    name: str
    url: str
    tier: str
    enabled: bool = True
    note: str = ""


@dataclass
class AddFeedResult:
    group_id: str
    feed_index: int
    feed: FeedEntry


@dataclass
class UpdateFeedRequest:
    """None인 필드는 기존 값을 유지한다 — legacy의 update_feed(전체 덮어쓰기)와
    set_feed_enabled(토글만)를 부분 수정 하나로 통합했다."""

    group_id: str
    feed_index: int
    name: str | None = None
    url: str | None = None
    tier: str | None = None
    enabled: bool | None = None
    note: str | None = None


@dataclass
class UpdateFeedResult:
    group_id: str
    feed_index: int
    feed: FeedEntry


@dataclass
class RemoveFeedRequest:
    group_id: str
    feed_index: int


@dataclass
class RemoveFeedResult:
    group_id: str
    removed: bool


@dataclass
class HealthCheckGroupRequest:
    group_id: str


@dataclass
class HealthCheckGroupResult:
    group_id: str
    checked_at: str
    feeds: list[FeedEntry]


@dataclass
class CollectFeedItemsRequest:
    group_id: str
    hours: int = 24


@dataclass
class CollectFeedItemsResult:
    group_id: str
    saved_path: Path
    item_count: int
    items: list[dict] = field(default_factory=list)


# ============================================================
# 내부 헬퍼 — SOURCES_DIR/<group_id>.json 파일 하나가 그룹 하나다.
# ============================================================
def _group_path(group_id: str) -> Path:
    return SOURCES_DIR / f"{group_id}.json"


def _slugify(name: str) -> str:
    slug = _INVALID_FILENAME_CHARS.sub("_", name.strip())
    slug = re.sub(r"\s+", "-", slug)
    return slug or "그룹"


def _load_group_data(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("name", path.stem)
    data.setdefault("feeds", [])
    data.setdefault("_last_health_check", None)
    return data


def _save_group_data(path: Path, data: dict) -> None:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _require_group(group_id: str) -> tuple[Path, dict]:
    path = _group_path(group_id)
    if not path.exists():
        raise FileNotFoundError(f"소스 그룹을 찾을 수 없습니다: {group_id}")
    return path, _load_group_data(path)


def _feed_entry(raw: dict) -> FeedEntry:
    return FeedEntry(
        name=raw.get("name", ""),
        url=raw.get("url", ""),
        tier=raw.get("tier", ""),
        enabled=raw.get("enabled", True),
        note=raw.get("note", ""),
        verified=raw.get("verified"),
    )


# ============================================================
# 공개 함수
# ============================================================
def list_feed_groups() -> list[FeedGroupSummary]:
    """등록된 소스 그룹 목록 조회. legacy: sources_store.list_groups"""
    if not SOURCES_DIR.exists():
        return []
    summaries = []
    for path in sorted(SOURCES_DIR.glob("*.json")):
        data = _load_group_data(path)
        summaries.append(
            FeedGroupSummary(
                id=path.stem,
                name=data["name"],
                feed_count=len(data["feeds"]),
                last_health_check=data.get("_last_health_check"),
            )
        )
    return summaries


def create_feed_group(request: CreateFeedGroupRequest) -> CreateFeedGroupResult:
    """빈 소스 그룹을 생성한다(GPT 피드 후보 제안은 이번 단계 범위 밖 — 모듈 docstring 참고).
    legacy: sources_store.create_group"""
    display_name = request.name.strip()
    if not display_name:
        raise ValueError("그룹 이름이 비어 있습니다.")

    slug = _slugify(display_name)
    path = SOURCES_DIR / f"{slug}.json"
    n = 2
    while path.exists():
        path = SOURCES_DIR / f"{slug}-{n}.json"
        n += 1

    _save_group_data(path, {"name": display_name, "_last_health_check": None, "feeds": []})
    return CreateFeedGroupResult(id=path.stem, name=display_name)


def add_feed(request: AddFeedRequest) -> AddFeedResult:
    """그룹에 피드를 추가한다. legacy: sources_store.add_feed"""
    path, data = _require_group(request.group_id)
    entry = {
        "name": request.name.strip(),
        "url": request.url.strip(),
        "tier": request.tier.strip(),
        "enabled": request.enabled,
        "note": request.note.strip(),
        "verified": None,
    }
    data["feeds"].append(entry)
    _save_group_data(path, data)
    return AddFeedResult(group_id=request.group_id, feed_index=len(data["feeds"]) - 1, feed=_feed_entry(entry))


def update_feed(request: UpdateFeedRequest) -> UpdateFeedResult:
    """피드 정보를 부분 수정한다. legacy: sources_store.update_feed, set_feed_enabled"""
    path, data = _require_group(request.group_id)
    feeds = data["feeds"]
    if not (0 <= request.feed_index < len(feeds)):
        raise IndexError(f"피드 인덱스가 범위를 벗어났습니다: {request.feed_index}")

    feed = feeds[request.feed_index]
    if request.name is not None:
        feed["name"] = request.name.strip()
    if request.url is not None:
        feed["url"] = request.url.strip()
    if request.tier is not None:
        feed["tier"] = request.tier.strip()
    if request.enabled is not None:
        feed["enabled"] = request.enabled
    if request.note is not None:
        feed["note"] = request.note.strip()

    _save_group_data(path, data)
    return UpdateFeedResult(group_id=request.group_id, feed_index=request.feed_index, feed=_feed_entry(feed))


def remove_feed(request: RemoveFeedRequest) -> RemoveFeedResult:
    """피드를 삭제한다. legacy: sources_store.remove_feed"""
    path, data = _require_group(request.group_id)
    feeds = data["feeds"]
    if not (0 <= request.feed_index < len(feeds)):
        raise IndexError(f"피드 인덱스가 범위를 벗어났습니다: {request.feed_index}")

    feeds.pop(request.feed_index)
    _save_group_data(path, data)
    return RemoveFeedResult(group_id=request.group_id, removed=True)


def _check_feed(url: str) -> dict:
    today = date.today().isoformat()
    try:
        parsed = feedparser.parse(url, agent=_HEALTHCHECK_AGENT)
    except Exception as e:
        return {"status": "FAIL", "checked": today, "error": str(e)[:200]}

    http_status = getattr(parsed, "status", None)
    if http_status is not None and http_status >= 400:
        return {"status": "FAIL", "checked": today, "error": f"HTTP {http_status}"}

    if not parsed.entries:
        error = str(parsed.get("bozo_exception", "")) if parsed.get("bozo") else "항목 없음"
        return {"status": "FAIL", "checked": today, "error": error[:200]}

    times = [t for t in (e.get("published_parsed") or e.get("updated_parsed") for e in parsed.entries) if t]
    latest = datetime(*max(times)[:6]).date().isoformat() if times else None
    return {"status": "OK", "latest": latest, "checked": today}


def health_check_group(request: HealthCheckGroupRequest) -> HealthCheckGroupResult:
    """그룹 내 모든 피드 URL을 헬스체크한다(실제 네트워크 호출). legacy: sources_store.health_check_group"""
    path, data = _require_group(request.group_id)
    for feed in data["feeds"]:
        feed["verified"] = _check_feed(feed["url"])
    checked_at = datetime.now(timezone.utc).isoformat()
    data["_last_health_check"] = checked_at
    _save_group_data(path, data)
    return HealthCheckGroupResult(
        group_id=request.group_id, checked_at=checked_at, feeds=[_feed_entry(f) for f in data["feeds"]]
    )


def collect_feed_items(request: CollectFeedItemsRequest) -> CollectFeedItemsResult:
    """enabled 피드에서 최근 hours시간 항목을 수집해 저장한다(실제 네트워크 호출).
    legacy: sources_store.collect_group_items, save_rss_collection"""
    _, data = _require_group(request.group_id)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=request.hours)
    items = []
    for feed in data["feeds"]:
        if not feed.get("enabled", False):
            continue
        parsed = feedparser.parse(feed["url"], agent=_HEALTHCHECK_AGENT)
        for e in parsed.entries:
            t = e.get("published_parsed") or e.get("updated_parsed")
            when = datetime(*t[:6], tzinfo=timezone.utc) if t else None
            if when and when < cutoff:
                continue
            summary = (e.get("summary") or "").strip()
            summary = " ".join(summary.replace("<", " <").split())
            if len(summary) > 400:
                summary = summary[:400] + "…"
            items.append({
                "feed": feed["name"],
                "tier": feed.get("tier", ""),
                "title": e.get("title", "").strip(),
                "summary": summary,
                "link": e.get("link", ""),
                "when": when.isoformat() if when else None,
            })

    folder = RSS_COLLECT_DIR / request.group_id
    folder.mkdir(parents=True, exist_ok=True)
    out_path = folder / f"{date.today().isoformat()}.json"
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    return CollectFeedItemsResult(group_id=request.group_id, saved_path=out_path, item_count=len(items), items=items)
