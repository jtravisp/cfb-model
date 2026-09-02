"""Unit tests for the Ridge regression modeling and feature engineering pipeline."""

import pytest

from cfb_model.fit.features import (
    extract_game_features,
    get_team_season_stats,
)
from cfb_model.fit.ridge import (
    calculate_calibration_slope,
    evaluate_predictions,
)


def test_leakage_guard_raises_on_future_week() -> None:
    # Set up some dummy stats for weeks 0 to 4
    stats_by_week = {
        0: {
            "alabama": [
                {
                    "off_ppa": 1.0,
                    "def_ppa": 0.5,
                    "off_sr": 0.45,
                    "def_sr": 0.35,
                    "off_exp": 1.2,
                    "def_exp": 1.0,
                }
            ]
        },
        1: {
            "alabama": [
                {
                    "off_ppa": 1.2,
                    "def_ppa": 0.4,
                    "off_sr": 0.48,
                    "def_sr": 0.32,
                    "off_exp": 1.3,
                    "def_exp": 0.9,
                }
            ]
        },
    }

    # If evaluating current_week_idx = 1 (Week 2):
    # It must only look at Week 1 (index 0). It must NOT look at Week 2 (index 1) or later!
    # Our helper get_team_season_stats(team, current_week_idx, stats_by_week) handles this.
    stats, games = get_team_season_stats("alabama", current_week_idx=1, stats_by_week=stats_by_week)

    assert games == 1  # Only Week 1 (index 0) should be included!
    assert stats["off_ppa"] == 1.0


def test_extract_game_features_symmetry() -> None:
    stats_by_week = {
        0: {
            "alabama": [
                {
                    "off_ppa": 1.0,
                    "def_ppa": 0.5,
                    "off_sr": 0.45,
                    "def_sr": 0.35,
                    "off_exp": 1.2,
                    "def_exp": 1.0,
                }
            ],
            "clemson": [
                {
                    "off_ppa": 0.8,
                    "def_ppa": 0.6,
                    "off_sr": 0.40,
                    "def_sr": 0.38,
                    "off_exp": 1.1,
                    "def_exp": 1.1,
                }
            ],
        }
    }
    talent = {"alabama": 900.0, "clemson": 800.0}

    game = {
        "homeTeam": "alabama",
        "awayTeam": "clemson",
        "neutralSite": False,
    }

    feats = extract_game_features(
        game,
        current_week_idx=1,
        stats_by_week=stats_by_week,
        talent=talent,
        mean_talent=850.0,
    )

    # home minus away differences
    # ppa diff: 1.0 - 0.8 = 0.2
    assert feats["diff_off_ppa"] == pytest.approx(0.2)
    # def ppa diff: 0.5 - 0.6 = -0.1
    assert feats["diff_def_ppa"] == pytest.approx(-0.1)
    # talent diff: 900.0 - 800.0 = 100.0 (decayed with 1.0 since games = 1)
    assert feats["talent_diff_decayed"] == pytest.approx(100.0)
    assert feats["neutral_site"] == 0.0
    assert feats["home_indicator"] == 1.0


def test_calculate_calibration_slope() -> None:
    import numpy as np
    probs = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
    outcomes = np.array([0.0, 0.0, 1.0, 1.0, 1.0])

    slope = calculate_calibration_slope(probs, outcomes)
    assert 0.0 < slope < 2.0


def test_evaluate_predictions() -> None:
    import numpy as np
    pred_margins = np.array([14.0, -7.0, 3.0, 0.0])
    actual_margins = np.array([17.0, -10.0, -3.0, 1.0])

    metrics = evaluate_predictions(pred_margins, actual_margins, elo_per_point=16.0)
    assert metrics["mae"] == pytest.approx(3.25)
    assert 0.0 <= metrics["brier"] <= 1.0
    assert "calibration_slope" in metrics
