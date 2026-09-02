"""Ridge regression modeling, walk-forward training, and gate evaluation (SPEC-phase2 §5)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LinearRegression, Ridge

from cfb_model.crosswalk import load as load_crosswalk
from cfb_model.elo.seed import seed_history
from cfb_model.elo.state import EloModel, EloState
from cfb_model.fit.elo import load_all_games, predict_param, update_param

FEATURE_KEYS = [
    "diff_off_ppa",
    "diff_def_ppa",
    "diff_off_sr",
    "diff_def_sr",
    "diff_off_exp",
    "diff_def_exp",
    "talent_diff_decayed",
    "neutral_site",
    "home_indicator",
]


def calculate_calibration_slope(probs: np.ndarray, outcomes: np.ndarray, num_buckets: int = 10) -> float:
    """Calculate the calibration slope of actual outcomes regressed on predicted probabilities across buckets."""
    buckets = np.linspace(0.0, 1.0, num_buckets + 1)
    xs = []
    ys = []

    for i in range(num_buckets):
        low = buckets[i]
        high = buckets[i + 1]

        # Handle inclusive bounds for edge cases
        if i == 0:
            mask = (probs >= low) & (probs <= high)
        else:
            mask = (probs > low) & (probs <= high)

        if np.sum(mask) > 0:
            xs.append(np.mean(probs[mask]))
            ys.append(np.mean(outcomes[mask]))

    if len(xs) < 2:
        return 1.0

    lr = LinearRegression()
    lr.fit(np.array(xs).reshape(-1, 1), np.array(ys))
    return float(lr.coef_[0])


def evaluate_predictions(pred_margins: np.ndarray, actual_margins: np.ndarray, elo_per_point: float = 16.0) -> dict:
    """Compute MAE, Brier Score, and Calibration Slope from predicted margins and actual outcomes."""
    pred_probs = 1.0 / (1.0 + 10.0 ** (-(pred_margins * elo_per_point) / 400.0))
    actual_outcomes = np.where(actual_margins > 0, 1.0, 0.0)

    mae = float(np.mean(np.abs(pred_margins - actual_margins)))
    brier = float(np.mean((pred_probs - actual_outcomes) ** 2))
    slope = calculate_calibration_slope(pred_probs, actual_outcomes)

    return {
        "mae": mae,
        "brier": brier,
        "calibration_slope": slope,
        "total_games": len(pred_margins),
    }


def fit_walk_forward_ridge(
    train_seasons: list[int],
    eval_seasons: list[int],
    features_by_season: dict[int, list[dict]],
    elo_per_point: float = 16.0,
) -> dict:
    """Perform walk-forward Ridge fitting with temporal alpha-selection on training set."""
    alpha_candidates = [0.1, 1.0, 10.0, 100.0, 1000.0, 5000.0, 10000.0]

    all_eval_predictions = []  # List of dicts with predictions for eval seasons

    for eval_season in eval_seasons:
        # Seasons used for training: strictly < eval_season
        seasons_for_train = [s for s in train_seasons if s < eval_season]

        if not seasons_for_train:
            continue

        # Alpha Selection: Find the last season of our training set to use as validation set
        val_season = max(seasons_for_train)
        subtrain_seasons = [s for s in seasons_for_train if s < val_season]

        best_alpha = 100.0  # Safe default fallback
        if subtrain_seasons:
            # Build sub-training set
            X_subtrain, y_subtrain = [], []
            for s in subtrain_seasons:
                for row in features_by_season.get(s, []):
                    X_subtrain.append([row[k] for k in FEATURE_KEYS])
                    y_subtrain.append(row["actual_margin"])

            # Build validation set
            X_val, y_val = [], []
            for row in features_by_season.get(val_season, []):
                X_val.append([row[k] for k in FEATURE_KEYS])
                y_val.append(row["actual_margin"])

            X_subtrain_np, y_subtrain_np = np.array(X_subtrain), np.array(y_subtrain)
            X_val_np, y_val_np = np.array(X_val), np.array(y_val)

            best_val_mae = float("inf")
            for alpha in alpha_candidates:
                model = Ridge(alpha=alpha)
                model.fit(X_subtrain_np, y_subtrain_np)
                preds = model.predict(X_val_np)
                mae = float(np.mean(np.abs(preds - y_val_np)))
                if mae < best_val_mae:
                    best_val_mae = mae
                    best_alpha = alpha

        # Train final model for eval_season using the selected optimal alpha on full seasons_for_train
        X_train, y_train = [], []
        for s in seasons_for_train:
            for row in features_by_season.get(s, []):
                X_train.append([row[k] for k in FEATURE_KEYS])
                y_train.append(row["actual_margin"])

        X_train_np, y_train_np = np.array(X_train), np.array(y_train)

        final_model = Ridge(alpha=best_alpha)
        final_model.fit(X_train_np, y_train_np)

        # Predict for the eval_season
        eval_rows = features_by_season.get(eval_season, [])
        for row in eval_rows:
            x_feat = np.array([[row[k] for k in FEATURE_KEYS]])
            pred_margin = float(final_model.predict(x_feat)[0])
            pred_prob = 1.0 / (1.0 + 10.0 ** (-(pred_margin * elo_per_point) / 400.0))

            all_eval_predictions.append({
                "game_id": row["game_id"],
                "season": eval_season,
                "week": row["week"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "pred_margin": pred_margin,
                "pred_prob": pred_prob,
                "actual_margin": row["actual_margin"],
                "actual_outcome": row["actual_outcome"],
                "selected_alpha": best_alpha,
            })

    return {
        "predictions": all_eval_predictions,
        "features": FEATURE_KEYS,
    }


def get_elo_predictions_for_eval(
    all_seasons: list[int],
    eval_seasons: list[int],
    params: dict,
    raw_dir: Path = Path("research/raw/cfbd"),
) -> dict[int, dict]:
    """Simulate walk-forward Elo and capture predictions specifically for all completed games in the evaluation seasons."""
    ratings = {}
    prev_season = None

    elo_predictions = {}  # game_id -> prediction dict

    weeks = [
        "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15",
        "postseason"
    ]

    games_cache = load_all_games(all_seasons, raw_dir=raw_dir)

    for season in all_seasons:
        if prev_season is None:
            ratings = seed_history(None, raw_dir=raw_dir)
        else:
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

        if season not in games_cache:
            continue

        # Load crosswalk to get raw game IDs and homeTeam/awayTeam
        try:
            cw = load_crosswalk(season)
        except Exception:
            continue

        for week in weeks:
            # We must load raw game data to get actual CFBD game IDs (so we can align by ID!)
            games_dir = raw_dir / f"season={season}" / f"week={week}" / "games"
            if not games_dir.exists():
                continue

            json_files = [f for f in games_dir.glob("*.json") if not f.name.endswith(".meta.json")]
            if not json_files:
                continue

            with open(json_files[0], encoding="utf-8") as f:
                games_data = json.load(f)

            sorted_games = sorted(games_data, key=lambda g: g.get("startDate", ""))

            for game in sorted_games:
                if not game.get("completed") or game.get("homePoints") is None or game.get("awayPoints") is None:
                    continue
                if game["homePoints"] == game["awayPoints"]:
                    continue

                try:
                    home_canonical = cw.from_cfbd(game["homeTeam"])
                    away_canonical = cw.from_cfbd(game["awayTeam"])
                except Exception:
                    continue

                mapped_game = {
                    "homeTeam": home_canonical,
                    "awayTeam": away_canonical,
                    "homePoints": game["homePoints"],
                    "awayPoints": game["awayPoints"],
                    "neutralSite": game.get("neutralSite", False),
                }

                # Evaluate and capture prediction if in eval seasons
                if season in eval_seasons:
                    margin, prob = predict_param(
                        ratings,
                        mapped_game,
                        hfa=params["hfa"],
                        elo_per_point=params["elo_per_point"],
                    )
                    elo_predictions[game["id"]] = {
                        "game_id": game["id"],
                        "season": season,
                        "week": week,
                        "pred_margin": margin,
                        "pred_prob": prob,
                        "actual_margin": mapped_game["homePoints"] - mapped_game["awayPoints"],
                    }

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

    return elo_predictions
