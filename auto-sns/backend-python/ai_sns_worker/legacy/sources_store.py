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

from pipeline_common import CAND_DIR, DATA, RSS_COLLECT_DIR, SOURCES_DIR

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


def _candidates_folder(group_path: Path) -> Path:
    return CAND_DIR / group_path.stem


def save_candidates(group_path: Path, candidates: list[dict]) -> Path:
    folder = _candidates_folder(group_path)
    folder.mkdir(parents=True, exist_ok=True)
    out_path = folder / f"{date.today().isoformat()}.json"
    out_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def list_candidate_files(group_path: Path) -> list[Path]:
    folder = _candidates_folder(group_path)
    if not folder.exists():
        return []
    return sorted(folder.glob("*.json"), reverse=True)


def load_candidates(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


SELECT_PERSONA_TEMPLATE = """(이 계정의 성격과 독자를 적어주세요 - 예: "너는 '자동화세상' 인스타그램 계정의 편집자다. 독자는 뉴스에 관심이 많은 사람이다.")"""


SELECT_CRITERIA_PROMPT = """아래는 사용자가 오늘의 카드뉴스 소재 후보로 직접 고른 뉴스 항목들(제목+요약)이다.

다음 기준으로 후보를 추려 카드뉴스 후보 카드로 정리하라:
- 같은 사건을 여러 항목이 다뤘으면 하나로 병합하고, 대표 출처는 가장 1차에 가까운 것(공식 발표 > 매체)으로 고른다.
- 내용이 사실상 겹치는 항목도 하나로 합친다(중복 제거).
- 독자의 흥미를 끄는 후킹 요소(의외성, 숫자 임팩트, 논쟁성, 실생활 영향 등)가 강한 순으로 우선한다.
- 최대 10개까지만 선별한다. 좋은 후보가 10개 미만이면 있는 만큼만 출력한다."""


# GPT가 반환해야 하는 JSON 필드 스키마 — 다운스트림 코드(save_candidates, 후보 선택 UI, 딥리서치의
# build_research_prompt 등)가 이 필드명을 그대로 읽으므로, 화면에서 사용자가 편집하거나
# select_prompt_state.json에 저장되지 않는 고정값으로 둔다. 필드를 추가/변경할 땐 여기만 고치면
# "선별 실행"을 한 번이라도 성공시켜 본 사용자에게도 즉시 반영된다(선별 기준과 뒤섞여 있으면 사용자가
# 저장해둔 예전 텍스트에 새 필드 지시가 반영되지 않는 문제가 있었다 — 2026-07-29).
SELECT_OUTPUT_SCHEMA = """각 후보에 대해 아래 필드를 채워라:
- id: "YYYYMMDD-NN" 형식 (오늘 날짜 + 순번)
- title: 한 줄 제목
- one_line: 무슨 소식인지 한 문장
- why_now: 왜 지금 다룰 가치가 있는지
- angle: 카드 각도 제안 (독자 특성에 맞는 관점)
- source: 대표 출처 URL (반드시 입력 항목에 있던 실제 링크)
- sources: 이 후보로 병합된 입력 항목들의 링크 배열 (source도 포함, 중복 제거, 최소 1개 —
  반드시 입력 항목에 있던 실제 링크만. 딥리서치 단계에서 이 링크들을 전부 원문으로 읽어 근거를
  보강하는 데 쓰이니, 병합했다면 하나만 남기지 말고 병합에 쓰인 링크를 모두 적어라.)
- visual: 시각화 난이도 한줄평 (예: "비교표로 5장 무리 없음")

입력에 없는 사실을 지어내지 않는다.

**순수 JSON 배열만 출력**한다. 설명·마크다운 없이.
"""


# 함수 기본값 등 "편집 없이 그대로 쓸 때"를 위한 결합 버전 — 화면(다이얼로그)에서는 페르소나/선별
# 기준만 편집하고, 출력 형식은 항상 SELECT_OUTPUT_SCHEMA를 그대로 뒤에 붙인다.
SELECT_PROMPT = SELECT_PERSONA_TEMPLATE + "\n\n" + SELECT_CRITERIA_PROMPT + "\n\n" + SELECT_OUTPUT_SCHEMA

SELECT_PROMPT_STATE_FILE = DATA / "select_prompt_state.json"

# 예전 버전(선별 기준과 출력 형식이 한 텍스트로 저장되던 시절)에 저장된 상태 파일을 정리하기 위한 앵커.
_OLD_SCHEMA_ANCHOR = "\n\n각 후보에 대해 아래 필드를 채워라:"


def load_select_prompt_state() -> dict:
    """
    GPT 선별 다이얼로그에서 마지막으로 실행에 성공했을 때의 "선별 기준"을 읽어온다.
    저장된 적이 없으면 기본 템플릿을 반환한다 — 세션이 끊기거나 앱을 재시작해도 마지막에 쓴 기준을
    그대로 이어서 쓸 수 있게 하기 위함이다. 출력 형식(SELECT_OUTPUT_SCHEMA)은 여기 포함되지 않는다 —
    항상 코드의 최신 값이 별도로 적용된다.
    """
    if SELECT_PROMPT_STATE_FILE.exists():
        data = json.loads(SELECT_PROMPT_STATE_FILE.read_text(encoding="utf-8"))
        rules = data.get("rules", SELECT_CRITERIA_PROMPT)
        if _OLD_SCHEMA_ANCHOR in rules:
            rules = rules.split(_OLD_SCHEMA_ANCHOR)[0].rstrip()
        return {
            "persona": data.get("persona", SELECT_PERSONA_TEMPLATE),
            "rules": rules,
        }
    return {"persona": SELECT_PERSONA_TEMPLATE, "rules": SELECT_CRITERIA_PROMPT}


def save_select_prompt_state(persona: str, rules: str) -> None:
    SELECT_PROMPT_STATE_FILE.write_text(
        json.dumps({"persona": persona, "rules": rules}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def select_candidates_from_items(client, items: list[dict], system_prompt: str = SELECT_PROMPT) -> list[dict]:
    """
    사용자가 화면에서 체크한 RSS 항목만 GPT에 넘겨 카드뉴스 후보 카드로 정리시킨다.
    (과거 Research.py의 select_candidates()와 달리 대상 항목을 GPT가 아니라 사용자가 이미 골랐으므로
    history.json 대조·"최대 5개로 추리기" 같은 필터링은 하지 않는다.)

    system_prompt: 화면에서 편집됐을 수 있는 시스템 프롬프트. 기본값은 SELECT_PROMPT.
    항목 목록(user_content)은 항상 여기서 그대로 조립한다 — 편집 대상이 아니다.
    """
    today = datetime.now().strftime("%Y%m%d")
    lines = [f"오늘 날짜: {today}\n\n항목 목록:"]
    for i, it in enumerate(items, 1):
        lines.append(
            f"\n[{i}] ({it.get('feed', '')}, tier={it.get('tier', '')})\n"
            f"제목: {it.get('title', '')}\n요약: {it.get('summary', '')}\n링크: {it.get('link', '')}"
        )
    user_content = "\n".join(lines)

    resp = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)


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
