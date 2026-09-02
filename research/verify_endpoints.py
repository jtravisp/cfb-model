"""Diagnostic script to verify CFBD stats_game_advanced endpoint schema and completeness.

This script loads the 2015 backfilled advanced metrics snapshots,
verifies that offensive/defensive PPA (EPA), success rate, and explosiveness
fields are present and non-null, and proves readiness for the Ridge model.
"""

import json
import random
from pathlib import Path


def main() -> None:
    raw_dir = Path("research/raw/cfbd/season=2015")
    if not raw_dir.exists():
        print(f"Error: Directory {raw_dir} does not exist. Did you run s3 sync?")
        return

    # Find all week-scoped JSON snapshots (excluding .meta.json files)
    json_files = sorted(
        [
            f
            for f in raw_dir.glob("**/stats_game_advanced/*.json")
            if not f.name.endswith(".meta.json")
        ]
    )

    if not json_files:
        print("Error: No stats_game_advanced JSON files found under research/raw/cfbd/season=2015/")
        return

    print(f"Found {len(json_files)} advanced stats snapshots for the 2015 season.")

    # Select a random week's snapshot to verify
    selected_file = random.choice(json_files)
    week_name = selected_file.parent.parent.name  # e.g., 'week=01' or 'week=postseason'
    print(f"\n--- Diagnostic verification of selected snapshot: {week_name} ---")
    print(f"File path: {selected_file}")

    with open(selected_file) as f:
        games_data = json.load(f)

    print(f"Total game records in this snapshot: {len(games_data)}")
    assert len(games_data) > 0, "Selected snapshot is empty"

    # Define the required metrics to check
    required_metrics = ["ppa", "successRate", "explosiveness"]

    # Verify every record in the selected week's file
    checked_records = 0
    for _idx, record in enumerate(games_data):
        game_id = record.get("gameId")
        team = record.get("team")
        opp = record.get("opponent")

        # Assert sections exist
        assert "offense" in record, f"Game {game_id}: 'offense' section is missing"
        assert "defense" in record, f"Game {game_id}: 'defense' section is missing"

        off = record["offense"]
        def_ = record["defense"]

        # Assert offensive metrics exist and are non-null
        for metric in required_metrics:
            assert metric in off, f"Game {game_id} ({team} vs {opp}): offense.{metric} is missing"
            assert off[metric] is not None, f"Game {game_id} ({team} vs {opp}): offense.{metric} is null"
            assert isinstance(off[metric], (int, float)), (
                f"Game {game_id} ({team} vs {opp}): offense.{metric} is not a numeric value: {off[metric]}"
            )

        # Assert defensive metrics exist and are non-null
        for metric in required_metrics:
            assert metric in def_, f"Game {game_id} ({team} vs {opp}): defense.{metric} is missing"
            assert def_[metric] is not None, f"Game {game_id} ({team} vs {opp}): defense.{metric} is null"
            assert isinstance(def_[metric], (int, float)), (
                f"Game {game_id} ({team} vs {opp}): defense.{metric} is not a numeric value: {def_[metric]}"
            )

        checked_records += 1

    print(f"Successfully validated {checked_records}/{len(games_data)} records in {week_name}.")
    print("All assertions passed: Required fields exist and are of valid numeric types.")

    # Let's perform a broad analysis of ALL weeks to inspect completeness across the whole season
    print("\n--- Season-Wide Data Completeness Analysis ---")
    total_games_all_weeks = 0
    total_missing_offense = 0
    total_missing_defense = 0
    total_null_metrics = 0

    for file in json_files:
        w_name = file.parent.parent.name
        with open(file) as f:
            data = json.load(f)

        null_count_in_week = 0
        for r in data:
            total_games_all_weeks += 1
            off = r.get("offense")
            df = r.get("defense")

            if not off:
                total_missing_offense += 1
                continue
            if not df:
                total_missing_defense += 1
                continue

            for m in required_metrics:
                if r["offense"].get(m) is None:
                    total_null_metrics += 1
                    null_count_in_week += 1
                if r["defense"].get(m) is None:
                    total_null_metrics += 1
                    null_count_in_week += 1

        print(f"  - {w_name:<16}: {len(data):>3} games checked, {null_count_in_week} nulls/missing found.")

    print("\nSummary of Season-Wide Metrics:")
    print(f"  - Total unique game-team records: {total_games_all_weeks}")
    print(f"  - Records missing entire offense stats: {total_missing_offense}")
    print(f"  - Records missing entire defense stats: {total_missing_defense}")
    print(f"  - Total null required metrics: {total_null_metrics}")

    if total_missing_offense == 0 and total_missing_defense == 0 and total_null_metrics == 0:
        print("\nPROVEN: CFBD stats_game_advanced endpoint provides 100% complete metrics for 2015!")
    else:
        print(f"\nWARNING: Found some missing data in historical records! ({total_null_metrics} nulls)")


if __name__ == "__main__":
    main()
