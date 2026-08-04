"""GPT 후보 선별 + 딥리서치(원문 근거 보강) 실행.

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO를 받고 result DTO를 반환한다.
- 실패는 예외로 알린다. 단, `select_candidates`/`run_deep_research`는 실제 GPT 호출(비용
  발생)이 필요하다 — 코드는 이관해뒀지만 실제 실행 전에는 반드시 사용자 확인을 받는다
  (2026-08-03, `wiki/decisions.md` 참고).

legacy 대응:
- legacy/sources_store.py (select_candidates_from_items, SELECT_PERSONA_TEMPLATE,
  SELECT_CRITERIA_PROMPT, SELECT_OUTPUT_SCHEMA — save_candidates/list_candidate_files/
  load_candidates는 collect_feed_items와 같은 패턴으로 select_candidates 안에 합쳤다.
  load_select_prompt_state/save_select_prompt_state(마지막으로 편집한 프롬프트 기억)는
  이관하지 않았다 — UI 편의 기능이라 이번 단계 범위 밖, `wiki/decisions.md`의 미확정
  목록 참고)
- legacy/pipeline_common.py (fetch_article_text, build_research_prompt,
  run_research_prompt, RESEARCH_NOTE_PROMPT)
- legacy/Research.py (구 CLI 경로 — 참고용, 이관 대상 아님)

`get_research_note`는 저장된 노트를 읽기만 하므로 GPT 호출 없이 이미 이관 완료했다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from ..core.clients import get_openai_client
from ..core.paths import CAND_DIR, RESEARCH_DIR
from . import pipeline


@dataclass
class GetResearchNoteRequest:
    content_id: str


@dataclass
class GetResearchNoteResult:
    content_id: str
    note_path: Path
    note_text: str


@dataclass
class SelectCandidatesRequest:
    group_id: str
    items: list[dict]
    persona: str | None = None
    rules: str | None = None


@dataclass
class SelectCandidatesResult:
    group_id: str
    saved_path: Path
    candidates: list[dict] = field(default_factory=list)


@dataclass
class RunDeepResearchRequest:
    content_id: str
    candidate: dict


@dataclass
class RunDeepResearchResult:
    content_id: str
    note_path: Path
    note_text: str
    fetched_any_article: bool


def get_research_note(request: GetResearchNoteRequest) -> GetResearchNoteResult:
    """저장된 조사 노트를 조회한다. 경로는 매번 새로 정하지 않고 services/pipeline.py 매니페스트의
    `research_note_path`를 그대로 따른다 — 노트 원본 경로는 그쪽이 canonical이다.
    legacy: 파일 시스템 data/research/*.md 직접 읽기 대응"""
    state = pipeline.load_pipeline_state(pipeline.LoadPipelineStateRequest(content_id=request.content_id))
    if not state.research_note_path:
        raise FileNotFoundError(f"조사 노트가 아직 생성되지 않았습니다: {request.content_id}")

    path = Path(state.research_note_path)
    if not path.exists():
        raise FileNotFoundError(f"조사 노트 파일을 찾을 수 없습니다: {path}")

    return GetResearchNoteResult(
        content_id=request.content_id, note_path=path, note_text=path.read_text(encoding="utf-8")
    )


# ============================================================
# GPT 후보 선별 — legacy: sources_store.select_candidates_from_items
# ============================================================
SELECT_PERSONA_TEMPLATE = """(이 계정의 성격과 독자를 적어주세요 - 예: "너는 '자동화세상' 인스타그램 계정의 편집자다. 독자는 뉴스에 관심이 많은 사람이다.")"""

SELECT_CRITERIA_PROMPT = """아래는 사용자가 오늘의 카드뉴스 소재 후보로 직접 고른 뉴스 항목들(제목+요약)이다.

다음 기준으로 후보를 추려 카드뉴스 후보 카드로 정리하라:
- 같은 사건을 여러 항목이 다뤘으면 하나로 병합하고, 대표 출처는 가장 1차에 가까운 것(공식 발표 > 매체)으로 고른다.
- 내용이 사실상 겹치는 항목도 하나로 합친다(중복 제거).
- 독자의 흥미를 끄는 후킹 요소(의외성, 숫자 임팩트, 논쟁성, 실생활 영향 등)가 강한 순으로 우선한다.
- 최대 10개까지만 선별한다. 좋은 후보가 10개 미만이면 있는 만큼만 출력한다."""

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


def _candidates_folder(group_id: str) -> Path:
    return CAND_DIR / group_id


def select_candidates(request: SelectCandidatesRequest) -> SelectCandidatesResult:
    """RSS 원본 중 선택 항목을 GPT로 카드뉴스 후보로 정리해 저장한다.
    실제 GPT 호출(비용 발생) — 실행 전 사용자 확인 필요(모듈 docstring 참고).
    legacy: sources_store.select_candidates_from_items + save_candidates"""
    persona = request.persona if request.persona is not None else SELECT_PERSONA_TEMPLATE
    rules = request.rules if request.rules is not None else SELECT_CRITERIA_PROMPT
    system_prompt = f"{persona}\n\n{rules}\n\n{SELECT_OUTPUT_SCHEMA}"

    today = date.today().strftime("%Y%m%d")
    lines = [f"오늘 날짜: {today}\n\n항목 목록:"]
    for i, it in enumerate(request.items, 1):
        lines.append(
            f"\n[{i}] ({it.get('feed', '')}, tier={it.get('tier', '')})\n"
            f"제목: {it.get('title', '')}\n요약: {it.get('summary', '')}\n링크: {it.get('link', '')}"
        )
    user_content = "\n".join(lines)

    client = get_openai_client()
    resp = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    candidates = json.loads(raw)

    folder = _candidates_folder(request.group_id)
    folder.mkdir(parents=True, exist_ok=True)
    saved_path = folder / f"{date.today().isoformat()}.json"
    saved_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")

    return SelectCandidatesResult(group_id=request.group_id, saved_path=saved_path, candidates=candidates)


# ============================================================
# 딥리서치 — legacy: pipeline_common.fetch_article_text/build_research_prompt/
# run_research_prompt/RESEARCH_NOTE_PROMPT
# ============================================================
_ARTICLE_FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) kaltoegak-research"}
_ARTICLE_STRIP_TAGS = ("script", "style", "nav", "header", "footer", "aside", "form", "iframe")

RESEARCH_NOTE_PROMPT = """아래 후보에 대해, 소스를 최대한 상세하게 분석하는 조사 노트를 작성하라.
아래 "기사 원문"들과 "후보 요약"에 담긴 사실만 쓰고, 없는 사실은 지어내지 마라. 웹 검색은 하지 않는다
(이미 주어진 원문/요약 밖의 새로운 정보를 찾으러 나가지 않는다는 뜻).

저작권: 원문은 뉴스 기사이므로, 숫자·날짜·기관명·발언의 요지 같은 **사실**은 정확히 유지하되 **문장은
원문을 그대로(또는 어순만 살짝 바꿔) 옮기지 말고 새로 써라.** 원문 문장을 그대로 인용해야만 하는
경우가 아니면 verbatim 문장을 쓰지 않는다 — 직접 인용이 꼭 필요하면 따옴표로 표시하고 누구의 말인지
밝힌다.

출력 형식:
마크다운으로 조사 노트 하나만 작성한다 (배경, 핵심 사실, 왜 지금 다룰 가치가 있는지, 관련 맥락과 함의,
특이사항·주의할 점 등). 원문에 있는 구체적인 숫자·날짜·기관명·발언 내용을 최대한 살려서 쓰되,
문장 자체는 원문을 베끼지 않고 새로 쓴다 — 뭉뚱그리지도, 그대로 옮기지도 않는다. 원문이 여러 건이면
겹치는 사실은 교차 확인된 것으로, 서로 다른 사실은 모두 반영해서 쓴다. 목표는 원문 문장의 요약이나
복사가 아니라, 원문에 있는 사실을 빠짐없이·정확하게·새 문장으로 옮겨 담는 것이다.
이 노트는 다음 단계(카드뉴스 생성)가 참고자료로 그대로 읽는다 — 노트에 없는 사실은 콘텐츠에 쓸 수
없으므로, 확인된 사실은 빠짐없이 담는다. 문서 맨 끝에는 `## 출처` 섹션을 두고 실제로 참고한 원문
URL을 목록으로 적는다 (아래 "출처 목록"에 있는 URL만 쓸 수 있다 — 없는 링크를 만들어내지 않는다).

후보:
- 제목: {title}
- 한 줄 요약: {one_line}
- 카드 각도: {angle}

출처 목록:
{sources}

기사 원문(참고용, 없으면 "없음" — 여러 건이면 [출처: URL]로 구분됨):
{article_text}
"""


def _fetch_article_text(url: str, max_chars: int = 6000) -> str | None:
    """후보의 source URL을 열어 기사 본문 텍스트를 뽑아온다. 실패(타임아웃/비-200/본문 없음)하면
    None을 반환한다 — 예외를 밖으로 던지지 않는다(원문 fetch 실패는 노트 생성 자체를 막지 않는다).
    legacy: pipeline_common.fetch_article_text"""

    def paragraph_text(container) -> str:
        paragraphs = [p.get_text(" ", strip=True) for p in container.find_all("p")]
        return "\n".join(p for p in paragraphs if p)

    try:
        resp = requests.get(url, timeout=10, headers=_ARTICLE_FETCH_HEADERS)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(_ARTICLE_STRIP_TAGS):
            tag.decompose()

        text = max((paragraph_text(a) for a in soup.find_all("article")), key=len, default="")
        if len(text) < 200 and soup.body is not None:
            body_text = paragraph_text(soup.body)
            if len(body_text) > len(text):
                text = body_text
        text = text.strip()
        if not text:
            return None
        return text[:max_chars]
    except Exception:
        return None


def _build_research_prompt(candidate: dict) -> tuple[str, bool]:
    """legacy: pipeline_common.build_research_prompt"""
    urls = candidate.get("sources") or [candidate.get("source", "")]
    urls = [u for u in dict.fromkeys(urls) if u]

    fetched = [(url, text) for url in urls if (text := _fetch_article_text(url))]
    if fetched:
        article_text = "\n\n".join(f"[출처: {url}]\n{text}" for url, text in fetched)
    else:
        article_text = "없음"

    prompt = RESEARCH_NOTE_PROMPT.format(
        title=candidate.get("title", ""),
        one_line=candidate.get("one_line", ""),
        angle=candidate.get("angle", ""),
        sources="\n".join(urls) if urls else "(없음)",
        article_text=article_text,
    )
    return prompt, bool(fetched)


def run_deep_research(request: RunDeepResearchRequest) -> RunDeepResearchResult:
    """후보의 출처 링크를 원문으로 읽어 조사 노트를 생성하고 저장한다. 완료 후
    services/pipeline.py 매니페스트에 candidate와 research_note_path를 함께 기록한다
    (legacy는 "이 후보로 진행"과 "딥리서치 실행"을 별도 화면 단계로 나눴지만, job 단위로는
    하나로 묶는 게 자연스러워 합쳤다 — 2026-08-03).
    실제 GPT 호출(비용 발생) — 실행 전 사용자 확인 필요(모듈 docstring 참고).
    legacy: pipeline_common.build_research_prompt/run_research_prompt"""
    prompt, fetched_any = _build_research_prompt(request.candidate)

    client = get_openai_client()
    resp = client.chat.completions.create(
        model="gpt-5.5",
        messages=[{"role": "user", "content": prompt}],
    )
    note_text = resp.choices[0].message.content.strip()

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    note_path = RESEARCH_DIR / f"{request.content_id}.md"
    note_path.write_text(note_text, encoding="utf-8")

    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(
            content_id=request.content_id, candidate=request.candidate, research_note_path=str(note_path)
        )
    )

    return RunDeepResearchResult(
        content_id=request.content_id, note_path=note_path, note_text=note_text, fetched_any_article=fetched_any
    )
