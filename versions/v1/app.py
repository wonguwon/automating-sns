#!/usr/bin/env python3
"""
칼퇴각 콘텐츠 스튜디오 — Streamlit UI
------------------------------------------------
Generate.py / Render.py / Render_reel.py의 로직을 그대로 import해서 화면만 씌운 것.
여기서 콘텐츠 생성·이미지 생성·렌더링·릴스 조립 로직을 다시 구현하지 않는다.

이 폴더(studio) 하나로 독립 실행되도록 Generate.py/Render.py/Render_reel.py/card-template.html/
prompt-content-json.md/music를 모두 이 폴더 안에 둔다. 다른 폴더를 참조하지 않는다 — studio
폴더 전체만 복사해도 그대로 실행된다.

실행:
    cd studio
    streamlit run app.py

사전 준비:
    이 폴더의 .env 파일에 OPENAI_API_KEY=sk-... 한 줄 작성
    표지 이미지 생성에서 Doubao-Seedream(Volcengine Ark)을 쓰려면 같은 파일에
    ARK_API_KEY=... 한 줄을 추가한다 (3단계 화면에서 API를 선택할 수 있다).
    코드에 키를 직접 쓰지 않는다 — .env는 .gitignore로 제외되어 있다.
    5단계(릴스 생성)를 쓰려면 ffmpeg가 시스템 PATH에 설치되어 있어야 한다.
------------------------------------------------
"""
import io
import json
import os
import random
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import streamlit as st
from dotenv import dotenv_values
from openai import OpenAI

# 이 폴더 자체가 Generate.py, Render.py, Render_reel.py가 있는 곳이다.
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from Generate import generate_content_json, generate_cover_image  # noqa: E402
from Render_reel import build_reel  # noqa: E402

RENDER_PY = HERE / "Render.py"
OUT_ROOT = HERE / "카드뉴스"
MUSIC_DIR = HERE / "music"
MUSIC_EXTS = ("*.mp3", "*.m4a", "*.wav", "*.aac")

# OPENAI_API_KEY는 이 폴더의 .env에서만 읽는다 (시스템 환경변수보다 우선).
# .env가 없거나 키가 비어 있으면 시스템 환경변수로 폴백한다.
_env_values = dotenv_values(HERE / ".env")
OPENAI_API_KEY = _env_values.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")

# ARK_API_KEY(표지 이미지 provider="seedream"용)도 동일하게 이 폴더의 .env에서 읽는다.
# Generate.py의 generate_cover_image()는 이 값을 os.environ에서 직접 읽으므로
# (CLI 실행과 동일한 경로를 타도록) 여기서 프로세스 환경변수에 채워 넣어준다.
ARK_API_KEY = _env_values.get("ARK_API_KEY") or os.environ.get("ARK_API_KEY")
if ARK_API_KEY:
    os.environ.setdefault("ARK_API_KEY", ARK_API_KEY)

# card-template.html의 LIMITS 상수와 동일 — 표시용 카운터 기준일 뿐,
# 실제 상한 검증은 Render.py(→card-template.html)가 한다.
LIMITS = {"hook_reel": 20, "lede": 45, "point": 30}

st.set_page_config(page_title="칼퇴각 콘텐츠 스튜디오", layout="wide")


# ============================================================
# 공용 헬퍼
# ============================================================
@st.cache_resource
def get_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY가 없습니다. 이 폴더의 .env 파일에 OPENAI_API_KEY=sk-...를 추가하세요."
        )
    return OpenAI(api_key=OPENAI_API_KEY)


def counter_caption(n: int, limit: int, note: str = "") -> None:
    text = f"{n}/{limit}자{note}"
    if n > limit:
        st.caption(f":red[**{text} — 초과**]")
    else:
        st.caption(f":gray[{text}]")


def to_local_path(file_uri: str) -> str:
    if not file_uri.startswith("file://"):
        return file_uri
    return url2pathname(urlparse(file_uri).path)


def list_music_library() -> list:
    if not MUSIC_DIR.exists():
        return []
    files = []
    for pattern in MUSIC_EXTS:
        files.extend(MUSIC_DIR.glob(pattern))
    return sorted(files)


def zip_folder(folder: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in folder.rglob("*"):
            if f.is_file():
                zf.write(f, arcname=f.relative_to(folder))
    return buf.getvalue()


def points_editor(key: str, initial_lines: list, limit_per: int = 30, max_items: int = 2) -> list:
    raw = st.text_area(
        "points (줄바꿈으로 항목 구분)",
        value="\n".join(initial_lines or []),
        key=key,
        height=90,
    )
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    for idx, line in enumerate(lines, start=1):
        counter_caption(len(line), limit_per, note=f" (항목 {idx})")
    if len(lines) > max_items:
        st.caption(f":red[**포인트는 최대 {max_items}개까지입니다 (현재 {len(lines)}개)**]")
    return lines


def slide_editor(idx: int, slide: dict) -> None:
    st.markdown(f"**슬라이드 {idx + 1}**")
    slide["eyebrow"] = st.text_input("eyebrow", value=slide.get("eyebrow", ""), key=f"slide_{idx}_eyebrow")
    slide["headline"] = st.text_area("headline", value=slide.get("headline", ""), key=f"slide_{idx}_headline", height=80)

    mode_options = ["한 문장 (lede)", "포인트 목록 (points)"]
    default_mode = 1 if "points" in slide else 0
    mode = st.radio("설명 방식", mode_options, index=default_mode, key=f"slide_{idx}_mode", horizontal=True)

    if mode == mode_options[0]:
        slide["lede"] = st.text_input("lede", value=slide.get("lede", ""), key=f"slide_{idx}_lede")
        counter_caption(len(slide["lede"]), LIMITS["lede"])
        slide.pop("points", None)
    else:
        slide["points"] = points_editor(f"slide_{idx}_points", slide.get("points", []), LIMITS["point"])
        slide.pop("lede", None)

    slide["source"] = st.text_input("source (출처 URL)", value=slide.get("source", ""), key=f"slide_{idx}_source")
    st.divider()


def show_gallery(folder: Path, title: str) -> None:
    files = sorted(folder.glob("*.png"))
    if not files:
        st.info(f"{title}: 생성된 이미지가 없습니다.")
        return
    st.markdown(f"**{title}** ({len(files)}장)")
    cols = st.columns(len(files))
    for col, f in zip(cols, files):
        with col:
            st.image(str(f), use_container_width=True)
            st.caption(f.name)


# ============================================================
# 세션 상태 초기화
# ============================================================
st.session_state.setdefault("pair_ids", [0])
st.session_state.setdefault("next_pair_id", 1)
st.session_state.setdefault("content", None)
st.session_state.setdefault("cover_image_path", None)
st.session_state.setdefault("cover_concept", None)
st.session_state.setdefault("feed_out_dir", None)
st.session_state.setdefault("reel_path", None)

st.title("칼퇴각 콘텐츠 스튜디오")
st.info("업로드는 인스타 앱에서 직접 해야 합니다. 이 화면은 이미지·문구 생성까지만 담당합니다.")
if not OPENAI_API_KEY:
    st.warning(
        "OPENAI_API_KEY가 설정되지 않았습니다. `이 폴더의 .env` 파일을 만들고 "
        "`OPENAI_API_KEY=sk-...` 한 줄을 추가하세요. "
        "생성 버튼을 누르기 전까지는 화면만 확인할 수 있습니다."
    )

# ============================================================
# 1단계 — 자료 입력 → content.json 생성
# ============================================================
st.header("1단계 — 자료 입력 → content.json 생성")

default_id = date.today().strftime("%Y%m%d") + "-01"
content_id_value = st.text_input("콘텐츠 ID", value=default_id, key="content_id_input")

st.subheader("조사 자료 (내용 · 출처 쌍)")
for pid in list(st.session_state.pair_ids):
    with st.container(border=True):
        c1, c2 = st.columns([3, 2])
        with c1:
            st.text_area("content", key=f"content_{pid}", height=100)
        with c2:
            st.text_input("source (URL)", key=f"source_{pid}")
        if len(st.session_state.pair_ids) > 1:
            if st.button("삭제", key=f"del_{pid}"):
                st.session_state.pair_ids.remove(pid)
                st.rerun()

if st.button("+ 자료 추가"):
    st.session_state.pair_ids.append(st.session_state.next_pair_id)
    st.session_state.next_pair_id += 1
    st.rerun()

if st.button("① content.json 생성", type="primary"):
    pairs = []
    for pid in st.session_state.pair_ids:
        c = st.session_state.get(f"content_{pid}", "").strip()
        s = st.session_state.get(f"source_{pid}", "").strip()
        if c and s:
            pairs.append({"content": c, "source": s})

    if not pairs:
        st.warning("최소 1쌍의 (내용, 출처)를 입력해주세요.")
    else:
        try:
            client = get_client()
            with st.spinner("content.json 생성 중..."):
                st.session_state.content = generate_content_json(client, pairs, content_id_value)
            st.session_state.cover_image_path = None
            st.session_state.cover_concept = None
            st.session_state.feed_out_dir = None
            st.session_state.reel_path = None
            st.success("content.json이 생성되었습니다. 아래 2단계에서 확인·수정하세요.")
        except Exception as e:
            st.error(f"content.json 생성 실패: {e}")

# ============================================================
# 2단계 — 생성 결과 편집
# ============================================================
st.header("2단계 — 생성 결과 편집")
content = st.session_state.content

if not content:
    st.info("먼저 1단계에서 content.json을 생성하세요.")
else:
    content["hook_reel"] = st.text_input("hook_reel", value=content.get("hook_reel", ""), key="f_hook_reel")
    counter_caption(len(content["hook_reel"]), LIMITS["hook_reel"])

    st.markdown("**cover**")
    content["cover"]["headline"] = st.text_area(
        "cover.headline", value=content["cover"].get("headline", ""), key="f_cover_headline", height=80
    )
    counter_caption(len(content["cover"]["headline"]), LIMITS["lede"])
    content["cover"]["lede"] = st.text_input("cover.lede", value=content["cover"].get("lede", ""), key="f_cover_lede")
    counter_caption(len(content["cover"]["lede"]), LIMITS["lede"])
    content["cover"]["image_concept"] = st.text_area(
        "cover.image_concept (이미지 생성용 장면 묘사 — headline과 별개)",
        value=content["cover"].get("image_concept", ""),
        key="f_cover_image_concept",
        height=80,
        help="장소+핵심 사물/인물+무엇을 비교하는지+어떤 변화가 보이는지+분위기 공식으로 작성 (prompt-content-json.md 참고). 비워두면 3단계에서 headline으로 대체됩니다.",
    )
    st.divider()

    st.markdown("**본문 슬라이드 (slides)**")
    for i, slide in enumerate(content.get("slides", [])):
        slide_editor(i, slide)

    st.markdown("**cta**")
    content["cta"]["headline"] = st.text_area(
        "cta.headline", value=content["cta"].get("headline", ""), key="f_cta_headline", height=80
    )
    content["cta"]["lede"] = st.text_input("cta.lede", value=content["cta"].get("lede", ""), key="f_cta_lede")
    counter_caption(len(content["cta"]["lede"]), LIMITS["lede"])
    st.divider()

    st.markdown("**캡션 · 해시태그**")
    content["caption"] = st.text_area("caption", value=content.get("caption", ""), key="f_caption", height=150)
    hashtags_raw = st.text_input(
        "hashtags (쉼표로 구분)", value=", ".join(content.get("hashtags", [])), key="f_hashtags"
    )
    content["hashtags"] = [h.strip().lstrip("#") for h in hashtags_raw.split(",") if h.strip()]

# ============================================================
# 3단계 — 표지 이미지 생성
# ============================================================
st.header("3단계 — 표지 이미지 생성")

if not content:
    st.info("먼저 1~2단계를 완료하세요.")
else:
    concept = (
        content["cover"].get("image_concept", "").strip()
        or content["cover"].get("headline", "").replace("\n", " ")
    )
    st.caption(f"이미지 컨셉 (2단계의 cover.image_concept 사용, 비어 있으면 headline 대체): {concept}")

    IMAGE_PROVIDERS = {"GPT Image 2 (OpenAI)": "openai", "Doubao-Seedream (Volcengine Ark)": "seedream"}
    provider_label = st.selectbox("이미지 생성 API", list(IMAGE_PROVIDERS.keys()), key="cover_image_provider_label")
    image_provider = IMAGE_PROVIDERS[provider_label]
    if image_provider == "seedream" and not ARK_API_KEY:
        st.warning("ARK_API_KEY가 없습니다. 이 폴더의 .env 파일에 ARK_API_KEY=... 를 추가하세요.")

    if st.button("② 표지 이미지 생성", type="primary"):
        try:
            client = get_client()
            st.session_state.cover_concept = concept
            with st.spinner("표지 이미지 생성 중..."):
                path = generate_cover_image(client, concept, content_id_value, provider=image_provider)
            st.session_state.cover_image_path = path
            content["cover"]["image"] = path
            if path is None:
                st.warning("폴백: 단색 배경으로 진행됩니다.")
        except Exception as e:
            st.error(f"이미지 생성 실패: {e}")

    if st.session_state.cover_image_path:
        st.image(to_local_path(st.session_state.cover_image_path), width=320)
    elif st.session_state.cover_concept is not None:
        st.info("폴백: 단색 배경으로 진행됩니다.")

    extra_direction = st.text_input("추가 지시", key="cover_extra_direction")
    if st.button("재생성"):
        if not st.session_state.cover_concept:
            st.warning("먼저 '② 표지 이미지 생성'을 한 번 눌러주세요.")
        else:
            try:
                client = get_client()
                with st.spinner("이미지 재생성 중..."):
                    path = generate_cover_image(
                        client,
                        st.session_state.cover_concept,
                        content_id_value,
                        extra_direction=extra_direction,
                        provider=image_provider,
                    )
                st.session_state.cover_image_path = path
                content["cover"]["image"] = path
                if path is None:
                    st.warning("폴백: 단색 배경으로 진행됩니다.")
                else:
                    st.image(to_local_path(path), width=320)
            except Exception as e:
                st.error(f"이미지 재생성 실패: {e}")

# ============================================================
# 4단계 — 피드 생성 (캐러셀 4:5 + 스토리 9:16 정지 이미지)
# ============================================================
st.header("4단계 — 피드 생성")

if not content:
    st.info("먼저 1~2단계를 완료하세요.")
else:
    if st.button("③ 피드 생성", type="primary"):
        out_dir = OUT_ROOT / content_id_value
        out_dir.mkdir(parents=True, exist_ok=True)
        content_path = out_dir / "content.json"
        content_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")

        with st.spinner("렌더링 중... (PNG 생성)"):
            result = subprocess.run(
                [sys.executable, str(RENDER_PY), str(content_path), str(out_dir)],
                capture_output=True, text=True, encoding="utf-8",
            )

        if result.returncode == 0:
            st.session_state.feed_out_dir = out_dir
            st.session_state.reel_path = None  # 콘텐츠가 바뀌었으니 이전 릴스는 무효화
            st.success(f"피드 생성 완료 → {out_dir}")
        else:
            st.session_state.feed_out_dir = None
            st.error("피드 생성 실패")
            st.code(result.stderr or result.stdout, language="text")

    if st.session_state.feed_out_dir:
        feed_dir = Path(st.session_state.feed_out_dir)
        show_gallery(feed_dir / "carousel", "캐러셀 (4:5)")
        show_gallery(feed_dir / "story", "스토리·릴스 (9:16)")
        st.download_button(
            "📦 피드 다운로드 (zip)",
            data=zip_folder(feed_dir),
            file_name=f"{feed_dir.name}-feed.zip",
            mime="application/zip",
        )

# ============================================================
# 5단계 — 릴스 생성 (스토리 9:16 PNG(표지+본문+CTA) + 배경음악 → mp4)
# ============================================================
st.header("5단계 — 릴스 생성")

if not st.session_state.feed_out_dir:
    st.info("먼저 4단계에서 피드를 생성하세요 (스토리 이미지가 있어야 릴스를 만들 수 있습니다).")
else:
    feed_dir = Path(st.session_state.feed_out_dir)
    story_dir = feed_dir / "story"
    story_count = len(list(story_dir.glob("*.png"))) if story_dir.exists() else 0

    if story_count < 2:
        st.warning(f"스토리 이미지가 {story_count}장뿐입니다 (최소 2장 필요). 4단계를 다시 확인하세요.")
    else:
        st.caption("ffmpeg가 시스템 PATH에 설치되어 있어야 합니다 (`ffmpeg -version`으로 확인).")

        music_library = list_music_library()
        mode_options = ["🎲 music/ 폴더에서 랜덤 선택", "📁 music/ 폴더에서 직접 선택", "⬆️ 파일 업로드"]
        if not music_library:
            st.caption(f"`{MUSIC_DIR.name}/` 폴더에 mp3 등을 넣어두면 생성할 때마다 자동으로 무작위 선곡할 수 있습니다.")
            music_mode = mode_options[2]
        else:
            music_mode = st.radio(
                "배경음악", mode_options, index=0, key="reel_music_mode", horizontal=True
            )

        uploaded_music_file = None
        picked_music_path = None
        if music_mode == mode_options[0]:
            st.caption(f"`{MUSIC_DIR.name}/`에 {len(music_library)}곡 있음 — 생성 버튼을 누를 때마다 그중 하나를 무작위로 씁니다.")
        elif music_mode == mode_options[1]:
            picked_music_path = st.selectbox(
                "곡 선택", music_library, format_func=lambda p: p.name, key="reel_music_pick"
            )
        else:
            uploaded_music_file = st.file_uploader("배경음악 파일", type=["mp3", "m4a", "wav", "aac"], key="reel_music")

        with st.expander("릴스 타이밍 설정 (선택, 기본값 그대로 써도 됩니다)"):
            first_sec = st.number_input("첫 장 노출 시간(초)", min_value=0.5, value=3.0, step=0.5, key="reel_first")
            other_sec = st.number_input("나머지 장 노출 시간(초)", min_value=0.5, value=2.0, step=0.5, key="reel_other")
            transition_sec = st.number_input("전환(크로스페이드) 시간(초)", min_value=0.1, value=0.5, step=0.1, key="reel_transition")

        if st.button("④ 릴스 생성", type="primary"):
            music_path = None
            if music_mode == mode_options[0]:
                if not music_library:
                    st.warning(f"`{MUSIC_DIR.name}/` 폴더에 음악 파일이 없습니다.")
                else:
                    music_path = random.choice(music_library)
            elif music_mode == mode_options[1]:
                music_path = picked_music_path
            else:
                if uploaded_music_file is None:
                    st.warning("배경음악 파일을 먼저 업로드하세요.")
                else:
                    music_path = feed_dir / f"bgm_upload{Path(uploaded_music_file.name).suffix}"
                    music_path.write_bytes(uploaded_music_file.getvalue())

            if music_path is not None:
                reel_out_path = feed_dir / "reel.mp4"
                try:
                    with st.spinner(f"릴스 생성 중... (배경음악: {music_path.name}, ffmpeg 인코딩이라 시간이 걸릴 수 있습니다)"):
                        build_reel(story_dir, music_path, reel_out_path, first_sec, other_sec, transition_sec)
                    st.session_state.reel_path = reel_out_path
                    st.success(f"릴스 생성 완료 → {reel_out_path} (배경음악: {music_path.name})")
                except FileNotFoundError:
                    st.error("ffmpeg를 찾을 수 없습니다. PATH에 설치되어 있는지 확인하세요.")
                except (Exception, SystemExit) as e:
                    st.error(f"릴스 생성 실패: {e}")

    if st.session_state.reel_path and Path(st.session_state.reel_path).exists():
        reel_path = Path(st.session_state.reel_path)
        st.video(str(reel_path))
        st.download_button(
            "🎬 릴스 다운로드 (mp4)",
            data=reel_path.read_bytes(),
            file_name=reel_path.name,
            mime="video/mp4",
        )
