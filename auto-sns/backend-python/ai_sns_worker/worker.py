"""워커 프로세스 진입점.

Spring Boot(backend-spring)가 MySQL auto_sns.jobs 테이블에 PENDING 작업을 기록하면,
이 워커가 polling으로 가져가 services/* 함수를 호출하고 결과를 다시 기록한다
(2026-07-31, 4단계 첫 슬라이스 — 나중에 Redis/RabbitMQ 큐나 FastAPI 상시 서비스로 바꿀 수
있도록 poll 방식은 이 파일 안에서만 감싸고, services 계층은 이 방식을 모른다).

`JobType.java`의 10개 타입 전부 연결했다(2026-08-03) — RSS_COLLECT는 4단계에서, 나머지
9개는 실제 GPT/이미지/TTS API 호출·Playwright/ffmpeg 실행까지 스모크 테스트로 검증한 뒤
연결했다(wiki/decisions.md 참고). COVER_IMAGE_GENERATE/SCENE_IMAGE_GENERATE는 이미지 생성
직후 각각 `cardnews.set_cover_image`/`reel.set_scene_resolved_image`로 content.json/대본에
자동으로 반영한다 — 스모크 테스트 중 이 연결이 빠져 있으면 렌더가 이미지 없이(단색 폴백)
나온다는 걸 실제로 확인했다.

jobs 테이블 구조는 backend-spring의 Job 엔티티와 공유한다(wiki/decisions.md 참고):
id, project_id, type, status(PENDING/RUNNING/DONE/FAILED), input_json, result_json,
error_message, created_at, updated_at.
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

import pymysql

from .core.db import get_connection
from .services import cardnews, image, reel, render, research, rss, tts

POLL_INTERVAL_SECONDS = 2

logger = logging.getLogger(__name__)


@dataclass
class JobRow:
    id: int
    type: str
    input_json: str


def _dispatch_rss_collect(input_json: str) -> str:
    """input_json 예: {"group_id": "뉴스", "hours": 24}"""
    payload = json.loads(input_json)
    request = rss.CollectFeedItemsRequest(group_id=payload["group_id"], hours=payload.get("hours", 24))
    result = rss.collect_feed_items(request)
    return json.dumps(
        {
            "group_id": result.group_id,
            "saved_path": str(result.saved_path),
            "item_count": result.item_count,
        },
        ensure_ascii=False,
    )


def _dispatch_candidate_select(input_json: str) -> str:
    """input_json 예: {"group_id": "뉴스", "items": [...], "persona": null, "rules": null}.
    실제 GPT 호출(비용 발생)."""
    payload = json.loads(input_json)
    request = research.SelectCandidatesRequest(
        group_id=payload["group_id"], items=payload["items"],
        persona=payload.get("persona"), rules=payload.get("rules"),
    )
    result = research.select_candidates(request)
    return json.dumps(
        {"group_id": result.group_id, "saved_path": str(result.saved_path), "candidate_count": len(result.candidates)},
        ensure_ascii=False,
    )


def _dispatch_deep_research(input_json: str) -> str:
    """input_json 예: {"content_id": "20260803-01", "candidate": {...}}. 실제 GPT 호출(비용 발생)."""
    payload = json.loads(input_json)
    request = research.RunDeepResearchRequest(content_id=payload["content_id"], candidate=payload["candidate"])
    result = research.run_deep_research(request)
    return json.dumps(
        {"content_id": result.content_id, "note_path": str(result.note_path), "fetched_any_article": result.fetched_any_article},
        ensure_ascii=False,
    )


def _dispatch_cardnews_generate(input_json: str) -> str:
    """input_json 예: {"content_id": ..., "template_name": "기본", "research_note": ...,
    "source_urls": [...], "brand": "", "handle": "", "audience": "", "direction": ""}.
    실제 GPT 호출(비용 발생)."""
    payload = json.loads(input_json)
    request = cardnews.GenerateContentJsonRequest(
        content_id=payload["content_id"], template_name=payload["template_name"],
        research_note=payload["research_note"], source_urls=payload.get("source_urls", []),
        brand=payload.get("brand", ""), handle=payload.get("handle", ""),
        audience=payload.get("audience", ""), direction=payload.get("direction", ""),
    )
    result = cardnews.generate_content_json(request)
    return json.dumps(
        {
            "content_id": result.content_id,
            "parsed": result.content is not None,
            "saved_path": str(result.saved_path) if result.saved_path else None,
        },
        ensure_ascii=False,
    )


def _dispatch_cover_image_generate(input_json: str) -> str:
    """input_json 예: {"content_id": ..., "concept": ..., "extra_direction": "",
    "provider": "openai", "quality": "high"}. 실제 이미지 생성 API 호출(비용 발생).
    성공하면 cardnews.set_cover_image로 content.json의 cover.image에도 반영한다."""
    payload = json.loads(input_json)
    request = image.GenerateCoverImageRequest(
        content_id=payload["content_id"], concept=payload["concept"],
        extra_direction=payload.get("extra_direction", ""),
        provider=payload.get("provider", "openai"), quality=payload.get("quality", "high"),
    )
    result = image.generate_cover_image(request)
    if result.image_uri:
        cardnews.set_cover_image(
            cardnews.SetCoverImageRequest(content_id=result.content_id, image_uri=result.image_uri)
        )
    return json.dumps(
        {"content_id": result.content_id, "image_uri": result.image_uri, "error": result.error},
        ensure_ascii=False,
    )


def _dispatch_cardnews_render(input_json: str) -> str:
    """input_json 예: {"content_id": ..., "template_name": "기본"}.
    Playwright 브라우저 실행(로컬 도구, 비용 없음)."""
    payload = json.loads(input_json)
    request = render.RenderCardnewsRequest(content_id=payload["content_id"], template_name=payload["template_name"])
    result = render.render_cardnews(request)
    return json.dumps(
        {"content_id": result.content_id, "out_dir": str(result.out_dir), "slide_count": result.slide_count},
        ensure_ascii=False,
    )


def _dispatch_reel_script_generate(input_json: str) -> str:
    """input_json 예: {"content_id": ..., "research_note": ..., "photo_library": [...], "direction": ""}.
    실제 GPT 호출(비용 발생)."""
    payload = json.loads(input_json)
    request = reel.GenerateReelScriptRequest(
        content_id=payload["content_id"], research_note=payload["research_note"],
        photo_library=payload.get("photo_library", []), direction=payload.get("direction", ""),
    )
    result = reel.generate_reel_script(request)
    return json.dumps(
        {
            "content_id": result.content_id,
            "parsed": result.script is not None,
            "saved_path": str(result.saved_path) if result.saved_path else None,
        },
        ensure_ascii=False,
    )


def _dispatch_scene_image_generate(input_json: str) -> str:
    """input_json 예: {"content_id": ..., "scene_index": 0, "concept": ...,
    "provider": "openai", "quality": "high"}. 실제 이미지 생성 API 호출(비용 발생).
    성공하면 reel.set_scene_resolved_image로 대본의 resolved_image_path에도 반영한다."""
    payload = json.loads(input_json)
    request = image.GenerateSceneImageRequest(
        content_id=payload["content_id"], scene_index=payload["scene_index"], concept=payload["concept"],
        provider=payload.get("provider", "openai"), quality=payload.get("quality", "high"),
    )
    result = image.generate_scene_image(request)
    if result.image_uri:
        reel.set_scene_resolved_image(
            reel.SetSceneResolvedImageRequest(
                content_id=result.content_id, scene_index=result.scene_index, image_path=str(result.image_path)
            )
        )
    return json.dumps(
        {
            "content_id": result.content_id,
            "scene_index": result.scene_index,
            "image_uri": result.image_uri,
            "error": result.error,
        },
        ensure_ascii=False,
    )


def _dispatch_tts_synthesize(input_json: str) -> str:
    """input_json 예: {"content_id": ..., "line_no": 1, "text": ..., "voice_id": null,
    "previous_text": "", "next_text": "", "emotion_type": "smart", ...}. 넘기지 않은 선택
    필드는 SynthesizeLineRequest의 기본값을 그대로 쓴다. 실제 네트워크 호출(비용 없음)."""
    payload = json.loads(input_json)
    kwargs = {"content_id": payload["content_id"], "line_no": payload["line_no"], "text": payload["text"]}
    for field in (
        "voice_id", "previous_text", "next_text", "model", "audio_format",
        "audio_tempo", "emotion_type", "emotion_preset", "emotion_intensity",
    ):
        if field in payload:
            kwargs[field] = payload[field]
    result = tts.synthesize_line(tts.SynthesizeLineRequest(**kwargs))
    return json.dumps(
        {"content_id": result.content_id, "line_no": result.line_no, "audio_path": str(result.audio_path)},
        ensure_ascii=False,
    )


def _dispatch_reel_render(input_json: str) -> str:
    """input_json 예: {"content_id": ..., "bgm_path": null, "bgm_volume": 0.15}.
    ffmpeg 실행(로컬 도구, 비용 없음)."""
    payload = json.loads(input_json)
    bgm_path = payload.get("bgm_path")
    request = render.RenderReelRequest(
        content_id=payload["content_id"],
        bgm_path=Path(bgm_path) if bgm_path else None,
        bgm_volume=payload.get("bgm_volume", 0.15),
    )
    result = render.render_reel(request)
    return json.dumps(
        {"content_id": result.content_id, "out_path": str(result.out_path), "total_duration": result.total_duration},
        ensure_ascii=False,
    )


DISPATCH = {
    "RSS_COLLECT": _dispatch_rss_collect,
    "CANDIDATE_SELECT": _dispatch_candidate_select,
    "DEEP_RESEARCH": _dispatch_deep_research,
    "CARDNEWS_GENERATE": _dispatch_cardnews_generate,
    "COVER_IMAGE_GENERATE": _dispatch_cover_image_generate,
    "CARDNEWS_RENDER": _dispatch_cardnews_render,
    "REEL_SCRIPT_GENERATE": _dispatch_reel_script_generate,
    "SCENE_IMAGE_GENERATE": _dispatch_scene_image_generate,
    "TTS_SYNTHESIZE": _dispatch_tts_synthesize,
    "REEL_RENDER": _dispatch_reel_render,
}


def _fetch_next_pending(conn) -> JobRow | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, type, input_json FROM jobs WHERE status = 'PENDING' "
            "ORDER BY created_at ASC LIMIT 1"
        )
        row = cur.fetchone()
    if row is None:
        return None
    return JobRow(id=row["id"], type=row["type"], input_json=row["input_json"])


def _mark_running(conn, job_id: int) -> bool:
    """PENDING인 job만 RUNNING으로 바꾼다 — 여러 워커가 동시에 떠도 같은 job을 두 번
    집지 않도록 WHERE status='PENDING' 조건으로 낙관적 잠금을 건다."""
    with conn.cursor() as cur:
        affected = cur.execute(
            "UPDATE jobs SET status = 'RUNNING' WHERE id = %s AND status = 'PENDING'",
            (job_id,),
        )
    return affected == 1


def _mark_done(conn, job_id: int, result_json: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = 'DONE', result_json = %s WHERE id = %s",
            (result_json, job_id),
        )


def _mark_failed(conn, job_id: int, error_message: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = 'FAILED', error_message = %s WHERE id = %s",
            (error_message[:2000], job_id),
        )


def poll_once() -> bool:
    """대기 중인 job을 하나 집어 처리한다. 처리한 job이 있으면 True, 없으면 False."""
    conn = get_connection()
    try:
        job = _fetch_next_pending(conn)
        if job is None:
            return False
        if not _mark_running(conn, job.id):
            return False  # 다른 워커가 먼저 집어감

        handler = DISPATCH.get(job.type)
        try:
            if handler is None:
                raise NotImplementedError(f"아직 연결되지 않은 job 타입: {job.type}")
            result_json = handler(job.input_json)
        except Exception as e:
            logger.exception("job %s 처리 실패(type=%s)", job.id, job.type)
            _mark_failed(conn, job.id, f"{e}\n{traceback.format_exc()}")
        else:
            _mark_done(conn, job.id, result_json)
            logger.info("job %s 완료(type=%s)", job.id, job.type)
        return True
    finally:
        conn.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("워커 시작 — jobs 테이블 polling (%s초 간격)", POLL_INTERVAL_SECONDS)
    while True:
        try:
            processed = poll_once()
        except pymysql.MySQLError:
            logger.exception("DB 연결 오류")
            processed = False
        if not processed:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
