"""Elo model research simulation, walk-forward evaluation, and grid search (SPEC-phase2 §4)."""

import json
import math
from datetime import UTC, datetime
from pathlib import Path

from cfb_model.crosswalk import load as load_crosswalk
from cfb_model.elo.seed import seed_history
from cfb_model.elo.state import EloModel, EloState


def predict_param(ratings, game, *, hfa, elo_per_point):
    """Parameterized predict function to avoid global constants."""
    home = ratings.get(game["homeTeam"], 1500.0)
    away = ratings.get(game["awayTeam"], 1500.0)
    gap = home - away
    edge = 0.0 if game["neutralSite"] else hfa
    margin = gap / elo_per_point + edge
    prob = 1 / (1 + 10 ** (-(margin * elo_per_point) / 400))
    return margin, prob


def update_param(
    ratings,
    game,
    *,
    hfa,
    elo_per_point,
    k,
    mov_damping,
    mov_denominator_floor,
):
    """Parameterized update function to avoid global constants."""
    home = ratings.get(game["homeTeam"], 1500.0)
    away = ratings.get(game["awayTeam"], 1500.0)
    edge = 0.0 if game["neutralSite"] else hfa
    diff = home + edge * elo_per_point - away
    expected = 1 / (1 + 10 ** (-diff / 400))

    margin = game["homePoints"] - game["awayPoints"]
    actual = 1.0 if margin > 0 else 0.0
    signed = diff if margin > 0 else -diff

    raw_denom = signed * 0.001 + mov_damping
    denom = max(raw_denom, mov_denominator_floor)

    mov_mult = math.log(abs(margin) + 1) * (mov_damping / denom)
    delta = k * mov_mult * (actual - expected)

    new_ratings = ratings.copy()
    new_ratings[game["homeTeam"]] = home + delta
    new_ratings[game["awayTeam"]] = away - delta
    return new_ratings


def load_all_games(seasons, raw_dir=Path("research/raw/cfbd")):
    """Pre-load and resolve all games for specified seasons to cache in memory (huge speedup)."""
    cache = {}
    weeks = [
        "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15",
        "postseason"
    ]

    for season in seasons:
        try:
            cw = load_crosswalk(season)
        except Exception:
            continue

        cache[season] = {}
        for week in weeks:
            games_dir = raw_dir / f"season={season}" / f"week={week}" / "games"
            if not games_dir.exists():
                continue

            json_files = [f for f in games_dir.glob("*.json") if not f.name.endswith(".meta.json")]
            if not json_files:
                continue

            with open(json_files[0], encoding="utf-8") as f:
                games_data = json.load(f)

            sorted_games = sorted(games_data, key=lambda g: g.get("startDate", ""))
            mapped_games = []

            for game in sorted_games:
                is_invalid = (
                    not game.get("completed")
                    or game.get("homePoints") is None
                    or game.get("awayPoints") is None
                )
                if is_invalid:
                    continue
                if game["homePoints"] == game["awayPoints"]:
                    continue

                try:
                    home_canonical = cw.from_cfbd(game["homeTeam"])
                    away_canonical = cw.from_cfbd(game["awayTeam"])
                except Exception:
                    continue

                mapped_games.append({
                    "homeTeam": home_canonical,
                    "awayTeam": away_canonical,
                    "homePoints": game["homePoints"],
                    "awayPoints": game["awayPoints"],
                    "neutralSite": game.get("neutralSite", False),
                })

            if mapped_games:
                cache[season][week] = mapped_games
    return cache


def simulate_and_evaluate(
    params,
    seasons,
    *,
    exclude_weeks_1_3=False,
    eval_seasons=None,
    games_cache=None,
    raw_dir=Path("research/raw/cfbd"),
):
    """Run sequential walk-forward simulation across multiple seasons and calculate performance."""
    ratings = {}
    prev_season = None

    # List of tuples: (predicted_margin, predicted_prob, actual_margin, actual_prob)
    predictions = []

    weeks = [
        "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15",
        "postseason"
    ]

    # Use games cache if provided to bypass disk reads completely
    cache = games_cache if games_cache is not None else load_all_games(seasons, raw_dir=raw_dir)

    for season in seasons:
        # Preseason Seeding
        if prev_season is None:
            ratings = seed_history(None, raw_dir=raw_dir)
        else:
            # Construct a lightweight mock previous EloState
            prev_state_obj = EloState(
                schema_version=2,
                season=prev_season,
                week="postseason",
                generated_at=datetime.now(UTC),
                seeded_from="dummy",
                games_applied=0,
                model=EloModel(
                    elo_per_point=params["elo_per_point"],
                    k=params["k"],
                    mov_damping=params["mov_damping"],
                    mov_denominator_floor=params["mov_denominator_floor"],
                    regression_to_mean=params["regression_to_mean"],
                    hfa_source="fitted",
                ),
                ratings=ratings,
            )
            gap = season - prev_season
            ratings = seed_history(prev_state_obj, gap_seasons=gap, raw_dir=raw_dir)

        # Skip season if not present in cache
        if season not in cache:
            continue

        for week in weeks:
            mapped_games = cache[season].get(week, [])
            for mapped_game in mapped_games:
                # Evaluate prediction if outside burn-in and in evaluation seasons
                is_eval_season = (
                    (eval_seasons is not None and season in eval_seasons) or
                    (eval_seasons is None and season >= 2017)
                )
                if is_eval_season:
                    # Apply optional Weeks 1-3 exclusion for sensitivity fit
                    if not (exclude_weeks_1_3 and week in ("01", "02", "03")):
                        margin, prob = predict_param(
                            ratings,
                            mapped_game,
                            hfa=params["hfa"],
                            elo_per_point=params["elo_per_point"],
                        )
                        actual_margin = mapped_game["homePoints"] - mapped_game["awayPoints"]
                        actual_outcome = 1.0 if actual_margin > 0 else 0.0
                        predictions.append((margin, prob, actual_margin, actual_outcome))

                # Update ratings
                ratings = update_param(
                    ratings,
                    mapped_game,
                    hfa=params["hfa"],
                    elo_per_point=params["elo_per_point"],
                    k=params["k"],
                    mov_damping=params["mov_damping"],
                    mov_denominator_floor=params["mov_denominator_floor"],
                )

        prev_season = season

    # Calculate metrics
    if not predictions:
        return {
            "mae": float("inf"),
            "brier": 1.0,
            "total_games": 0,
            "seven_point_win_rate": 0.0,
            "seven_point_count": 0,
        }

    abs_errors = [abs(p[0] - p[2]) for p in predictions]
    brier_errors = [(p[1] - p[3]) ** 2 for p in predictions]

    mae = sum(abs_errors) / len(abs_errors)
    brier = sum(brier_errors) / len(brier_errors)

    # 7-Point Favorites observed win rate (predicted margin in absolute [6.5, 7.5])
    seven_point_games = []
    for pred_margin, _, actual_margin, _ in predictions:
        if 6.5 <= abs(pred_margin) <= 7.5:
            # Did the predicted favorite win?
            if pred_margin > 0:
                fav_won = (actual_margin > 0)
            else:
                fav_won = (actual_margin < 0)
            seven_point_games.append(1.0 if fav_won else 0.0)

    seven_point_win_rate = (
        sum(seven_point_games) / len(seven_point_games) if seven_point_games else 0.0
    )

    return {
        "mae": mae,
        "brier": brier,
        "total_games": len(predictions),
        "seven_point_win_rate": seven_point_win_rate,
        "seven_point_count": len(seven_point_games),
    }


def perform_grid_search(
    *,
    seasons,
    exclude_weeks_1_3=False,
    eval_seasons=None,
    fixed_regression=None,
    games_cache=None,
):
    """Grid search optimization of ELO parameters minimizing MAE on specified seasons."""
    # Coarser grid search spaces for extreme performance while covering full requested ranges
    elo_range = [12.0, 16.0, 20.0, 24.0]
    k_range = [10.0, 20.0, 30.0, 40.0]
    hfa_range = [1.0, 2.0, 3.0, 4.0]
    floor_range = [0.05, 0.25, 1.0]

    # REGRESSION_TO_MEAN: free (0.1 to 0.6) or pinned (1/3)
    if fixed_regression is not None:
        reg_range = [fixed_regression]
    else:
        reg_range = [0.2, 0.33, 0.5]

    best_mae = float("inf")
    best_params = None
    best_metrics = None

    # Constants to hold fixed
    mov_damping = 2.2

    for elo in elo_range:
        for k in k_range:
            for hfa in hfa_range:
                for floor in floor_range:
                    for reg in reg_range:
                        params = {
                            "elo_per_point": elo,
                            "k": k,
                            "mov_damping": mov_damping,
                            "mov_denominator_floor": floor,
                            "regression_to_mean": reg,
                            "hfa": hfa,
                        }
                        metrics = simulate_and_evaluate(
                            params,
                            seasons,
                            exclude_weeks_1_3=exclude_weeks_1_3,
                            eval_seasons=eval_seasons,
                            games_cache=games_cache,
                        )
                        if metrics["mae"] < best_mae:
                            best_mae = metrics["mae"]
                            best_params = params.copy()
                            best_metrics = metrics.copy()

    return best_params, best_metrics
