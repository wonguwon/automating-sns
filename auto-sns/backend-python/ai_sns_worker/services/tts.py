"""타입캐스트(Typecast) TTS 음성 목록 조회 및 합성.

원칙:
- 이 계층은 Streamlit을 import하지 않는다.
- 이 계층은 DB를 직접 알지 않는다 (호출부가 영속화를 책임진다).
- 함수는 input DTO를 받고 result DTO를 반환한다.
- 실패는 예외로 알린다 — legacy는 TTS 실패를 "화면에 에러를 보여주고 False/None 반환"하는
  소프트 실패로 다뤘지만(사용자가 재시도할 수 있는 UI), 여기서는 하드 예외로 바꿨다: 표지
  이미지와 달리 TTS 오디오가 없으면 릴스 조립(services/render.py)이 어차피 이어질 수 없어
  소프트 실패가 도움이 되지 않기 때문이다(2026-08-03).
  API 키가 없거나(설정 문제) 실제 호출이 실패하면(네트워크/응답 문제) 모두 예외를 던진다.
  실제 네트워크 호출(비용은 없지만 외부 API 호출)이 필요한 함수들이라, 실제 실행 전에는
  반드시 사용자 확인을 받는다(2026-08-03, `wiki/decisions.md` 참고).

legacy 대응: legacy/pipeline_common.py
(list_typecast_voices, synthesize_reel_line, REEL_DEFAULT_VOICE_ID, REEL_EMOTION_PRESETS)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import requests

from ..core.config import load_api_keys
from ..core.paths import REEL_AUDIO_DIR
from . import pipeline

TYPECAST_BASE_URL = "https://api.typecast.ai"

# 목소리는 우선 "민욱"(Minuk, 남성/중년, ssfm-v30 감정 7종 전부 지원)으로 고정한다(legacy 결정).
REEL_DEFAULT_VOICE_ID = "tc_68f0727fd62a5934102f7ec0"
REEL_EMOTION_PRESETS = ["normal", "happy", "sad", "angry", "whisper", "toneup", "tonedown"]


def _require_typecast_key() -> str:
    keys = load_api_keys()
    if not keys.typecast:
        raise ValueError("TYPECAST_API_KEY가 없습니다. backend-python/.env에 TYPECAST_API_KEY=...를 추가하세요.")
    return keys.typecast


@dataclass
class ListVoicesResult:
    voices: list[dict] = field(default_factory=list)


def list_voices() -> ListVoicesResult:
    """GET /v2/voices로 사용 가능한 음성 목록을 조회한다.
    legacy: pipeline_common.list_typecast_voices"""
    api_key = _require_typecast_key()
    resp = requests.get(f"{TYPECAST_BASE_URL}/v2/voices", headers={"X-API-KEY": api_key}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    voices = data if isinstance(data, list) else (data.get("voices") or data.get("data") or [])
    return ListVoicesResult(voices=voices)


@dataclass
class SynthesizeLineRequest:
    content_id: str
    line_no: int
    text: str
    voice_id: str = REEL_DEFAULT_VOICE_ID
    previous_text: str = ""
    next_text: str = ""
    model: str = "ssfm-v30"
    audio_format: str = "mp3"
    audio_tempo: float = 1.0
    emotion_type: str = "smart"
    emotion_preset: str = "normal"
    emotion_intensity: float = 1.0


@dataclass
class SynthesizeLineResult:
    content_id: str
    line_no: int
    audio_path: Path


def synthesize_line(request: SynthesizeLineRequest) -> SynthesizeLineResult:
    """대본 한 줄을 타입캐스트 TTS로 합성해 저장한다.

    emotion_type: "smart"(문맥 기반 자동 — previous_text/next_text로 감정을 정함) 또는
    "preset"(emotion_preset/emotion_intensity로 감정을 직접 고정).
    legacy: pipeline_common.synthesize_reel_line"""
    api_key = _require_typecast_key()

    if request.emotion_type == "preset":
        prompt = {
            "emotion_type": "preset",
            "emotion_preset": request.emotion_preset,
            "emotion_intensity": request.emotion_intensity,
        }
    else:
        prompt = {
            "emotion_type": "smart",
            "previous_text": request.previous_text,
            "next_text": request.next_text,
        }

    body = {
        "voice_id": request.voice_id,
        "text": request.text,
        "model": request.model,
        "prompt": prompt,
        "output": {"audio_format": request.audio_format, "audio_tempo": request.audio_tempo},
    }
    resp = requests.post(
        f"{TYPECAST_BASE_URL}/v1/text-to-speech",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"TTS 실패({resp.status_code}): {resp.text[:300]}")

    out_dir = REEL_AUDIO_DIR / request.content_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"line_{request.line_no:02d}.{request.audio_format}"
    out_path.write_bytes(resp.content)

    pipeline.save_pipeline_state(
        pipeline.SavePipelineStateRequest(content_id=request.content_id, reel_audio_dir=str(out_dir))
    )

    return SynthesizeLineResult(content_id=request.content_id, line_no=request.line_no, audio_path=out_path)
