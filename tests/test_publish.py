"""Unit tests for bake-off publishing and HTML reporting logic."""

import pytest

from cfb_model.publish.models import calculate_ats_record
from cfb_model.publish.report import generate_calibration_data


def test_calculate_ats_record() -> None:
    # Set up some dummy aligned predictions
    # Spread of -7.0 means Home is a 7-point favorite (expected home margin = 7.0)
    predictions = [
        # Case 1: Model predicted margin 10.0 (> 7.0 expected home margin), so we bet Home.
        # Actual margin is 14.0 (> 7.0 expected home margin) -> Win!
        {
            "market_spread": -7.0,
            "elo_pred_margin": 10.0,
            "actual_margin": 14.0,
        },
        # Case 2: Model predicted margin 3.0 (< 7.0 expected home margin), so we bet Away.
        # Actual margin is -3.0 (< 7.0 expected home margin) -> Win!
        {
            "market_spread": -7.0,
            "elo_pred_margin": 3.0,
            "actual_margin": -3.0,
        },
        # Case 3: Model predicted margin 10.0 (> 7.0 expected home margin), so we bet Home.
        # Actual margin is 3.0 (< 7.0 expected home margin) -> Loss!
        {
            "market_spread": -7.0,
            "elo_pred_margin": 10.0,
            "actual_margin": 3.0,
        },
        # Case 4: Model predicted margin 10.0 (> 7.0 expected home margin), so we bet Home.
        # Actual margin is 7.0 (== 7.0 expected home margin) -> Push!
        {
            "market_spread": -7.0,
            "elo_pred_margin": 10.0,
            "actual_margin": 7.0,
        },
        # Case 5: Model predicted margin 7.0 (== 7.0 expected home margin) -> No Edge, Excluded!
        {
            "market_spread": -7.0,
            "elo_pred_margin": 7.0,
            "actual_margin": 14.0,
        },
    ]

    record = calculate_ats_record(predictions, "elo")
    assert record["record"] == "2-1-1"
    assert record["wins"] == 2
    assert record["losses"] == 1
    assert record["pushes"] == 1
    assert record["excluded_no_edge"] == 1


def test_generate_calibration_data() -> None:
    # Setup some predictions: (pred_margin, pred_prob, actual_margin, actual_outcome)
    predictions = [
        # Bucket '7' (5.0 <= abs(pred_m) < 8.5)
        (7.0, 0.67, 14.0, 1.0),   # Favorite won
        (-7.0, 0.33, -3.0, 0.0),  # Favorite won (Away won when Away predicted)
        (6.0, 0.65, -3.0, 0.0),   # Favorite lost
        # Bucket '3' (1.5 <= abs(pred_m) < 5.0)
        (3.0, 0.58, 7.0, 1.0),    # Favorite won
    ]

    cal_data = generate_calibration_data(predictions)

    # We expect 7 buckets
    assert len(cal_data) == 7

    # Find bucket '7'
    cal_7 = [b for b in cal_data if b["margin_bucket"] == "7"][0]
    assert cal_7["games_count"] == 3
    # 2 out of 3 won -> 66.6% win rate
    assert cal_7["observed_win_rate"] == pytest.approx(2.0 / 3.0)

    # Find bucket '3'
    cal_3 = [b for b in cal_data if b["margin_bucket"] == "3"][0]
    assert cal_3["games_count"] == 1
    # 1 out of 1 won -> 100% win rate
    assert cal_3["observed_win_rate"] == 1.0
