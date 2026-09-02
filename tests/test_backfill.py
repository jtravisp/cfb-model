"""Tests for CFBD historical backfill implementation."""

import json
from datetime import UTC, datetime

import pytest

from cfb.manifest import manifest_key, snapshot_key
from cfb.models import Manifest
from cfb.storage import MemorySnapshotStore
from cfb_model.backfill import (
    build_backfill_items,
    execute_backfill,
    plan_backfill,
)


class MockCfbdClient:
    """Simple mock CFBD client for testing."""

    def __init__(self, data: bytes = b"[]", fail_path: str | None = None):
        self.data = data
        self.fail_path = fail_path
        self.calls_made = 0

    def get(self, path: str, **kwargs) -> bytes:
        self.calls_made += 1
        if self.fail_path and path == self.fail_path:
            raise RuntimeError("API error simulation")
        return self.data


def test_build_backfill_items() -> None:
    # 1 season, calendar and games
    items = build_backfill_items(
        seasons=[2024],
        resources=["calendar", "games"],
        weeks=[1, 2],
        include_postseason=True,
    )
    # calendar is season-scoped -> 1 item: week="season"
    # games is week-scoped -> 2 items (weeks 1, 2) + 1 item (postseason) -> 3 items
    # Total = 4 items
    assert len(items) == 4

    calendar_item = [it for it in items if it.resource == "calendar"][0]
    assert calendar_item.week == "season"
    assert calendar_item.params == {"year": 2024}
    assert calendar_item.key_prefix == "raw/cfbd/season=2024/week=season/calendar/"

    games_items = [it for it in items if it.resource == "games"]
    assert len(games_items) == 3
    assert {it.week for it in games_items} == {"01", "02", "postseason"}


def test_plan_backfill_empty_store() -> None:
    store = MemorySnapshotStore()
    plan = plan_backfill(
        store=store,
        seasons=[2024],
        resources=["calendar"],
        include_postseason=False,
    )
    assert len(plan.total_planned) == 1
    assert len(plan.existing) == 0
    assert len(plan.outstanding) == 1
    assert plan.estimated_calls == 1


def test_plan_backfill_with_existing() -> None:
    store = MemorySnapshotStore()
    fetched_at = datetime.now(UTC)
    snap_key = snapshot_key(
        source="cfbd",
        season=2024,
        week="season",
        fetched_at=fetched_at,
        resource="calendar",
    )
    store.put_bytes(snap_key, b"[]", "application/json")

    manifest = Manifest(
        schema_version=1,
        source="cfbd",
        resource="calendar",
        source_url="https://api.collegefootballdata.com/calendar",
        http_status=200,
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        bytes=2,
        encoding=None,
        fetched_at=fetched_at,
        season=2024,
        week="season",
        week_resolution="calendar",
        snapshot_key=snap_key,
    )
    store.put_json(
        manifest_key(snap_key),
        manifest.model_dump(mode="json", exclude={"unmapped"}),
    )

    plan = plan_backfill(
        store=store, seasons=[2024], resources=["calendar"], include_postseason=False
    )
    assert len(plan.total_planned) == 1
    assert len(plan.existing) == 1
    assert len(plan.outstanding) == 0
    assert plan.estimated_calls == 0


def test_plan_backfill_ignore_store_errors() -> None:
    class FailingStore(MemorySnapshotStore):
        def list_manifests(self, prefix: str):
            raise RuntimeError("S3 connection error simulation")

    store = FailingStore()
    # Without ignore_store_errors, it should raise RuntimeError
    with pytest.raises(RuntimeError, match="S3 connection error simulation"):
        plan_backfill(store=store, seasons=[2024], resources=["calendar"])

    # With ignore_store_errors, it should print warning and succeed (assuming empty cache)
    plan = plan_backfill(
        store=store,
        seasons=[2024],
        resources=["calendar"],
        ignore_store_errors=True,
    )
    assert len(plan.total_planned) == 1
    assert len(plan.outstanding) == 1


def test_execute_backfill_success() -> None:
    store = MemorySnapshotStore()
    plan = plan_backfill(
        store=store,
        seasons=[2024],
        resources=["calendar"],
        include_postseason=False,
    )
    client = MockCfbdClient(data=b'{"key": "value"}')

    result = execute_backfill(
        store=store,
        client=client,
        plan=plan,
        max_calls=1,
    )

    assert result.fetched_count == 1
    assert result.bytes_written == 16
    assert len(result.errors) == 0
    assert client.calls_made == 1

    # Verify snapshot and manifest written to store
    manifests = store.list_manifests("raw/cfbd/")
    assert len(manifests) == 1
    manifest = manifests[0]
    assert manifest.season == 2024
    assert manifest.week == "season"
    assert manifest.resource == "calendar"
    assert manifest.bytes == 16

    data = store.get_bytes(manifest.snapshot_key)
    assert json.loads(data) == {"key": "value"}


def test_execute_backfill_with_errors() -> None:
    store = MemorySnapshotStore()
    plan = plan_backfill(
        store=store,
        seasons=[2024],
        resources=["calendar", "teams"],
        include_postseason=False,
    )
    client = MockCfbdClient(fail_path="/teams")

    result = execute_backfill(
        store=store,
        client=client,
        plan=plan,
        max_calls=2,
    )

    # First succeeds (calendar), second fails (teams)
    assert result.fetched_count == 1
    assert len(result.errors) == 1
    assert result.errors[0][0].resource == "teams"
    assert "API error simulation" in result.errors[0][1]
