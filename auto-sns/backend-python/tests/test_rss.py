"""services/rss.py 그룹 CRUD 테스트.

health_check_group / collect_feed_items는 실제 네트워크(feedparser) 호출이 필요해
자동 테스트 범위에서 제외한다 — 수동 스모크 테스트로 별도 확인한다.
"""

import pytest

from ai_sns_worker.services import rss


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """SOURCES_DIR/RSS_COLLECT_DIR을 tmp_path 아래로 바꿔 실제 storage/를 건드리지 않는다."""
    monkeypatch.setattr(rss, "SOURCES_DIR", tmp_path / "sources")
    monkeypatch.setattr(rss, "RSS_COLLECT_DIR", tmp_path / "rss_collect")


def test_create_and_list_group():
    result = rss.create_feed_group(rss.CreateFeedGroupRequest(name="테스트 그룹"))
    assert result.name == "테스트 그룹"

    groups = rss.list_feed_groups()
    assert len(groups) == 1
    assert groups[0].id == result.id
    assert groups[0].feed_count == 0
    assert groups[0].last_health_check is None


def test_create_group_dedupes_slug():
    a = rss.create_feed_group(rss.CreateFeedGroupRequest(name="뉴스"))
    b = rss.create_feed_group(rss.CreateFeedGroupRequest(name="뉴스"))
    assert a.id != b.id
    assert len(rss.list_feed_groups()) == 2


def test_create_group_empty_name_raises():
    with pytest.raises(ValueError):
        rss.create_feed_group(rss.CreateFeedGroupRequest(name="   "))


def test_add_update_remove_feed():
    group = rss.create_feed_group(rss.CreateFeedGroupRequest(name="테스트"))

    added = rss.add_feed(rss.AddFeedRequest(
        group_id=group.id, name="피드1", url="https://example.com/rss", tier="1",
    ))
    assert added.feed_index == 0
    assert added.feed.enabled is True

    updated = rss.update_feed(rss.UpdateFeedRequest(
        group_id=group.id, feed_index=0, enabled=False,
    ))
    assert updated.feed.enabled is False
    assert updated.feed.name == "피드1"  # 지정하지 않은 필드는 유지된다

    removed = rss.remove_feed(rss.RemoveFeedRequest(group_id=group.id, feed_index=0))
    assert removed.removed is True
    assert rss.list_feed_groups()[0].feed_count == 0


def test_operations_on_missing_group_raise():
    with pytest.raises(FileNotFoundError):
        rss.add_feed(rss.AddFeedRequest(group_id="없는그룹", name="a", url="b", tier="1"))


def test_update_feed_invalid_index_raises():
    group = rss.create_feed_group(rss.CreateFeedGroupRequest(name="테스트"))
    with pytest.raises(IndexError):
        rss.update_feed(rss.UpdateFeedRequest(group_id=group.id, feed_index=0, enabled=True))
