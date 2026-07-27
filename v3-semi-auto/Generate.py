#!/usr/bin/env python3
"""
칼퇴각 콘텐츠 생성기 — Flow 2 본체
------------------------------------------------
조사 자료(텍스트)를 넣으면:
  1) GPT-5.5로 content.json 생성 (prompt-content-json.md 규칙 적용)
  2) 표지 이미지 생성 — GPT Image 2(기본) 또는 Volcengine Ark Doubao-Seedream 중 선택 (실패 시 null 폴백)
  3) Render.py 실행 → PNG 10장

오늘은 손으로 여러 번 실행해보며 프롬프트 품질을 다지는 용도.
나중엔 헤르메스가 플로우2에서 이 스크립트를 그대로 호출한다.

사전 준비
    pip3 install openai python-dotenv
    이 폴더(app2)의 .env 파일에 OPENAI_API_KEY=sk-... 작성 (코드에 키를 직접 쓰지 말 것)
    --image-provider seedream을 쓰려면 같은 파일에 ARK_API_KEY=...도 추가
    (.env가 없으면 시스템 환경변수로 폴백한다)

사용법
    python3 Generate.py --topic topic.txt
    python3 Generate.py --topic topic.txt --no-image   (이미지 생략, 빠른 반복 테스트용)
    python3 Generate.py --topic topic.txt --id 20260719-02
    python3 Generate.py --topic topic.txt --image-provider seedream   (Doubao-Seedream으로 표지 생성)
------------------------------------------------
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

HERE = Path(__file__).parent

# 같은 폴더의 .env에 있는 OPENAI_API_KEY / ARK_API_KEY를 프로세스 환경변수로 읽어온다.
# override=False(기본값)라서 이미 셸에 설정된 환경변수가 있으면 그쪽이 우선한다.
load_dotenv(HERE / ".env")

# Volcengine Ark(바이트댄스)는 OpenAI 호환 API를 제공하므로 openai 패키지를 그대로 쓰되
# base_url과 api_key만 바꿔서 별도 클라이언트를 만든다.
ARK_BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3"
SEEDREAM_MODEL = "seedream-5-0-260128"

# Windows 콘솔 기본 코드페이지(cp949)는 ⚠/✗ 같은 기호를 인코딩하지 못해
# 직접 실행이든 subprocess로 실행되든 stdout/stderr를 UTF-8로 고정한다.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PROMPT_PATH = HERE / "prompt-content-json.md"
ASSETS_DIR = HERE / "assets"

IMAGE_PROMPT_TEMPLATE = """한국 디지털 뉴스 매체의 세로형 썸네일에 사용할 사실적인 보도사진을 만들어주세요.

주제: {concept}

구도: 아래 주제에 가장 잘 어울리는 소재를 자유롭게 고릅니다 — 사람의 뒷모습·옆모습·실루엣, 손이나 도구의 클로즈업, 장소나 건물의 풍경, 화면·차트·서류 같은 사물, 여러 사람이 있는 현장 등. 매번 같은 인물 뒷모습 구도로 고정하지 말고 주제마다 다르게 선택합니다. 사람이 등장할 경우 얼굴이 정면으로 또렷하게 드러나지 않게 합니다. 화면 하단부는 나중에 자동으로 어둡게 처리되어 글자가 얹히므로, 특정 위치에 여백을 미리 비워둘 필요는 없습니다. 이미지 안에는 실제 글자나 로고를 넣지 마세요.

스타일: 한국에서 실제 기자가 촬영한 보도사진처럼 자연스럽고 신뢰감 있게 표현합니다. 흐린 날의 부드러운 자연광, 낮은 채도, 절제된 색감, 35mm 다큐멘터리 사진, 현실적인 인체와 건축물, 과장되지 않은 긴장감을 사용합니다.

제외: 영화 포스터, 스톡사진 포즈, 정면 얼굴, 과도한 보케, SF 인터페이스, 일러스트, 3D 렌더링, 글자, 워터마크를 제외합니다."""


def load_system_prompt() -> str:
    if not PROMPT_PATH.exists():
        sys.exit(f"프롬프트 파일을 찾을 수 없음: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def generate_content_json(client: OpenAI, pairs: list[dict], content_id: str) -> dict:
    """
    pairs: [{ "content": "...", "source": "https://..." }, ...]
    최소 1쌍이면 충분하다. 개수 제한 없음.
    """
    system_prompt = load_system_prompt()
    pairs_json = json.dumps(pairs, ensure_ascii=False, indent=2)
    user_prompt = (
        f"오늘 채택된 소재 ID: {content_id}\n\n"
        f"아래는 (내용, 출처) 쌍 배열이다. 이 안에 명시된 사실만 사용해서 스키마에 맞는 JSON을 만들어라.\n\n"
        f"{pairs_json}"
    )

    resp = client.chat.completions.create(
        model="gpt-5.5",  # 실제 사용 가능한 모델 문자열로 확인 후 조정할 것
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        # gpt-5.5는 기본값(1) 외의 temperature를 지원하지 않는다 — 파라미터 자체를 생략.
    )

    raw = resp.choices[0].message.content.strip()
    # 혹시 모델이 코드펜스를 붙였으면 벗겨낸다
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()

    try:
        content = json.loads(raw)
    except json.JSONDecodeError as e:
        print("=== 모델 원본 출력 ===")
        print(raw)
        sys.exit(f"\n✗ JSON 파싱 실패: {e}\n → 프롬프트나 모델 출력을 점검할 것")

    content["id"] = content_id
    return content


def generate_cover_image(
    client: OpenAI,
    concept: str,
    content_id: str,
    extra_direction: str = "",
    provider: str = "openai",
) -> str | None:
    """
    concept: content.json의 cover.image_concept (없으면 headline 폴백).
    헤드라인 문구가 아니라 "장소+인물/사물+비교+변화+분위기" 공식으로 쓴 장면 묘사여야 한다
    (prompt-content-json.md의 '표지 이미지 컨셉' 절 참고).
    IMAGE_PROMPT_TEMPLATE는 플레이그라운드에서 검증 후 고정한 값이므로 이 함수 밖에서 바꾸지 않는다.
    재생성할 때는 concept는 그대로 두고 extra_direction만 바꿔서 다시 호출하면 된다.

    provider: "openai"(기본, GPT Image 2) 또는 "seedream"(Volcengine Ark, Doubao-Seedream).
    seedream을 쓰려면 환경변수 ARK_API_KEY가 설정돼 있어야 한다 — 인자로 받은 client는
    OPENAI_API_KEY로 만들어진 것이라 이 경로에서는 쓰지 않고, Ark용 클라이언트를 새로 만든다.
    """
    prompt = IMAGE_PROMPT_TEMPLATE.replace("{concept}", concept)
    if extra_direction.strip():
        prompt += f"\n\n추가 지시: {extra_direction.strip()}"

    try:
        if provider == "seedream":
            ark_api_key = os.environ.get("ARK_API_KEY")
            if not ark_api_key:
                print("⚠ ARK_API_KEY 환경변수가 없음 — 단색 폴백으로 진행")
                return None
            ark_client = OpenAI(api_key=ark_api_key, base_url=ARK_BASE_URL)
            resp = ark_client.images.generate(
                model=SEEDREAM_MODEL,
                prompt=prompt,
                # Seedream은 최소 3,686,400픽셀 이상을 요구해 1024x1536(2:3)로는 400 에러가 난다.
                # 1664x2496도 2:3 비율을 유지하면서 최소 픽셀 수를 넘긴다.
                size="1664x2496",
                # watermark는 openai SDK의 images.generate()가 아는 파라미터가 아니라
                # (Ark 전용 필드) extra_body로 넘겨야 요청 바디에 실제로 포함된다.
                extra_body={"watermark": False},
            )
        else:
            resp = client.images.generate(
                model="gpt-image-2",  # 실제 사용 가능한 모델 문자열로 확인 후 조정할 것
                prompt=prompt,
                size="1024x1536",
                quality="high",
            )
        url_or_b64 = resp.data[0]
        ASSETS_DIR.mkdir(exist_ok=True)
        out_path = ASSETS_DIR / f"cover-{content_id}.png"

        if getattr(url_or_b64, "url", None):
            urllib.request.urlretrieve(url_or_b64.url, out_path)
        elif getattr(url_or_b64, "b64_json", None):
            import base64
            out_path.write_bytes(base64.b64decode(url_or_b64.b64_json))
        else:
            print("⚠ 이미지 응답 형식을 인식하지 못함 — 폴백 처리")
            return None

        # Windows 경로(백슬래시)를 f-string으로 그냥 붙이면 CSS url()에서
        # 백슬래시가 이스케이프 문자로 해석돼 이미지가 로드되지 않는다.
        # as_uri()는 항상 정규 형식(file:///C:/...)의 슬래시로 만들어준다.
        return out_path.resolve().as_uri()
    except Exception as e:
        print(f"⚠ 이미지 생성 실패, 단색 폴백으로 진행: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True, help="(내용, 출처) 쌍 배열이 담긴 JSON 파일 경로")
    ap.add_argument("--id", default=None, help="콘텐츠 ID (기본: 오늘날짜-01)")
    ap.add_argument("--no-image", action="store_true", help="이미지 생성 생략 (빠른 반복용)")
    ap.add_argument("--concept", default=None, help="표지 이미지 컨셉 문장 (없으면 cover.image_concept, 그다음 headline 순으로 폴백)")
    ap.add_argument("--extra", default="", help="이미지 추가 지시문 (고정 템플릿 뒤에 덧붙임)")
    ap.add_argument(
        "--image-provider",
        choices=["openai", "seedream"],
        default="openai",
        help="표지 이미지 생성 API 선택 (openai=GPT Image 2 기본값, seedream=Volcengine Ark Doubao-Seedream, ARK_API_KEY 필요)",
    )
    args = ap.parse_args()

    content_id = args.id or f"{date.today().isoformat().replace('-', '')}-01"
    pairs = json.loads(Path(args.topic).read_text(encoding="utf-8"))

    client = OpenAI()  # OPENAI_API_KEY 환경변수 사용

    print(f"[1/3] content.json 생성 중... (id={content_id})")
    content = generate_content_json(client, pairs, content_id)

    if not args.no_image:
        print("[2/3] 표지 이미지 생성 중...")
        concept = (
            args.concept
            or content["cover"].get("image_concept")
            or content["cover"]["headline"].replace("\n", " ")
        )
        image_path = generate_cover_image(client, concept, content_id, args.extra, provider=args.image_provider)
        content["cover"]["image"] = image_path
        print(f"  → {image_path or '(폴백: 단색 배경)'}")
    else:
        print("[2/3] 이미지 생성 생략")

    out_dir = HERE / "카드뉴스" / content_id
    out_dir.mkdir(parents=True, exist_ok=True)
    content_path = out_dir / "content.json"
    content_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {content_path}")

    print("[3/3] Render.py 실행 중...")
    result = subprocess.run(
        [sys.executable, str(HERE / "Render.py"), str(content_path), str(out_dir)],
        capture_output=True, text=True, encoding="utf-8",
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        sys.exit(f"\n✗ 렌더 실패 (id={content_id})")

    print(f"\n완료 → {out_dir}")


if __name__ == "__main__":
    main()