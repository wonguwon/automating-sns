#!/usr/bin/env python3
"""
칼퇴각 후보 수집기 (플로우1)
------------------------------------------------
sources.json의 활성 피드에서 최근 24시간 항목을 모아
  → history.json과 대조해 이미 다룬 소재 제외
  → GPT-5.5로 중복 사건 병합 + '직장인 각도'가 나오는 후보 5개 선별
  → data/candidates/YYYY-MM-DD.json 저장

매일 아침 cron으로 실행하는 것이 최종 목표. 지금은 손으로 돌려 품질 확인.

사전 준비: pip3 install feedparser openai python-dotenv
          이 폴더(app2)의 .env 파일에 OPENAI_API_KEY=sk-... 작성 (없으면 시스템 환경변수로 폴백)
사용법:
    python3 research.py
    python3 research.py --hours 48        (창 넓히기, 소재 적은 날)
    python3 research.py --dry-run         (수집만, GPT 호출/저장 안 함)
------------------------------------------------
"""
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import feedparser
except ImportError:
    sys.exit("feedparser 필요: pip3 install feedparser")

from dotenv import load_dotenv
from openai import OpenAI

HERE = Path(__file__).parent

# 같은 폴더의 .env에 있는 OPENAI_API_KEY를 프로세스 환경변수로 읽어온다.
# override=False(기본값)라서 이미 셸에 설정된 환경변수가 있으면 그쪽이 우선한다.
load_dotenv(HERE / ".env")
SOURCES = HERE / "sources.json"
DATA = HERE / "data"
CAND_DIR = DATA / "candidates"
HISTORY = DATA / "history.json"

SELECT_PROMPT = """너는 '칼퇴각' 인스타그램 계정의 편집자다.
독자는 비개발자 일반 직장인이다. 아래는 최근 24시간 AI 뉴스 항목들(제목+요약)이다.

다음 기준으로 오늘의 카드뉴스 후보를 최대 5개 골라라:

선별 기준:
- '이게 내 업무에 뭐가 달라지나'라는 질문에 답이 나오는 것을 우선한다.
- 같은 사건을 여러 매체가 다뤘으면 하나로 병합하고, 대표 출처는 가장 1차에 가까운 것(공식 발표 > 매체)으로 고른다.
- 지나치게 기술적이거나(논문 세부, 벤치마크 수치만 있는 것) 독자와 무관한 것은 제외한다.
- 국내 출시·가격·규제·한국 기업(네이버/카카오/LG/업스테이지) 소식은 로컬 맥락으로 가치가 높으니 우대한다.

각 후보에 대해 아래를 채워라:
- id: "YYYYMMDD-NN" 형식 (오늘 날짜 + 순번)
- title: 한 줄 제목
- one_line: 무슨 소식인지 한 문장
- why_now: 왜 지금 다룰 가치가 있는지 (예: 어젯밤 공식 발표 / 국내 아직 안 다룸)
- angle: 직장인 대상 카드 각도 제안 (예: "비개발자가 당장 써먹는 법 3가지")
- source: 대표 출처 URL (반드시 입력 항목에 있던 실제 링크)
- visual: 시각화 난이도 한줄평 (예: "비교표로 5장 무리 없음")

**순수 JSON 배열만 출력**한다. 설명·마크다운 없이. 좋은 후보가 5개 미만이면 있는 만큼만 출력한다.
좋은 후보가 하나도 없으면 빈 배열 []을 출력한다.
"""


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def collect_items(hours: int) -> list[dict]:
    sources = load_json(SOURCES, {"feeds": []})
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []

    for f in sources["feeds"]:
        if not f.get("enabled", False):
            continue
        feed = feedparser.parse(f["url"], agent="Mozilla/5.0 (kaltoegak research)")
        for e in feed.entries:
            t = e.get("published_parsed") or e.get("updated_parsed")
            when = datetime(*t[:6], tzinfo=timezone.utc) if t else None
            if when and when < cutoff:
                continue
            summary = (e.get("summary") or "").strip()
            # HTML 태그 대충 제거, 길이 제한 (제목+요약만 주기로 함)
            summary = " ".join(summary.replace("<", " <").split())
            if len(summary) > 400:
                summary = summary[:400] + "…"
            items.append({
                "feed": f["name"],
                "tier": f["tier"],
                "title": e.get("title", "").strip(),
                "summary": summary,
                "link": e.get("link", ""),
                "when": when.isoformat() if when else None,
            })
    return items


def filter_history(items: list[dict]) -> list[dict]:
    history = load_json(HISTORY, [])
    seen_links = {h.get("source") for h in history}
    seen_titles = {h.get("title", "").strip() for h in history}
    out = []
    for it in items:
        if it["link"] in seen_links:
            continue
        if it["title"] in seen_titles:
            continue
        out.append(it)
    return out


def select_candidates(client: OpenAI, items: list[dict]) -> list[dict]:
    today = datetime.now().strftime("%Y%m%d")
    lines = [f"오늘 날짜: {today}\n\n항목 목록:"]
    for i, it in enumerate(items, 1):
        lines.append(f"\n[{i}] ({it['feed']}, tier={it['tier']})\n제목: {it['title']}\n요약: {it['summary']}\n링크: {it['link']}")
    user_content = "\n".join(lines)

    resp = client.chat.completions.create(
        model="gpt-5.5",  # 실제 사용 가능한 모델 문자열로 확인 후 조정
        messages=[
            {"role": "system", "content": SELECT_PROMPT},
            {"role": "user", "content": user_content},
        ],
        # gpt-5.5는 기본값(1) 외의 temperature를 지원하지 않는다 — 파라미터 자체를 생략.
    )
    raw = resp.choices[0].message.content.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24, help="수집 시간 창 (기본 24)")
    ap.add_argument("--dry-run", action="store_true", help="수집만, GPT 호출·저장 안 함")
    args = ap.parse_args()

    print(f"[1/3] 최근 {args.hours}시간 수집 중...")
    items = collect_items(args.hours)
    print(f"  수집: {len(items)}건")

    items = filter_history(items)
    print(f"  이력 제외 후: {len(items)}건")

    if not items:
        print("새 항목 없음. 백로그(이전 candidates)에서 꺼내 쓰거나 --hours 48로 넓혀볼 것.")
        return

    if args.dry_run:
        for it in items:
            print(f"  - [{it['feed']}] {it['title']}")
        return

    print("[2/3] GPT-5.5 선별 중...")
    client = OpenAI()
    candidates = select_candidates(client, items)
    print(f"  후보: {len(candidates)}개")

    CAND_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CAND_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.json"
    out_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[3/3] 저장 → {out_path}")

    for c in candidates:
        print(f"\n  {c.get('id')} | {c.get('title')}")
        print(f"    각도: {c.get('angle')}")


if __name__ == "__main__":
    main()