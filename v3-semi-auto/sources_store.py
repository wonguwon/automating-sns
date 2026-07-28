#!/usr/bin/env python3
"""
소스 그룹 저장소
------------------------------------------------
sources/*.json 하나가 그룹 하나다. 각 그룹 파일은:
{
  "name": "표시용 이름",
  "_last_health_check": "2026-07-28T.../null",
  "feeds": [
    {"name": "...", "url": "...", "tier": "...", "enabled": true, "note": "...", "verified": {...}|null}
  ]
}

루트의 기존 sources.json은 이 모듈이 건드리지 않는다 — Research.py가 지금도 그 파일을 그대로 읽는다.
그룹과 실제 RSS 수집을 연결하는 건 다음 작업 범위.
------------------------------------------------
"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import feedparser

from pipeline_common import RSS_COLLECT_DIR, SOURCES_DIR

HEALTHCHECK_AGENT = "Mozilla/5.0 (kaltoegak sources healthcheck)"


def list_groups() -> list[Path]:
    return sorted(SOURCES_DIR.glob("*.json"))


def load_group(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("name", path.stem)
    data.setdefault("feeds", [])
    return data


def save_group(path: Path, data: dict) -> None:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def group_label(path: Path) -> str:
    return load_group(path).get("name", path.stem)


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def _slugify(name: str) -> str:
    slug = _INVALID_FILENAME_CHARS.sub("_", name.strip())
    slug = re.sub(r"\s+", "-", slug)
    return slug or "그룹"


def create_group(display_name: str) -> Path:
    slug = _slugify(display_name)
    path = SOURCES_DIR / f"{slug}.json"
    n = 2
    while path.exists():
        path = SOURCES_DIR / f"{slug}-{n}.json"
        n += 1
    save_group(path, {"name": display_name.strip() or slug, "_last_health_check": None, "feeds": []})
    return path


def add_feed(path: Path, name: str, url: str, tier: str, enabled: bool = True, note: str = "") -> None:
    data = load_group(path)
    data["feeds"].append({
        "name": name.strip(),
        "url": url.strip(),
        "tier": tier.strip(),
        "enabled": enabled,
        "note": note.strip(),
        "verified": None,
    })
    save_group(path, data)


def remove_feed(path: Path, index: int) -> None:
    data = load_group(path)
    if 0 <= index < len(data["feeds"]):
        data["feeds"].pop(index)
        save_group(path, data)


def set_feed_enabled(path: Path, index: int, enabled: bool) -> None:
    data = load_group(path)
    if 0 <= index < len(data["feeds"]):
        data["feeds"][index]["enabled"] = enabled
        save_group(path, data)


def update_feed(path: Path, index: int, name: str, url: str, tier: str, enabled: bool, note: str = "") -> None:
    data = load_group(path)
    if 0 <= index < len(data["feeds"]):
        feed = data["feeds"][index]
        feed["name"] = name.strip()
        feed["url"] = url.strip()
        feed["tier"] = tier.strip()
        feed["enabled"] = enabled
        feed["note"] = note.strip()
        save_group(path, data)


def _check_feed(url: str) -> dict:
    today = date.today().isoformat()
    try:
        parsed = feedparser.parse(url, agent=HEALTHCHECK_AGENT)
    except Exception as e:
        return {"status": "FAIL", "checked": today, "error": str(e)[:200]}

    http_status = getattr(parsed, "status", None)
    if http_status is not None and http_status >= 400:
        return {"status": "FAIL", "checked": today, "error": f"HTTP {http_status}"}

    if not parsed.entries:
        error = str(parsed.get("bozo_exception", "")) if parsed.get("bozo") else "항목 없음"
        return {"status": "FAIL", "checked": today, "error": error[:200]}

    latest = None
    times = [e.get("published_parsed") or e.get("updated_parsed") for e in parsed.entries]
    times = [t for t in times if t]
    if times:
        latest = datetime(*max(times)[:6]).date().isoformat()

    return {"status": "OK", "latest": latest, "checked": today}


def health_check_group(path: Path) -> dict:
    data = load_group(path)
    for feed in data["feeds"]:
        feed["verified"] = _check_feed(feed["url"])
    data["_last_health_check"] = datetime.now(timezone.utc).isoformat()
    save_group(path, data)
    return data


def collect_group_items(path: Path, hours: int = 24) -> list[dict]:
    """
    로드된 그룹의 enabled=true인 피드에서 최근 hours시간 항목을 그대로 모아온다.
    GPT 선별은 하지 않는다 — 그건 딥리서치 단계에서 별도로 한다. 여기서는 원본 그대로 반환.
    """
    data = load_group(path)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []
    for feed in data["feeds"]:
        if not feed.get("enabled", False):
            continue
        parsed = feedparser.parse(feed["url"], agent=HEALTHCHECK_AGENT)
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
    return items


def _rss_collect_folder(group_path: Path) -> Path:
    return RSS_COLLECT_DIR / group_path.stem


def save_rss_collection(group_path: Path, items: list[dict]) -> Path:
    folder = _rss_collect_folder(group_path)
    folder.mkdir(parents=True, exist_ok=True)
    out_path = folder / f"{date.today().isoformat()}.json"
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def list_rss_collections(group_path: Path) -> list[Path]:
    folder = _rss_collect_folder(group_path)
    if not folder.exists():
        return []
    return sorted(folder.glob("*.json"), reverse=True)


def load_rss_collection(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


DEFAULT_FEED_PROMPT = """아래 설명에 맞는 RSS/Atom 피드 후보를 조사해 JSON 배열로 제안하라.

주제/범위: (여기에 원하는 소스 그룹의 성격을 적어주세요 — 예: "국내 스타트업 뉴스", "생성형 이미지 AI 전문 매체")

각 항목은 다음 필드를 가진 객체다:
- name: 매체/채널 이름
- url: 실제로 존재하는 RSS/Atom 피드 URL (확신이 없는 URL은 절대 지어내지 말고 통째로 제외할 것)
- tier: 1(공식 발표), newsletter(뉴스레터), kr(국내 매체), yt(유튜브) 중 하나 — 해당 없으면 자유 텍스트
- note: 이 소스를 넣는 이유 한 줄

**순수 JSON 배열만 출력**한다. 설명·마크다운 없이. 확신할 수 있는 피드만 5~10개 제안한다.
좋은 후보가 하나도 없으면 빈 배열 []을 출력한다.
"""


def generate_feeds_from_prompt(client, prompt: str) -> list[dict]:
    """
    GPT에게 프롬프트를 그대로 넘겨 피드 후보 JSON 배열을 받는다.
    URL은 GPT가 지어냈을 수 있으므로, 호출부가 이 결과에 이어서 health_check_group을
    돌려 실제로 살아있는지 반드시 확인해야 한다 — 여기서는 형식만 정리해 돌려준다.
    """
    resp = client.chat.completions.create(
        model="gpt-5.5",
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.choices[0].message.content.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    parsed = json.loads(raw)

    feeds = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        if not (name and url):
            continue
        feeds.append({
            "name": name,
            "url": url,
            "tier": str(item.get("tier", "")).strip(),
            "enabled": True,
            "note": str(item.get("note", "")).strip(),
            "verified": None,
        })
    return feeds
