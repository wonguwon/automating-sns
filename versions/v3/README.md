# 칼퇴각 파이프라인 (app2) — v1 고도화판

`studio`(v1)에서는 소재 조사와 (내용, 출처) 입력을 손으로 해야 했다. app2는 그 앞단 — 소재 발굴부터
딥리서치, 인스타 캡션 작성까지 — 을 자동화해 하나의 흐름으로 이어붙인 후속 버전이다. 카드 디자인
(`card-template.html`)과 생성 규칙(`prompt-content-json.md`)은 studio와 동일한 최신 버전을 쓴다.

이 폴더 하나로 독립 실행됩니다. 다른 폴더를 참조하지 않으므로, `app2` 폴더 전체만 복사해도 그대로
동작합니다.

## 파이프라인 (Streamlit UI 7단계)

1. **후보 가져오기** — `Research.py`가 `sources.json`의 RSS 피드에서 최근 24시간 항목을 모으고,
   `data/history.json`과 대조해 이미 다룬 소재를 제외한 뒤 GPT-5.5로 후보 5개를 선별한다.
2. **딥리서치** — 선택한 후보의 원문 URL을 크롤링하고, GPT-5.5로 조사 노트(마크다운) + (내용, 출처) 쌍
   배열을 생성한다.
3. **콘텐츠 JSON** — 딥리서치에서 뽑은 사실 쌍으로 `content.json`을 생성하고, 필요하면 화면에서 전체
   JSON을 텍스트로 직접 편집한다 (`beats`/`type:"list"`/`type:"compare"` 등 최신 스키마 전부 편집 가능).
4. **표지 이미지 생성** — 프롬프트를 화면에서 직접 수정 가능. GPT Image 2(기본) 또는 Doubao-Seedream 중 선택.
5. **콘텐츠 렌더** — `Render.py`(Playwright)로 캐러셀(4:5)·스토리(9:16) PNG 생성, `data/history.json`에 기록.
6. **릴스 렌더** — 스토리 PNG + `music/`의 배경음악을 ffmpeg로 이어 붙여 MP4 생성.
7. **인스타 설명란 문구** — 딥리서치 노트를 참고해 캡션(훅 문장 + 해시태그)을 별도로 생성.

## 사전 준비

```
python -m venv .venv
.venv\Scripts\Activate.ps1        # PowerShell
pip install -r requirements.txt
playwright install chromium       # Render.py가 Playwright로 카드를 캡처한다
```

- `ffmpeg`가 시스템 PATH에 있어야 한다 (6단계 릴스 생성용). `ffmpeg -version`으로 확인.
- 이 폴더의 `.env` 파일에 API 키를 작성한다 (코드에 키를 직접 쓰지 않는다):
  - `OPENAI_API_KEY` (필수) — 후보 선별·딥리서치·content.json·캡션 생성(GPT-5.5), 표지 이미지 기본값(GPT Image 2)
  - `ARK_API_KEY` (선택) — 표지 이미지를 Doubao-Seedream으로 생성할 때만 필요
  - `.env`는 `.gitignore`로 제외되어 있다.
- `sources.json`에 수집할 RSS 피드 목록이 있다. `enabled: true`인 피드만 1단계에서 수집한다.

## 실행

```
cd app2
streamlit run app.py
```

## 폴더 구성 / 결과물 저장 위치

모두 이 폴더(`app2/`) 안에 저장된다 — 다른 폴더와 공유하지 않는다.

- `data/candidates/` — 날짜별 후보 목록 (1단계 결과)
- `data/research/` — 딥리서치 노트 마크다운 (2단계 결과)
- `data/content/`, `data/history.json` — 렌더 완료된 콘텐츠와 발행 이력 (같은 소재 재수집 방지에 쓰임)
- `카드뉴스/<content_id>/` — 렌더된 캐러셀·스토리 PNG, `reel.mp4`, `content.json`
- `assets/` — 생성된 표지 이미지
- `music/` — 배경음악 라이브러리

## 이 폴더 안의 파이프라인 스크립트

`app.py`가 화면만 담당하고, 실제 로직은 아래 스크립트를 import 또는 subprocess로 그대로 재사용한다 —
로직을 이 파일 안에서 다시 구현하지 않는다.

- `Research.py` — RSS 수집 + 후보 선별 (1단계, subprocess로 호출)
- `Generate.py` — `content.json` 생성 + 표지 이미지 생성 로직 (2~4단계에서 함수로 import)
- `Render.py` — `card-template.html`을 Playwright로 캡처해 카드뉴스 PNG 생성 (5단계, subprocess로 호출)
- `Render_reel.py` — 스토리 PNG + 배경음악 → 릴스 MP4 조립 (6단계, subprocess로 호출)
- `card-template.html` — 카드 디자인 템플릿 (Render.py가 직접 참조)
- `prompt-content-json.md` — content.json 생성 시 GPT에게 주는 규칙 프롬프트
- `sources.json` — 1단계에서 수집할 RSS 피드 목록

## studio와의 차이

| | studio (v1) | app2 (v1 고도화) |
|---|---|---|
| 소재 수집 | 없음 (직접 조사해서 입력) | 1단계에서 RSS 피드 자동 수집 + history.json으로 중복 제외 |
| 딥리서치 | 없음 | 2단계에서 기사 원문 크롤링 + GPT 조사노트/사실쌍 자동 생성 |
| content.json 편집 | 필드별 폼(구버전 스키마만) | 전체 JSON 텍스트 편집(신버전 스키마 포함 전부 가능) |
| 인스타 캡션 생성 | 없음(1단계에서 GPT가 만든 caption을 그대로 씀) | 7단계에서 딥리서치 노트 기반으로 별도 생성 |
| 단계 수 | 5단계 | 7단계 |
