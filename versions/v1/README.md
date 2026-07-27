# 칼퇴각 콘텐츠 스튜디오 (studio) — v1

조사한 (내용, 출처) 쌍을 손으로 입력하면 인스타그램 카드뉴스(캐러셀 PNG + 스토리/릴스 PNG + 릴스 MP4)를
만들어주는 도구입니다. 이 프로젝트의 원조 버전(v1)이며, 후속 버전인 `app2`가 이 워크플로우 앞단(소재
수집·조사·캡션 작성)을 자동화했습니다 — 자세한 차이는 맨 아래 "app2와의 차이" 참고.

이 폴더 하나로 독립 실행됩니다. 다른 폴더를 참조하지 않으므로, `studio` 폴더 전체만 복사해도 그대로
동작합니다.

## 파이프라인 (Streamlit UI 5단계)

1. **자료 입력 → content.json 생성** — (내용, 출처) 쌍을 여러 개 입력하면 GPT-5.5가 `prompt-content-json.md`
   규칙에 따라 `content.json`을 만든다.
2. **생성 결과 편집** — headline/lede/points/캡션/해시태그를 화면에서 직접 수정한다.
3. **표지 이미지 생성** — GPT Image 2(기본) 또는 Doubao-Seedream(Volcengine Ark) 중 선택. 실패 시 단색 배경으로 자동 폴백.
4. **피드 생성** — `Render.py`(Playwright)로 캐러셀(4:5)·스토리(9:16) PNG를 렌더링, zip으로 다운로드 가능.
5. **릴스 생성** — 스토리 PNG + 배경음악을 ffmpeg로 이어 붙여 MP4 생성.

## 사전 준비

```
python -m venv .venv
.venv\Scripts\Activate.ps1        # PowerShell
pip install -r requirements.txt
playwright install chromium       # Render.py가 Playwright로 카드를 캡처한다
```

- `ffmpeg`가 시스템 PATH에 있어야 한다 (5단계 릴스 생성용). `ffmpeg -version`으로 확인.
- 이 폴더의 `.env` 파일에 API 키를 작성한다 (코드에 키를 직접 쓰지 않는다):
  - `OPENAI_API_KEY` (필수) — content.json 생성(GPT-5.5), 표지 이미지 생성 기본값(GPT Image 2)
  - `ARK_API_KEY` (선택) — 표지 이미지를 Doubao-Seedream으로 생성할 때만 필요
  - `.env`는 `.gitignore`로 제외되어 있다.

## 실행

```
cd studio
streamlit run app.py
```

## 폴더 구성 / 결과물 저장 위치

모두 이 폴더(`studio/`) 안에 저장된다 — 다른 폴더와 공유하지 않는다.

- `카드뉴스/<content_id>/` — 렌더된 캐러셀·스토리 PNG, `reel.mp4`, `content.json`
- `assets/` — 생성된 표지 이미지
- `music/` — 배경음악 라이브러리 (여기 넣어두면 5단계에서 랜덤/직접 선택 가능)

## 이 폴더 안의 파이프라인 스크립트

`app.py`가 화면만 담당하고, 실제 로직은 아래 스크립트를 import 또는 subprocess로 그대로 재사용한다 —
로직을 이 파일 안에서 다시 구현하지 않는다.

- `Generate.py` — `content.json` 생성 + 표지 이미지 생성 로직
- `Render.py` — `card-template.html`을 Playwright로 캡처해 카드뉴스 PNG 생성
- `Render_reel.py` — 스토리 PNG + 배경음악 → 릴스 MP4 조립 (ffmpeg 호출)
- `card-template.html` — 카드 디자인 템플릿 (Generate.py가 아니라 Render.py가 직접 참조)
- `prompt-content-json.md` — content.json 생성 시 GPT에게 주는 규칙 프롬프트

## 알려진 제약

- **2단계 편집 화면은 구버전 스키마(`lede`/`points`)만 지원한다.** `card-template.html`/
  `prompt-content-json.md`는 이후 `beats`(2~3문장 본문), `type:"list"`(정리 슬라이드),
  `type:"compare"`(전후 비교 슬라이드) 같은 더 풍부한 슬라이드 구조를 지원하도록 업데이트됐지만,
  이 화면의 슬라이드 편집 UI(`slide_editor`)는 아직 그 필드들을 위한 입력창이 없다. 1단계에서 GPT가
  새 스키마로 생성한 내용 자체는 유지되지만, 2단계에서 그 슬라이드를 만지면 `lede`/`points`로 되돌아간다.
  새 스키마를 화면에서 직접 편집하고 싶다면 `app2`의 3단계("JSON 보기/편집")를 쓰는 것이 낫다 — 거기는
  전체 JSON을 텍스트로 편집해서 스키마 제약이 없다.
- 소재를 자동으로 찾아오는 기능(RSS 수집)과 딥리서치, 인스타 캡션 자동 생성 기능은 없다 — 전부 `app2`에 있다.

## app2와의 차이

| | studio (v1) | app2 (v1 고도화) |
|---|---|---|
| 소재 수집 | 없음 (직접 조사해서 입력) | 1단계에서 RSS 피드 자동 수집 + history.json으로 중복 제외 |
| 딥리서치 | 없음 | 2단계에서 기사 원문 크롤링 + GPT 조사노트/사실쌍 자동 생성 |
| content.json 편집 | 필드별 폼(구버전 스키마만) | 전체 JSON 텍스트 편집(신버전 스키마 포함 전부 가능) |
| 인스타 캡션 생성 | 없음(1단계에서 GPT가 만든 caption을 그대로 씀) | 7단계에서 딥리서치 노트 기반으로 별도 생성 |
| 단계 수 | 5단계 | 7단계 |
