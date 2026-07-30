#!/usr/bin/env python3
"""릴스 제작. 딥리서치 결과 → 대본(대사+장면) 생성 → 음성·속도·감정 설정 → 장면 이미지 준비 →
타입캐스트 TTS → 릴스 조립까지, 카드뉴스 제작과 같은 파일 기반 독립 실행 패턴으로 만든다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import subprocess

import streamlit as st

from pipeline_common import (
    HERE,
    IMAGE_PROMPT_TEMPLATE,
    IMAGE_PROVIDERS,
    MUSIC_DIR,
    MUSIC_EXTS,
    REEL_AUDIO_DIR,
    REEL_DEFAULT_VOICE_ID,
    REEL_EMOTION_PRESETS,
    REEL_IMAGES_DIR,
    REEL_OUT_ROOT,
    REEL_PHOTOS_DIR,
    REEL_SCRIPT_DIR,
    RESEARCH_DIR,
    build_reel_script_prompt,
    generate_scene_image_raw,
    get_client,
    load_reel_photo_index,
    list_research_notes,
    run_reel_script_prompt,
    show_json_dialog,
    synthesize_reel_line,
)
from pipeline_state import save_state

st.title("릴스 제작")

# ============================================================
# 딥리서치 결과 선택 — 카드뉴스 제작과 동일한 파일 기반 선택 패턴.
# ============================================================
st.subheader("딥리서치 결과 선택")

notes = list_research_notes()


def _note_label(p: Path) -> str:
    try:
        first_line = next((ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()), "")
    except Exception:
        first_line = ""
    preview = (first_line[:50] + "…") if len(first_line) > 50 else first_line
    return f"{p.stem} · {preview}" if preview else p.stem


if not notes:
    st.info("저장된 딥리서치 결과가 없습니다. 딥리서치 페이지에서 먼저 실행하세요.")
else:
    pick_row = st.columns([3, 1], vertical_alignment="bottom")
    with pick_row[0]:
        picked_note = st.selectbox("결과 파일", notes, format_func=_note_label, key="reel_note_pick")
    with pick_row[1]:
        if st.button("선택", type="primary", key="reel_note_select"):
            st.session_state["reel_id"] = picked_note.stem
            st.rerun()

content_id = st.session_state.get("reel_id")
research_note = None
if content_id:
    note_path = RESEARCH_DIR / f"{content_id}.md"
    if note_path.exists():
        research_note = note_path.read_text(encoding="utf-8")
        st.caption(f"선택된 리서치: `{content_id}`")
    else:
        st.error(f"{note_path.name} 파일이 없습니다 — 위에서 다시 선택하세요.")

st.divider()

# ============================================================
# 대본 생성 — 조사 노트 + 사진 라이브러리(assets/reel_photos/index.json, 별도 관리) + 대본
# 예시(data/record-sample)를 참고해 줄 단위(화자·대사·장면) JSON 대본을 만든다.
# 사진 라이브러리 자체의 추가/편집/삭제는 이 페이지가 아니라 별도로 관리한다(2026-07-30 사용자
# 결정) — 여기서는 읽기만 한다.
# ============================================================
st.subheader("대본 생성")

if not content_id or research_note is None:
    st.info("먼저 위에서 딥리서치 결과를 선택하세요.")
else:
    direction = st.text_input(
        "대본 방향성/의견 (선택)",
        key="reel_direction",
        placeholder="비워두면 GPT가 소재에 맞는 논조를 알아서 정합니다 — 예: 걱정보다 안심시키는 톤으로, 정부 대응을 비판적으로",
    )
    st.caption("사실(조사 노트)은 그대로 두고, 여기 입력한 방향성만큼 관점·논조를 반영해 문장을 새로 씁니다.")

    prompt_key = f"reel_script_prompt::{content_id}"
    ver_key = f"{prompt_key}::ver"
    version = st.session_state.get(ver_key, 0)
    photo_library = load_reel_photo_index()  # 방금 추가/삭제됐을 수 있으니 다시 읽는다

    def _rebuild_script_prompt():
        _, user_prompt = build_reel_script_prompt(content_id, research_note, photo_library, direction=direction)
        st.session_state[prompt_key] = user_prompt

    if prompt_key not in st.session_state:
        _rebuild_script_prompt()

    edited_script_prompt = st.text_area(
        "대본 생성 프롬프트 (수정 가능)",
        value=st.session_state[prompt_key],
        height=280,
        key=f"{prompt_key}::edit::{version}",
    )

    btn_row = st.columns([1, 1])
    with btn_row[0]:
        if st.button("프롬프트 새로고침 (방향성·사진 라이브러리 반영)", key="reel_script_prompt_refresh"):
            _rebuild_script_prompt()
            st.session_state[ver_key] = version + 1
            st.rerun()
    with btn_row[1]:
        script_run_clicked = st.button("대본 생성", type="primary", key="reel_script_run")

    if script_run_clicked:
        try:
            client = get_client()
            system_prompt, _ = build_reel_script_prompt(content_id, research_note, photo_library, direction=direction)
            with st.spinner("대본 생성 중..."):
                script, raw = run_reel_script_prompt(client, system_prompt, edited_script_prompt, content_id)
            if script is None:
                st.error("모델 출력이 JSON으로 파싱되지 않았습니다 — 아래 원본을 확인하세요.")
                with st.expander("모델 원본 출력"):
                    st.code(raw, language=None)
            else:
                script_path = REEL_SCRIPT_DIR / f"{content_id}.json"
                script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
                save_state(content_id, reel_script_path=str(script_path))
                st.session_state[f"reel_script::{content_id}"] = script
                st.success(f"생성 완료 — {script_path.name} 저장됨 ({len(script.get('lines', []))}줄). 아래에서 선택하세요.")
        except Exception as e:
            st.error(f"대본 생성 실패: {e}")

st.divider()

# ============================================================
# 대본 선택 — 파일 기반: data/reel_script/*.json 중에서 고른다.
# ============================================================
st.subheader("대본 선택")

script_files = sorted(REEL_SCRIPT_DIR.glob("*.json"), reverse=True)
picked_script = None
picked_script_path = None


def _script_label(p: Path) -> str:
    try:
        lines = json.loads(p.read_text(encoding="utf-8")).get("lines", [])
        return f"{p.stem} · {len(lines)}줄"
    except Exception:
        return p.stem


if not script_files:
    st.info("저장된 대본이 없습니다 — 위에서 먼저 생성하세요.")
else:
    srow = st.columns([3, 1, 1], vertical_alignment="bottom")
    with srow[0]:
        picked_script_path = st.selectbox(
            "대본 파일", script_files, format_func=_script_label, key="reel_script_pick"
        )
    sk = f"reel_script::{picked_script_path.stem}"
    if st.session_state.get(sk) is None:
        try:
            st.session_state[sk] = json.loads(picked_script_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            st.error(f"{picked_script_path.name} 파싱 실패: {e}")
    with srow[1]:
        if st.button("보기/편집", key="reel_script_edit_btn", disabled=st.session_state.get(sk) is None):
            show_json_dialog(st.session_state[sk], sk)
    with srow[2]:
        if st.button("선택", type="primary", key="reel_script_select", disabled=st.session_state.get(sk) is None):
            st.session_state["reel_confirmed_script"] = picked_script_path.stem
            st.rerun()

    picked_script = st.session_state.get(sk)
    if picked_script:
        serialized = json.dumps(picked_script, ensure_ascii=False, indent=2)
        if picked_script_path.read_text(encoding="utf-8") != serialized:
            picked_script_path.write_text(serialized, encoding="utf-8")
            save_state(picked_script_path.stem, reel_script_path=str(picked_script_path))

confirmed_script_id = st.session_state.get("reel_confirmed_script")
script_confirmed = (
    picked_script is not None
    and picked_script_path is not None
    and confirmed_script_id == picked_script_path.stem
)

st.divider()

# ============================================================
# 음성·속도·감정 설정 — 목소리는 우선 "민욱"으로 고정한다(여러 목소리 중 고르는 셀렉트박스는
# 추후에 붙인다, 2026-07-30 사용자 결정). 속도(audio_tempo)와 감정(자동/직접 지정)은 여기서
# 조절해서 TTS 생성에 그대로 반영한다.
# ============================================================
st.subheader("음성·속도·감정 설정")

if not script_confirmed:
    st.info("먼저 위에서 대본을 고르고 「선택」을 누르세요.")
    tts_settings = None
else:
    st.caption("목소리: **민욱** (고정 — 추후 여러 목소리 중 선택할 수 있게 바꿀 예정)")

    tempo = st.slider("말 속도", 0.5, 2.0, 1.0, step=0.05, key="reel_tts_tempo")

    emotion_mode = st.radio(
        "감정",
        ["자동 (앞뒤 문맥에 맞춰 AI가 결정)", "직접 지정"],
        key="reel_tts_emotion_mode",
        horizontal=True,
    )
    if emotion_mode == "직접 지정":
        e_row = st.columns([2, 1])
        with e_row[0]:
            emotion_preset = st.selectbox("감정 종류", REEL_EMOTION_PRESETS, key="reel_tts_emotion_preset")
        with e_row[1]:
            emotion_intensity = st.slider("강도", 0.0, 2.0, 1.0, step=0.1, key="reel_tts_emotion_intensity")
        tts_settings = {
            "audio_tempo": tempo, "emotion_type": "preset",
            "emotion_preset": emotion_preset, "emotion_intensity": emotion_intensity,
        }
    else:
        tts_settings = {"audio_tempo": tempo, "emotion_type": "smart"}

st.divider()

# ============================================================
# 장면 이미지 준비 — 대본의 장면(scenes[])마다 기존 사진을 재사용하거나, 없으면 새로 생성한다.
# 장면 하나를 여러 줄이 공유하므로(2026-07-30 스키마 변경, 이미지 수·비용을 줄이고 카메라
# 움직임으로 다이나믹하게 만들기 위함) 줄이 아니라 장면 단위로 이미지를 준비한다.
# 결과(resolved_image_path)는 대본 JSON 파일에 그대로 반영해 릴스 조립 단계가 읽게 한다.
# ============================================================
st.subheader("장면 이미지 준비")

if not script_confirmed:
    st.info("먼저 위에서 대본을 고르고 「선택」을 누르세요.")
else:
    sid = confirmed_script_id
    scenes = picked_script.get("scenes", [])
    lines = picked_script.get("lines", [])
    photo_library = load_reel_photo_index()
    photo_files = {e["file"] for e in photo_library}
    changed = False

    for si, scene in enumerate(scenes):
        scene_lines = [l.get("text", "") for l in lines if l.get("scene_index") == si]
        motion = scene.get("motion", "static")
        with st.expander(f"장면 {si + 1}. {scene.get('visual_concept', '')[:40]} (motion: {motion})"):
            st.caption("이 장면이 쓰이는 대사: " + " / ".join(scene_lines) if scene_lines else "이 장면을 쓰는 줄이 없습니다.")

            resolved = scene.get("resolved_image_path")
            if not resolved and scene.get("image_source") == "existing" and scene.get("image_file") in photo_files:
                resolved = str((REEL_PHOTOS_DIR / scene["image_file"]).resolve())
                scene["resolved_image_path"] = resolved
                changed = True

            if resolved and Path(resolved).exists():
                st.image(resolved, width=200)
            else:
                st.caption("아직 준비된 이미지가 없습니다.")

            prompt_key = f"reel_scene_prompt::{sid}::{si}"
            if prompt_key not in st.session_state:
                st.session_state[prompt_key] = IMAGE_PROMPT_TEMPLATE.replace(
                    "{concept}", scene.get("visual_concept", "")
                )
            edited_scene_prompt = st.text_area(
                "이미지 생성 프롬프트", value=st.session_state[prompt_key], height=150, key=f"{prompt_key}::edit"
            )
            gen_row = st.columns([2, 1, 1])
            with gen_row[0]:
                provider_label = st.selectbox(
                    "생성 API", list(IMAGE_PROVIDERS), key=f"reel_scene_provider::{sid}::{si}"
                )
            with gen_row[1]:
                quality = st.selectbox(
                    "품질", ["high", "medium", "low"], key=f"reel_scene_quality::{sid}::{si}",
                    disabled=IMAGE_PROVIDERS[provider_label] == "seedream",
                )
            with gen_row[2]:
                if st.button("생성", key=f"reel_scene_gen::{sid}::{si}"):
                    try:
                        client = get_client()
                        with st.spinner("이미지 생성 중..."):
                            uri = generate_scene_image_raw(
                                client, edited_scene_prompt, sid, si, quality,
                                provider=IMAGE_PROVIDERS[provider_label],
                            )
                        if uri:
                            local = Path(REEL_IMAGES_DIR / sid / f"scene_{si:02d}.png").resolve()
                            scene["resolved_image_path"] = str(local)
                            scene["image_source"] = "generate"
                            picked_script_path.write_text(
                                json.dumps(picked_script, ensure_ascii=False, indent=2), encoding="utf-8"
                            )
                            st.success("생성 완료")
                            st.rerun()
                    except Exception as e:
                        st.error(f"이미지 생성 실패: {e}")

    if changed:
        picked_script_path.write_text(json.dumps(picked_script, ensure_ascii=False, indent=2), encoding="utf-8")

    ready_count = sum(
        1 for scene in scenes
        if scene.get("resolved_image_path") and Path(scene["resolved_image_path"]).exists()
    )
    st.caption(f"준비된 장면 이미지: {ready_count}/{len(scenes)}")

st.divider()

# ============================================================
# TTS 생성 — 타입캐스트 API로 줄마다 오디오를 만든다. emotion_type=smart로 앞/뒤 줄을
# 문맥으로 넘겨 감정을 자동으로 바꾼다(대본 예시들의 리듬감 재현).
# ============================================================
st.subheader("TTS 생성 (타입캐스트)")

if not script_confirmed:
    st.info("먼저 위에서 대본을 고르고 「선택」을 누르세요.")
else:
    sid = confirmed_script_id
    lines = picked_script.get("lines", [])
    audio_dir = REEL_AUDIO_DIR / sid

    if st.button("전체 줄 TTS 생성", type="primary", key="reel_tts_all"):
        with st.spinner(f"{len(lines)}줄 합성 중..."):
            ok_count = 0
            for idx, line in enumerate(lines, start=1):
                out_path = audio_dir / f"line_{idx:02d}.mp3"
                prev_text = lines[idx - 2]["text"] if idx >= 2 else ""
                next_text = lines[idx]["text"] if idx < len(lines) else ""
                if synthesize_reel_line(
                    text=line["text"], voice_id=REEL_DEFAULT_VOICE_ID,
                    out_path=out_path, previous_text=prev_text, next_text=next_text,
                    **tts_settings,
                ):
                    ok_count += 1
        save_state(sid, reel_audio_dir=str(audio_dir))
        st.success(f"{ok_count}/{len(lines)}줄 생성 완료")

    for idx, line in enumerate(lines, start=1):
        audio_path = audio_dir / f"line_{idx:02d}.mp3"
        row = st.columns([4, 1])
        row[0].caption(f"{idx}. [{line.get('speaker', '나레이션')}] {line.get('text', '')[:40]}")
        if audio_path.exists():
            row[0].audio(str(audio_path))
        if row[1].button("다시 생성", key=f"reel_tts_one::{sid}::{idx}"):
            prev_text = lines[idx - 2]["text"] if idx >= 2 else ""
            next_text = lines[idx]["text"] if idx < len(lines) else ""
            with st.spinner("합성 중..."):
                synthesize_reel_line(
                    text=line["text"], voice_id=REEL_DEFAULT_VOICE_ID,
                    out_path=audio_path, previous_text=prev_text, next_text=next_text,
                    **tts_settings,
                )
            st.rerun()

st.divider()

# ============================================================
# 릴스 조립 — 장면 이미지 + 줄별 오디오를 Render_reel_narrated.py(ffmpeg)로 합친다.
# ============================================================
st.subheader("릴스 조립")

if not script_confirmed:
    st.info("먼저 위에서 대본을 고르고 「선택」을 누르세요.")
else:
    sid = confirmed_script_id
    lines = picked_script.get("lines", [])
    scenes = picked_script.get("scenes", [])
    audio_dir = REEL_AUDIO_DIR / sid
    out_path = REEL_OUT_ROOT / sid / "reel.mp4"

    images_ready = bool(scenes) and all(
        scene.get("resolved_image_path") and Path(scene["resolved_image_path"]).exists()
        for scene in scenes
    )
    audio_ready = all((audio_dir / f"line_{i:02d}.mp3").exists() for i in range(1, len(lines) + 1))

    if not images_ready:
        st.info("먼저 모든 장면의 이미지를 준비하세요.")
    elif not audio_ready:
        st.info("먼저 모든 줄의 TTS 오디오를 생성하세요.")
    else:
        music_files = sorted(f for ext in MUSIC_EXTS for f in MUSIC_DIR.glob(ext))
        bgm_choice = st.selectbox(
            "배경음악 (선택)", ["(없음)"] + [f.name for f in music_files], key="reel_bgm_pick"
        )
        bgm_volume = st.slider("배경음악 볼륨", 0.0, 1.0, 0.15, key="reel_bgm_volume")

        if st.button("릴스 조립", type="primary", key="reel_assemble_btn"):
            script_path = REEL_SCRIPT_DIR / f"{sid}.json"
            cmd = [
                sys.executable, str(HERE / "Render_reel_narrated.py"),
                str(script_path), str(audio_dir), str(out_path),
            ]
            if bgm_choice != "(없음)":
                cmd += ["--bgm", str(MUSIC_DIR / bgm_choice), "--bgm-volume", str(bgm_volume)]
            with st.spinner("릴스 조립 중..."):
                result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                st.error("조립 실패")
                st.code(result.stderr or result.stdout)
            else:
                save_state(sid, reel_path=str(out_path))
                st.success(f"조립 완료 → {out_path}")

        if out_path.exists():
            st.video(str(out_path))
