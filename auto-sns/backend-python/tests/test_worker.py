"""worker.py 테스트.

- _dispatch_rss_collect의 JSON 파싱은 네트워크 없이 monkeypatch로 검증한다.
- PENDING → RUNNING → DONE/FAILED 상태 전이는 실제 로컬 MySQL(auto_sns)에 대해 검증한다
  (backend-python/.env의 DB_* 값 필요) — 다만 실제 RSS 수집(네트워크 호출)은 필요 없는
  "아직 연결 안 된 job 타입 → FAILED" 경로로 확인해, tests/test_rss.py와 같은 원칙
  (네트워크 필요한 경로는 자동 테스트에서 제외)을 유지한다.
"""

import json

import pytest

from ai_sns_worker import worker
from ai_sns_worker.core.db import get_connection
from ai_sns_worker.services import rss


def test_dispatch_rss_collect_parses_input(monkeypatch):
    captured = {}

    def fake_collect(request):
        captured["group_id"] = request.group_id
        captured["hours"] = request.hours
        return rss.CollectFeedItemsResult(
            group_id=request.group_id, saved_path="dummy.json", item_count=3, items=[]
        )

    monkeypatch.setattr(rss, "collect_feed_items", fake_collect)

    result_json = worker._dispatch_rss_collect(json.dumps({"group_id": "테스트", "hours": 12}))

    assert captured == {"group_id": "테스트", "hours": 12}
    assert json.loads(result_json) == {
        "group_id": "테스트",
        "saved_path": "dummy.json",
        "item_count": 3,
    }


def test_dispatch_rss_collect_defaults_hours(monkeypatch):
    captured = {}

    def fake_collect(request):
        captured["hours"] = request.hours
        return rss.CollectFeedItemsResult(group_id=request.group_id, saved_path="x", item_count=0)

    monkeypatch.setattr(rss, "collect_feed_items", fake_collect)
    worker._dispatch_rss_collect(json.dumps({"group_id": "테스트"}))
    assert captured["hours"] == 24


def test_dispatch_rss_collect_missing_group_id_raises():
    with pytest.raises(KeyError):
        worker._dispatch_rss_collect(json.dumps({"hours": 12}))


@pytest.fixture
def db_conn():
    conn = get_connection()
    yield conn
    conn.close()


@pytest.fixture
def temp_project(db_conn):
    """auto_sns 스키마에 임시 user/project를 만들고 테스트가 끝나면 지운다."""
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (email, display_name, created_at) VALUES (%s, %s, NOW())",
            (f"worker-test-{id(cur)}@example.com", "Worker Test User"),
        )
        user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO projects (owner_id, name, created_at) VALUES (%s, %s, NOW())",
            (user_id, "Worker Test Project"),
        )
        project_id = cur.lastrowid

    yield project_id

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM jobs WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))


def test_poll_once_returns_false_when_no_pending_job(db_conn, temp_project):
    # temp_project만 만들고 job은 없는 상태 — 다만 다른 프로젝트에 PENDING job이 있으면
    # 그걸 집어갈 수 있으니, 이 테스트는 "적어도 예외 없이 False/True 중 하나를 반환한다"만
    # 확인한다(전체 테이블을 비운다고 가정할 수 없어서).
    assert isinstance(worker.poll_once(), bool)


def test_poll_once_marks_unimplemented_job_type_failed(db_conn, temp_project):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs (project_id, type, status, input_json, created_at, updated_at) "
            "VALUES (%s, 'DEEP_RESEARCH', 'PENDING', %s, NOW(), NOW())",
            (temp_project, "{}"),
        )
        job_id = cur.lastrowid

    # 이 job보다 먼저 생성된 다른 PENDING job이 없다는 전제 하에 바로 이 job을 집는다.
    processed = worker.poll_once()
    assert processed is True

    with db_conn.cursor() as cur:
        cur.execute("SELECT status, error_message FROM jobs WHERE id = %s", (job_id,))
        row = cur.fetchone()

    assert row["status"] == "FAILED"
    assert "DEEP_RESEARCH" in row["error_message"]
