"""Tests for historical preseason seeding and Elo state schema."""

import json
from datetime import UTC, datetime

import pytest

from cfb_model.elo.seed import seed_history
from cfb_model.elo.state import EloModel, EloState


@pytest.fixture
def base_model() -> EloModel:
    return EloModel(
        elo_per_point=20.0,
        k=20.0,
        mov_damping=2.2,
        mov_denominator_floor=0.25,
        regression_to_mean=1.0 / 3.0,
        hfa_source="fitted",
    )


@pytest.fixture
def previous_state(base_model: EloModel) -> EloState:
    return EloState(
        schema_version=2,
        season=2019,
        week="postseason",
        generated_at=datetime.now(UTC),
        seeded_from="raw/cfbd/season=2019/week=season/teams/dummy.json",
        games_applied=1000,
        folded_from=None,
        through_kickoff=datetime.now(UTC),
        model=base_model,
        ratings={
            "Alabama": 1800.0,
            "Clemson": 1750.0,
            "Georgia": 1650.0,
            "Vanderbilt": 1300.0,
        },
    )


def test_seed_history_cold_start_empty(tmp_path: pytest.TempPathFactory) -> None:
    # Cold start with no raw teams snapshot folder -> should return empty ratings
    ratings = seed_history(None, gap_seasons=1, raw_dir=tmp_path)
    assert ratings == {}


def test_seed_history_cold_start_with_teams(tmp_path: pytest.TempPathFactory) -> None:
    # Setup mock raw directory for 2015
    season_dir = tmp_path / "season=2015" / "week=season" / "teams"
    season_dir.mkdir(parents=True, exist_ok=True)

    teams_data = [
        {"school": "Alabama", "classification": "fbs"},
        {"school": "Clemson", "classification": "fbs"},
        {"school": "Abilene Christian", "classification": "fcs"},  # Should be ignored
    ]
    with open(season_dir / "teams_snapshot.json", "w", encoding="utf-8") as f:
        json.dump(teams_data, f)

    ratings = seed_history(None, gap_seasons=1, raw_dir=tmp_path)

    # 2015 cold start: all FBS teams map to exactly 1500.0
    assert ratings == {
        "Alabama": 1500.0,
        "Clemson": 1500.0,
    }


def test_seed_history_gap_1_transition(
    previous_state: EloState, tmp_path: pytest.TempPathFactory
) -> None:
    # Setup mock raw directory for new season 2020 (gap_seasons=1)
    season_dir = tmp_path / "season=2020" / "week=season" / "teams"
    season_dir.mkdir(parents=True, exist_ok=True)

    teams_data = [
        {"school": "Alabama", "classification": "fbs"},
        {"school": "Clemson", "classification": "fbs"},
        {"school": "Georgia", "classification": "fbs"},
        {"school": "Vanderbilt", "classification": "fbs"},
    ]
    with open(season_dir / "teams_snapshot.json", "w", encoding="utf-8") as f:
        json.dump(teams_data, f)

    ratings = seed_history(previous_state, gap_seasons=1, raw_dir=tmp_path)

    # Regression to mean = 1/3 (factor = 2/3)
    # 1500 + (r - 1500) * (2/3)
    # Alabama: 1500 + (1800 - 1500) * 2/3 = 1500 + 300 * 2/3 = 1700.0
    # Clemson: 1500 + (1750 - 1500) * 2/3 = 1500 + 250 * 2/3 = 1666.6666...
    # Georgia: 1500 + (1650 - 1500) * 2/3 = 1500 + 150 * 2/3 = 1600.0
    # Vanderbilt: 1500 + (1300 - 1500) * 2/3 = 1500 - 200 * 2/3 = 1366.6666...
    assert ratings["Alabama"] == pytest.approx(1700.0)
    assert ratings["Clemson"] == pytest.approx(1500.0 + 250.0 * (2.0 / 3.0))
    assert ratings["Georgia"] == pytest.approx(1600.0)
    assert ratings["Vanderbilt"] == pytest.approx(1500.0 - 200.0 * (2.0 / 3.0))


def test_seed_history_gap_2_transition_2020_hole(
    previous_state: EloState, tmp_path: pytest.TempPathFactory
) -> None:
    # Setup mock raw directory for 2021 (gap_seasons=2, stepping over the 2020 hole)
    season_dir = tmp_path / "season=2021" / "week=season" / "teams"
    season_dir.mkdir(parents=True, exist_ok=True)

    teams_data = [
        {"school": "Alabama", "classification": "fbs"},
        {"school": "Clemson", "classification": "fbs"},
    ]
    with open(season_dir / "teams_snapshot.json", "w", encoding="utf-8") as f:
        json.dump(teams_data, f)

    ratings = seed_history(previous_state, gap_seasons=2, raw_dir=tmp_path)

    # Regression to mean factor = (2/3) ** 2 = 4/9
    # Alabama: 1500 + (1800 - 1500) * 4/9 = 1500 + 300 * 4/9 = 1500 + 133.333 = 1633.333...
    # Clemson: 1500 + (1750 - 1500) * 4/9 = 1500 + 250 * 4/9 = 1500 + 111.111 = 1611.111...
    assert ratings["Alabama"] == pytest.approx(1500.0 + 300.0 * (4.0 / 9.0))
    assert ratings["Clemson"] == pytest.approx(1500.0 + 250.0 * (4.0 / 9.0))


def test_seed_history_with_unrated_team(
    previous_state: EloState, tmp_path: pytest.TempPathFactory
) -> None:
    # Setup mock raw directory for 2020
    season_dir = tmp_path / "season=2020" / "week=season" / "teams"
    season_dir.mkdir(parents=True, exist_ok=True)

    # Setup teams where "Coastal Carolina" is a new FBS team
    teams_data = [
        {"school": "Alabama", "classification": "fbs"},
        {"school": "Coastal Carolina", "classification": "fbs"},
    ]
    with open(season_dir / "teams_snapshot.json", "w", encoding="utf-8") as f:
        json.dump(teams_data, f)

    ratings = seed_history(previous_state, gap_seasons=1, raw_dir=tmp_path)

    # Coastal Carolina was not in previous ratings -> should enter at exactly 1500.0
    assert ratings["Coastal Carolina"] == 1500.0
    assert ratings["Alabama"] == pytest.approx(1700.0)
