"""CFBD historical data backfill engine (SPEC-phase2 §3.5-§3.7, PRD §3).

Features:
- Store-derived resumability: checks existing snapshots in `raw/cfbd/` and fetches missing only.
- Dry-run verification: computes exact call plan, estimated API usage, and run budgets with 0 spend.
- Strict immutability: writes once to `raw/cfbd/` with `.meta.json` manifests.
- Budget guardrails: integrates with `CfbdClient` per-run call budget to protect quota.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cfb.collectors.cfbd import BASE_URL, CALL_BUDGET_PER_RUN, CfbdClient
from cfb.manifest import manifest_key, snapshot_key
from cfb.models import Manifest, validating
from cfb.storage import SnapshotStore

__all__ = [
    "DEFAULT_RESOURCES",
    "RESOURCE_DEFINITIONS",
    "BackfillItem",
    "BackfillPlan",
    "BackfillResource",
    "BackfillResult",
    "build_backfill_items",
    "discover_existing_snapshots",
    "execute_backfill",
    "format_backfill_plan",
    "plan_backfill",
]


@dataclass(frozen=True)
class BackfillResource:
    name: str
    path: str
    is_week_scoped: bool
    description: str


RESOURCE_DEFINITIONS: dict[str, BackfillResource] = {
    "calendar": BackfillResource(
        name="calendar",
        path="/calendar",
        is_week_scoped=False,
        description="Season schedule and week boundaries",
    ),
    "teams": BackfillResource(
        name="teams",
        path="/teams",
        is_week_scoped=False,
        description="FBS and FCS team metadata",
    ),
    "talent": BackfillResource(
        name="talent",
        path="/talent",
        is_week_scoped=False,
        description="247Sports Team Talent Composite ratings",
    ),
    "games": BackfillResource(
        name="games",
        path="/games",
        is_week_scoped=True,
        description="Game schedules, final scores, and completion status",
    ),
    "lines": BackfillResource(
        name="lines",
        path="/lines",
        is_week_scoped=True,
        description="Historical consensus and sportsbook point spreads",
    ),
    "stats_game_advanced": BackfillResource(
        name="stats_game_advanced",
        path="/stats/game/advanced",
        is_week_scoped=True,
        description="Per-game advanced efficiency (EPA/PPA, success rate, explosiveness)",
    ),
}

DEFAULT_RESOURCES: tuple[str, ...] = tuple(RESOURCE_DEFINITIONS.keys())


@dataclass(frozen=True)
class BackfillItem:
    season: int
    week: str
    resource: str
    path: str
    params: dict[str, Any]

    @property
    def key_prefix(self) -> str:
        """Partition prefix under raw/cfbd/."""
        return f"raw/cfbd/season={self.season}/week={self.week}/{self.resource}/"


@dataclass(frozen=True)
class BackfillPlan:
    seasons: list[int]
    resources: list[str]
    total_planned: list[BackfillItem]
    existing: list[BackfillItem]
    outstanding: list[BackfillItem]

    @property
    def estimated_calls(self) -> int:
        return len(self.outstanding)


@dataclass(frozen=True)
class BackfillResult:
    fetched_count: int
    bytes_written: int
    errors: list[tuple[BackfillItem, str]]


def build_backfill_items(
    seasons: list[int],
    resources: list[str] | None = None,
    weeks: list[int] | None = None,
    include_postseason: bool = True,
) -> list[BackfillItem]:
    """Generate the full universe of expected backfill items for given seasons."""
    chosen_resources = resources if resources is not None else list(DEFAULT_RESOURCES)
    for res in chosen_resources:
        if res not in RESOURCE_DEFINITIONS:
            raise ValueError(
                f"unknown resource {res!r}: expected one of {sorted(RESOURCE_DEFINITIONS)}"
            )

    items: list[BackfillItem] = []
    target_weeks = weeks if weeks is not None else list(range(1, 16))

    for season in sorted(seasons):
        # 1. Season-level resources
        for res_name in chosen_resources:
            res_def = RESOURCE_DEFINITIONS[res_name]
            if not res_def.is_week_scoped:
                items.append(
                    BackfillItem(
                        season=season,
                        week="season",
                        resource=res_name,
                        path=res_def.path,
                        params={"year": season},
                    )
                )

        # 2. Week-level resources (regular season)
        for w in target_weeks:
            week_str = f"{w:02d}"
            for res_name in chosen_resources:
                res_def = RESOURCE_DEFINITIONS[res_name]
                if res_def.is_week_scoped:
                    items.append(
                        BackfillItem(
                            season=season,
                            week=week_str,
                            resource=res_name,
                            path=res_def.path,
                            params={"year": season, "week": w},
                        )
                    )

        # 3. Postseason (week-level resources)
        if include_postseason:
            for res_name in chosen_resources:
                res_def = RESOURCE_DEFINITIONS[res_name]
                if res_def.is_week_scoped:
                    items.append(
                        BackfillItem(
                            season=season,
                            week="postseason",
                            resource=res_name,
                            path=res_def.path,
                            params={"year": season, "seasonType": "postseason"},
                        )
                    )

    return items


def discover_existing_snapshots(
    store: SnapshotStore,
    seasons: list[int],
    ignore_errors: bool = False,
) -> set[tuple[int, str, str]]:
    """Scan store for already captured snapshots. Returns set of (season, week, resource)."""
    existing: set[tuple[int, str, str]] = set()

    for season in seasons:
        prefix = f"raw/cfbd/season={season}/"
        try:
            manifests = store.list_manifests(prefix)
            for m in manifests:
                existing.add((m.season, m.week, m.resource))
        except Exception as exc:
            if ignore_errors:
                import sys

                print(
                    f"[Warning] Store connection / access error listing manifests "
                    f"for season {season}: {exc}.\n"
                    "Proceeding with empty cache for planning/dry-run purposes.",
                    file=sys.stderr,
                )
            else:
                raise

    return existing


def plan_backfill(
    store: SnapshotStore,
    seasons: list[int],
    resources: list[str] | None = None,
    weeks: list[int] | None = None,
    include_postseason: bool = True,
    ignore_store_errors: bool = False,
) -> BackfillPlan:
    """Compute the delta between desired backfill scope and existing store snapshots."""
    all_items = build_backfill_items(
        seasons=seasons,
        resources=resources,
        weeks=weeks,
        include_postseason=include_postseason,
    )
    existing_keys = discover_existing_snapshots(store, seasons, ignore_errors=ignore_store_errors)

    existing_items: list[BackfillItem] = []
    outstanding_items: list[BackfillItem] = []

    for item in all_items:
        if (item.season, item.week, item.resource) in existing_keys:
            existing_items.append(item)
        else:
            outstanding_items.append(item)

    return BackfillPlan(
        seasons=sorted(seasons),
        resources=resources if resources is not None else list(DEFAULT_RESOURCES),
        total_planned=all_items,
        existing=existing_items,
        outstanding=outstanding_items,
    )


def format_backfill_plan(plan: BackfillPlan, store_uri: str = "configured store") -> str:
    """Format a human-readable summary table for dry-run verification."""
    lines = [
        "=" * 80,
        "CFBD HISTORICAL BACKFILL PLAN (DRY-RUN)",
        "=" * 80,
        f"Target Store: {store_uri}",
        f"Target Seasons: {plan.seasons} ({len(plan.seasons)} season(s))",
        f"Resources: {', '.join(plan.resources)}",
        "",
        "SUMMARY BY SEASON:",
        f"{'Season':<8} | {'Existing':<10} | {'Outstanding':<12} | {'Total Items':<12}",
        "-" * 50,
    ]

    for season in plan.seasons:
        season_total = sum(1 for item in plan.total_planned if item.season == season)
        season_exist = sum(1 for item in plan.existing if item.season == season)
        season_out = sum(1 for item in plan.outstanding if item.season == season)
        lines.append(f"{season:<8} | {season_exist:<10} | {season_out:<12} | {season_total:<12}")

    tot_exist = len(plan.existing)
    tot_out = len(plan.outstanding)
    tot_plan = len(plan.total_planned)
    lines.extend(
        [
            "-" * 50,
            f"{'Total':<8} | {tot_exist:<10} | {tot_out:<12} | {tot_plan:<12}",
            "",
            "SUMMARY BY RESOURCE:",
            f"{'Resource':<22} | {'Existing':<10} | {'Outstanding':<12} | {'Total':<10}",
            "-" * 62,
        ]
    )

    for res in plan.resources:
        res_total = sum(1 for item in plan.total_planned if item.resource == res)
        res_exist = sum(1 for item in plan.existing if item.resource == res)
        res_out = sum(1 for item in plan.outstanding if item.resource == res)
        lines.append(f"{res:<22} | {res_exist:<10} | {res_out:<12} | {res_total:<10}")

    runs_needed = (len(plan.outstanding) + CALL_BUDGET_PER_RUN - 1) // CALL_BUDGET_PER_RUN
    lines.extend(
        [
            "=" * 80,
            f"ESTIMATED CFBD CALL SPEND: {plan.estimated_calls} call(s)",
            f"DEFAULT PER-RUN BUDGET:    {CALL_BUDGET_PER_RUN} calls/run",
            f"ESTIMATED BATCH RUNS:      {runs_needed} run(s)",
            "",
            "DRY-RUN STATUS: Zero API calls made. Zero store writes made.",
            "=" * 80,
        ]
    )

    return "\n".join(lines)


def execute_backfill(
    store: SnapshotStore,
    client: CfbdClient,
    plan: BackfillPlan,
    max_calls: int | None = None,
    now: datetime | None = None,
    progress_callback: Callable[[BackfillItem, int, int], None] | None = None,
) -> BackfillResult:
    """Execute live fetch of outstanding backfill items into store."""
    moment = now or datetime.now(UTC)
    limit = max_calls if max_calls is not None else len(plan.outstanding)
    items_to_fetch = plan.outstanding[:limit]

    fetched = 0
    total_bytes = 0
    errors: list[tuple[BackfillItem, str]] = []

    for i, item in enumerate(items_to_fetch, start=1):
        if progress_callback:
            progress_callback(item, i, len(items_to_fetch))

        try:
            data = client.get(item.path, **item.params)
            key = snapshot_key(
                source="cfbd",
                season=item.season,
                week=item.week,
                fetched_at=moment,
                resource=item.resource,
            )
            store.put_bytes(key, data, "application/json")

            with validating(f"manifest for {key}"):
                manifest = Manifest(
                    schema_version=1,
                    source="cfbd",
                    resource=item.resource,
                    source_url=f"{BASE_URL}{item.path}",
                    http_status=200,
                    sha256=hashlib.sha256(data).hexdigest(),
                    bytes=len(data),
                    encoding=None,
                    fetched_at=moment,
                    season=item.season,
                    week=item.week,
                    week_resolution="calendar",
                    snapshot_key=key,
                )
            store.put_json(
                manifest_key(key),
                manifest.model_dump(mode="json", exclude={"unmapped"}),
            )
            fetched += 1
            total_bytes += len(data)
        except Exception as exc:
            errors.append((item, str(exc)))
            break

    return BackfillResult(
        fetched_count=fetched,
        bytes_written=total_bytes,
        errors=errors,
    )
