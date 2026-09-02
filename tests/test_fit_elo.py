"""Unit tests for Elo walk-forward simulator and grid search optimizer."""

import pytest

from cfb_model.fit.elo import (
    perform_grid_search,
    predict_param,
    simulate_and_evaluate,
    update_param,
)


@pytest.fixture
def mock_ratings() -> dict[str, float]:
    return {
        "alabama": 1600.0,
        "clemson": 1400.0,
    }


def test_predict_param(mock_ratings) -> None:
    game = {
        "homeTeam": "alabama",
        "awayTeam": "clemson",
        "neutralSite": False,
    }

    # Standard HFA = 3.0, elo_per_point = 20.0
    # home - away = 1600.0 - 1400.0 = 200.0
    # gap = 200.0 / 20.0 = 10.0
    # margin = 10.0 + 3.0 = 13.0
    # prob = 1 / (1 + 10 ** (-(13 * 20) / 400))
    #      = 1 / (1 + 10 ** (-260 / 400))
    #      = 1 / (1 + 10 ** -0.65) = 1 / (1 + 0.22387) = 0.817
    # prob = 1 / 1.22387 = 0.817
    margin, prob = predict_param(mock_ratings, game, hfa=3.0, elo_per_point=20.0)
    assert margin == 13.0
    assert prob == pytest.approx(0.81709, abs=0.001)


def test_update_param(mock_ratings) -> None:
    game = {
        "homeTeam": "alabama",
        "awayTeam": "clemson",
        "neutralSite": False,
        "homePoints": 35,
        "awayPoints": 28,
    }

    new_ratings = update_param(
        mock_ratings,
        game,
        hfa=3.0,
        elo_per_point=20.0,
        k=20.0,
        mov_damping=2.2,
        mov_denominator_floor=0.25,
    )

    # Home team won, so ratings for Alabama should go up, Clemson down
    assert new_ratings["alabama"] > 1600.0
    assert new_ratings["clemson"] < 1400.0
    assert new_ratings["alabama"] + new_ratings["clemson"] == pytest.approx(3000.0)


def test_simulate_and_evaluate_empty_timeline() -> None:
    # Evaluating on an empty/unloaded cache or missing directories
    metrics = simulate_and_evaluate(
        {
            "elo_per_point": 20.0,
            "k": 20.0,
            "mov_damping": 2.2,
            "mov_denominator_floor": 0.25,
            "regression_to_mean": 1.0 / 3.0,
            "hfa": 3.0,
        },
        seasons=[2017],
        games_cache={},  # Empty cache
    )
    assert metrics["mae"] == float("inf")
    assert metrics["brier"] == 1.0
    assert metrics["total_games"] == 0


def test_simulate_and_evaluate_with_cache() -> None:
    # Define custom games cache
    games_cache = {
        2017: {
            "01": [
                {
                    "homeTeam": "alabama",
                    "awayTeam": "clemson",
                    "homePoints": 35,
                    "awayPoints": 28,
                    "neutralSite": False,
                }
            ]
        }
    }

    params = {
        "elo_per_point": 20.0,
        "k": 20.0,
        "mov_damping": 2.2,
        "mov_denominator_floor": 0.25,
        "regression_to_mean": 1.0 / 3.0,
        "hfa": 3.0,
    }

    metrics = simulate_and_evaluate(
        params,
        seasons=[2017],
        games_cache=games_cache,
    )

    assert metrics["total_games"] == 1
    assert metrics["mae"] != float("inf")
    assert 0.0 <= metrics["brier"] <= 1.0


def test_perform_grid_search_mock() -> None:
    games_cache = {
        2017: {
            "01": [
                {
                    "homeTeam": "alabama",
                    "awayTeam": "clemson",
                    "homePoints": 35,
                    "awayPoints": 28,
                    "neutralSite": False,
                }
            ]
        }
    }

    best_params, best_metrics = perform_grid_search(
        seasons=[2017],
        fixed_regression=1.0 / 3.0,
        games_cache=games_cache,
    )

    assert best_params is not None
    assert best_metrics is not None
    assert best_metrics["total_games"] == 1
