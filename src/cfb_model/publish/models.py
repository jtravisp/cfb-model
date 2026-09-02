"""Bake-off models.json generator (SPEC-phase2 §6)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

from cfb_model.crosswalk import load as load_crosswalk
from cfb_model.fit.features import build_season_feature_matrix
from cfb_model.fit.ridge import fit_walk_forward_ridge, get_elo_predictions_for_eval


def load_market_lines(season: int, cw, raw_dir: Path = Path("research/raw/cfbd")) -> dict[int, float]:
    """Load point spreads from raw lines snapshots by game ID."""
    market_lines = {}
    weeks = [
        "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15",
        "postseason"
    ]

    for week in weeks:
        lines_dir = raw_dir / f"season={season}" / f"week={week}" / "lines"
        if not lines_dir.exists():
            continue

        json_files = [f for f in lines_dir.glob("*.json") if not f.name.endswith(".meta.json")]
        if not json_files:
            continue

        with open(json_files[0], encoding="utf-8") as f:
            data = json.load(f)

        for game in data:
            if game.get("homeScore") is None or game.get("awayScore") is None:
                continue

            lines = game.get("lines") or []
            if not lines:
                continue

            # Select consensus spread, fallback to first
            spread = None
            for line in lines:
                if line.get("provider") == "consensus":
                    spread = line.get("spread")
                    break
            if spread is None:
                spread = lines[0].get("spread")

            if spread is not None:
                market_lines[game["id"]] = float(spread)

    return market_lines


def calculate_ats_record(predictions: list[dict], system_id: str) -> dict:
    """Calculate the Against the Spread (ATS) record for a given model system."""
    wins = 0
    losses = 0
    pushes = 0
    excluded_no_edge = 0

    for p in predictions:
        spread = p["market_spread"]
        pred_margin = p[f"{system_id}_pred_margin"]
        actual_margin = p["actual_margin"]

        # Market spread favorite value is negative (e.g. -7 means Home favored by 7).
        # We bet on Home to cover if predicted margin is greater than the market's expected margin (-spread).
        # i.e., predicted_margin + spread > 0
        expected_home_margin = -spread

        if pred_margin > expected_home_margin:
            # Bet Home
            if actual_margin > expected_home_margin:
                wins += 1
            elif actual_margin < expected_home_margin:
                losses += 1
            else:
                pushes += 1
        elif pred_margin < expected_home_margin:
            # Bet Away
            if actual_margin < expected_home_margin:
                wins += 1
            elif actual_margin > expected_home_margin:
                losses += 1
            else:
                pushes += 1
        else:
            # No edge (exact agreement with line)
            excluded_no_edge += 1

    return {
        "record": f"{wins}-{losses}-{pushes}",
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "excluded_no_line": 0,
        "excluded_no_edge": excluded_no_edge,
    }


def generate_models_json(
    season: int,
    store_uri: str | None = None,
    raw_dir: Path = Path("research/raw/cfbd"),
) -> dict:
    """Evaluate and compile the bake-off models.json document for a given season on the game intersection."""
    # Timeline includes burn-in to ensure proper Ratings starting state
    all_timeline = sorted(list(set([2015, 2016] + list(range(2017, season + 1)))))
    if 2020 in all_timeline:
        all_timeline.remove(2020)

    try:
        cw = load_crosswalk(season)
    except Exception as exc:
        raise ValueError(f"Crosswalk file missing for season {season}: {exc}") from None

    # Load pre-computed features and predictions
    print(f"Loading feature matrices and walk-forward predictions for season {season}...")
    features_by_season = {}
    for s in all_timeline:
        features_by_season[s] = build_season_feature_matrix(s, raw_dir=raw_dir)

    # Ridge walk-forward predictions
    ridge_res = fit_walk_forward_ridge(
        train_seasons=list(range(2017, season)),
        eval_seasons=[season],
        features_by_season=features_by_season,
        elo_per_point=16.0,
    )

    # Elo walk-forward predictions
    optimal_elo_params = {
        "elo_per_point": 16.0,
        "k": 30.0,
        "mov_damping": 2.2,
        "mov_denominator_floor": 0.05,
        "regression_to_mean": 1.0 / 3.0,
        "hfa": 3.0,
    }
    elo_preds = get_elo_predictions_for_eval(
        all_seasons=all_timeline,
        eval_seasons=[season],
        params=optimal_elo_params,
        raw_dir=raw_dir,
    )

    # Market lines
    market_lines = load_market_lines(season, cw, raw_dir=raw_dir)

    # Compute intersection of games predicted by all three available systems
    aligned_predictions = []
    for r_pred in ridge_res["predictions"]:
        game_id = r_pred["game_id"]
        if game_id in elo_preds and game_id in market_lines:
            e_pred = elo_preds[game_id]
            spread = market_lines[game_id]

            # Market predicted margin is -spread, prob is derived using standard elo logistic scale
            market_pred_margin = -spread
            market_pred_prob = 1.0 / (1.0 + 10.0 ** (-(market_pred_margin * 16.0) / 400.0))

            aligned_predictions.append({
                "game_id": game_id,
                "season": season,
                "week": r_pred["week"],
                "home_team": r_pred["home_team"],
                "away_team": r_pred["away_team"],
                "elo_pred_margin": e_pred["pred_margin"],
                "elo_pred_prob": e_pred["pred_prob"],
                "ridge_pred_margin": r_pred["pred_margin"],
                "ridge_pred_prob": r_pred["pred_prob"],
                "market_pred_margin": market_pred_margin,
                "market_pred_prob": market_pred_prob,
                "market_spread": spread,
                "actual_margin": r_pred["actual_margin"],
                "actual_outcome": r_pred["actual_outcome"],
            })

    if not aligned_predictions:
        raise ValueError(f"No game intersection found for season {season}.")

    print(f"Intersection of systems on season {season}: {len(aligned_predictions)} games.")

    # Calculate global metrics on the intersection for all systems
    systems_metrics = {}
    for sys_id in ["elo", "ridge", "market"]:
        margins = np.array([p[f"{sys_id}_pred_margin"] for p in aligned_predictions])
        probs = np.array([p[f"{sys_id}_pred_prob"] for p in aligned_predictions])
        actual_margins = np.array([p["actual_margin"] for p in aligned_predictions])
        outcomes = np.array([p["actual_outcome"] for p in aligned_predictions])

        mae = float(np.mean(np.abs(margins - actual_margins)))
        brier = float(np.mean((probs - outcomes) ** 2))

        # ATS record
        if sys_id == "market":
            ats = {
                "record": "0-0-0",
                "wins": 0,
                "losses": 0,
                "pushes": 0,
                "excluded_no_line": 0,
                "excluded_no_edge": len(aligned_predictions),
            }
        else:
            ats = calculate_ats_record(aligned_predictions, sys_id)

        systems_metrics[sys_id] = {
            "mae": mae,
            "brier": brier,
            "ats": ats,
        }

    # Group by week for by_week series
    by_week_data = []
    weeks_found = sorted(list(set(p["week"] for p in aligned_predictions)))

    for w_name in weeks_found:
        week_games = [p for p in aligned_predictions if p["week"] == w_name]
        week_mae = {}
        for sys_id in ["elo", "ridge", "market"]:
            w_margins = np.array([p[f"{sys_id}_pred_margin"] for p in week_games])
            w_actual_margins = np.array([p["actual_margin"] for p in week_games])
            week_mae[sys_id] = float(np.mean(np.abs(w_margins - w_actual_margins)))

        by_week_data.append({
            "week": w_name,
            "mae": week_mae,
        })

    # Construct the Schema V3 JSON document (§6.2)
    models_doc = {
        "schema_version": 3,
        "generated_at": datetime.now(UTC).isoformat() + "Z",
        "season": season,
        "through_week": max(weeks_found),
        "shared_denominator": {
            "games": len(aligned_predictions),
            "description": "games every system priced",
        },
        "systems": [
            {
                "id": "elo",
                "label": "This model (Elo)",
                "mae": systems_metrics["elo"]["mae"],
                "brier": systems_metrics["elo"]["brier"],
                "ats": systems_metrics["elo"]["ats"],
                "coverage": {
                    "priced": len(aligned_predictions),
                    "of": len(aligned_predictions),
                },
                "is_ours": True,
            },
            {
                "id": "ridge",
                "label": "This model (efficiency)",
                "mae": systems_metrics["ridge"]["mae"],
                "brier": systems_metrics["ridge"]["brier"],
                "ats": systems_metrics["ridge"]["ats"],
                "coverage": {
                    "priced": len(aligned_predictions),
                    "of": len(aligned_predictions),
                },
                "is_ours": True,
            },
            {
                "id": "market",
                "label": "The market",
                "mae": systems_metrics["market"]["mae"],
                "brier": systems_metrics["market"]["brier"],
                "ats": systems_metrics["market"]["ats"],
                "coverage": {
                    "priced": len(aligned_predictions),
                    "of": len(aligned_predictions),
                },
                "is_benchmark": True,
            },
        ],
        "by_week": by_week_data,
    }

    # Store models.json in either S3 or locally
    if store_uri and store_uri.startswith("s3://"):
        from cfb.storage import S3SnapshotStore
        parsed = urlparse(store_uri)
        bucket = parsed.netloc
        store = S3SnapshotStore(bucket, "us-east-1")
        key = "cfb/data/models.json"
        store.put_bytes(key, json.dumps(models_doc, indent=2).encode("utf-8"), "application/json")
        print(f"Bake-off document successfully uploaded to s3://{bucket}/{key}")
    else:
        # Save to research/derived/models.json
        derived_dir = Path("research/derived")
        derived_dir.mkdir(parents=True, exist_ok=True)
        models_path = derived_dir / "models.json"

        with open(models_path, "w", encoding="utf-8") as f:
            json.dump(models_doc, f, indent=2)

        print(f"Bake-off document successfully written to {models_path}")

    return models_doc
