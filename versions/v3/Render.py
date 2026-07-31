#!/usr/bin/env python3
"""
칼퇴각 카드뉴스 렌더러
------------------------------------------------
content.json 하나를 받아서
  - 4:5 캐러셀 PNG 5장 (carousel/01~05.png)
  - 9:16 스토리·릴스 PNG 5장 (story/01~05.png) — 비율만 다를 뿐 슬라이드 구성은 캐러셀과 동일
  - caption.txt, sources.md
를 출력 폴더에 만든다.

스키마 위반(글자수 초과, 출처 누락) 또는 텍스트 넘침이 있으면
그 자리에서 에러를 내고 멈춘다 — 깨진 카드가 조용히 만들어지는 걸 막기 위함.

사용법:
    python3 Render.py content.json
    python3 Render.py content.json ./내출력폴더

템플릿 HTML은 templates/기본/template.html을 사용한다.
------------------------------------------------
"""
import json
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

# Windows 콘솔 기본 코드페이지(cp949)는 ✓/✗/⚠ 같은 기호를 인코딩하지 못해
# 직접 실행이든 subprocess로 실행되든 stdout/stderr를 UTF-8로 고정한다.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# 템플릿은 templates/<템플릿명>/ 폴더에 html+프롬프트 세트로 관리한다(2026-07-29).
# 아직은 "기본" 고정 — 템플릿 선택 인자화는 카드뉴스 제작 페이지의 렌더 단계에서 붙인다.
TEMPLATE = Path(__file__).parent / "templates" / "기본" / "template.html"


def load_content(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_side_files(content: dict, out_dir: Path):
    caption = content.get("caption", "")
    hashtags = " ".join(f"#{h}" for h in content.get("hashtags", []))
    (out_dir / "caption.txt").write_text(f"{caption}\n\n{hashtags}", encoding="utf-8")

    lines = ["# 출처\n"]
    for i, s in enumerate(content.get("slides", []), start=1):
        if s.get("source"):
            lines.append(f"- 슬라이드 {i}: {s['source']}")
    (out_dir / "sources.md").write_text("\n".join(lines), encoding="utf-8")

    (out_dir / "content.json").write_text(
        json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def render(content_path: str, out_dir: Path, template_path: Path = TEMPLATE):
    content = load_content(content_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "carousel").mkdir(exist_ok=True)
    (out_dir / "story").mkdir(exist_ok=True)
    write_side_files(content, out_dir)

    slide_count = len(content.get("slides", [])) + 2  # 표지 1 + 본문 N + CTA 1
    content_json = json.dumps(content, ensure_ascii=False)
    template_url = f"file://{template_path.resolve()}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for ratio, folder in [("45", "carousel"), ("916", "story")]:
                for i in range(slide_count):
                    page = browser.new_page(viewport={"width": 1400, "height": 2100})
                    page.add_init_script(
                        f"window.__EXTERNAL_CONTENT__ = {content_json};"
                    )
                    page.goto(f"{template_url}?r={ratio}&i={i}")
                    page.wait_for_selector('body[data-ready="1"]', timeout=15000)

                    errs = page.evaluate("() => window.__validationErrors || []")
                    if errs:
                        raise RuntimeError(
                            "스키마 검증 실패 — 렌더 중단:\n  - " + "\n  - ".join(errs)
                        )

                    overflow = page.evaluate(
                        "() => { const b = document.querySelector('.bodyc'); "
                        "return b ? b.scrollHeight > b.clientHeight + 2 : false; }"
                    )
                    if overflow:
                        raise RuntimeError(
                            f"슬라이드 {i + 1} ({folder}) 텍스트 넘침 — "
                            "글자수를 줄이거나 상한(LIMITS)을 확인하세요."
                        )

                    out_path = out_dir / folder / f"{i + 1:02d}.png"
                    page.locator(".frame").screenshot(path=str(out_path))
                    page.close()
                    print(f"  ✓ {folder}/{i + 1:02d}.png")
        finally:
            browser.close()

    print(f"\n완료 → {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python3 Render.py content.json [출력폴더] [템플릿 html 경로]")
        sys.exit(1)

    content_path = sys.argv[1]
    if len(sys.argv) > 2:
        out_dir = Path(sys.argv[2])
    else:
        # 기본 출력 경로: ./카드뉴스/오늘날짜
        out_dir = Path("카드뉴스") / date.today().isoformat()
    template_path = Path(sys.argv[3]) if len(sys.argv) > 3 else TEMPLATE

    try:
        render(content_path, out_dir, template_path)
    except RuntimeError as e:
        print(f"\n✗ 렌더 실패\n{e}")
        sys.exit(1)