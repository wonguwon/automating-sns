"""워커 프로세스 진입점.

Spring Boot(backend-spring)가 MySQL auto_sns.jobs 테이블에 PENDING 작업을 기록하면,
이 워커가 polling으로 가져가 services/* 함수를 호출하고 결과를 다시 기록한다
(2026-07-31, 4단계 첫 슬라이스 — 나중에 Redis/RabbitMQ 큐나 FastAPI 상시 서비스로 바꿀 수
있도록 poll 방식은 이 파일 안에서만 감싸고, services 계층은 이 방식을 모른다).

지금은 RSS_COLLECT 타입만 실제로 연결했다(services.rss.collect_feed_items). 나머지
JobType은 해당 services 파일이 실제 구현되는 대로 DISPATCH에 추가한다 — 그 전까지는
NotImplementedError로 FAILED 처리된다(status 흐름 자체는 모든 타입에 대해 동작함).

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

import pymysql

from .core.db import get_connection
from .services import rss

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


DISPATCH = {
    "RSS_COLLECT": _dispatch_rss_collect,
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
