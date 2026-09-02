"""CLI entry point for cfb-model research commands.

Commands:
- `backfill`: Plan or execute historical CFBD snapshot backfill to S3/local store.
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from cfb.collectors.cfbd import CALL_BUDGET_PER_RUN, CfbdClient, http_fetch
from cfb.errors import CfbError
from cfb.storage import FileSnapshotStore, S3SnapshotStore, SnapshotStore
from cfb_model.backfill import (
    DEFAULT_RESOURCES,
    RESOURCE_DEFINITIONS,
    execute_backfill,
    format_backfill_plan,
    plan_backfill,
)

__all__ = ["DEFAULT_STORE", "build_parser", "main"]

DEFAULT_STORE = "s3://travispollard-cfb-data"
REGION = "us-east-1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cfb-model",
        description="College football research, fitting, and backfill CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. Backfill command
    bf = subparsers.add_parser("backfill", help="plan or execute CFBD historical backfill")
    _add_store_arg(bf)
    bf.add_argument(
        "--from",
        dest="from_season",
        type=int,
        help="start season (inclusive, e.g. 2024)",
    )
    bf.add_argument(
        "--to",
        dest="to_season",
        type=int,
        help="end season (inclusive, e.g. 2025)",
    )
    bf.add_argument(
        "--season",
        type=int,
        help="single target season (alternative to --from / --to)",
    )
    bf.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="inspect plan and estimated call budget without fetching or modifying store",
    )
    bf.add_argument(
        "--budget",
        type=int,
        default=CALL_BUDGET_PER_RUN,
        help=f"per-run call budget limit (default: {CALL_BUDGET_PER_RUN})",
    )
    bf.add_argument(
        "--resources",
        nargs="+",
        choices=list(RESOURCE_DEFINITIONS.keys()),
        default=list(DEFAULT_RESOURCES),
        help="specific CFBD resources to backfill",
    )
    bf.add_argument(
        "--no-postseason",
        action="store_true",
        default=False,
        help="exclude postseason week partition from week-scoped resources",
    )

    # 2. Fit command (parameter fitting & optimization)
    fit = subparsers.add_parser("fit", help="perform parameter fitting or grid searches")
    fit_subs = fit.add_subparsers(dest="subcommand", required=True)

    # Fit Elo command
    elo = fit_subs.add_parser("elo", help="perform grid search parameter fitting for the Elo model")
    elo.add_argument(
        "--seasons",
        default="2017-2023",
        help="comma-separated seasons or hyphen-separated ranges for fitting (default: 2017-2023)",
    )

    # Fit Ridge command
    ridge = fit_subs.add_parser("ridge", help="perform walk-forward fitting for the Ridge regression model")
    ridge.add_argument(
        "--seasons",
        default="2017-2023",
        help="comma-separated training seasons or hyphen-separated ranges (default: 2017-2023)",
    )

    # 3. Models command (bake-off json generator)
    models = subparsers.add_parser("models", help="generate models.json for the prediction bake-off")
    models.add_argument(
        "--season",
        type=int,
        default=2025,
        help="evaluate the specified season for the bake-off (default: 2025)",
    )
    models.add_argument(
        "--store",
        help="S3 bucket URL (e.g. s3://travispollard-cfb-data) or empty for local save",
    )

    # 4. Report command (static html report renderer)
    subparsers.add_parser("report", help="render the local standalone HTML diagnostic report")

    return parser


def _add_store_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--store",
        default=DEFAULT_STORE,
        metavar="URL",
        help=f"s3://bucket or file://path (default: {DEFAULT_STORE})",
    )


def resolve_store(url: str) -> SnapshotStore:
    """Resolve store URI to SnapshotStore instance."""
    parsed = urlparse(url)
    if parsed.scheme == "s3":
        return S3SnapshotStore(parsed.netloc, REGION)
    if parsed.scheme == "file":
        return FileSnapshotStore(Path(parsed.netloc + parsed.path))
    raise ValueError(f"--store must be s3:// or file://, got {url!r}")


def _dispatch_backfill(args: argparse.Namespace, *, now: datetime | None = None) -> int:
    # Determine seasons
    if args.season is not None:
        seasons = [args.season]
    elif args.from_season is not None and args.to_season is not None:
        if args.from_season > args.to_season:
            raise ValueError(f"--from ({args.from_season}) cannot exceed --to ({args.to_season})")
        seasons = list(range(args.from_season, args.to_season + 1))
    elif args.from_season is not None:
        seasons = [args.from_season]
    elif args.to_season is not None:
        seasons = [args.to_season]
    else:
        # Pilot Scope: Default to a pilot backfill configuration for seasons 2024–2025 (~90 calls)
        seasons = [2024, 2025]
        print(
            "No seasons specified. Defaulting to pilot backfill configuration "
            "for seasons 2024–2025."
        )

    if 2020 in seasons:
        seasons.remove(2020)
        print("Season 2020 is excluded as a structural break (SPEC-phase2 §3.2).")

    store = resolve_store(args.store)
    include_postseason = not args.no_postseason

    # 1. Plan
    plan = plan_backfill(
        store=store,
        seasons=seasons,
        resources=args.resources,
        include_postseason=include_postseason,
        ignore_store_errors=args.dry_run,
    )

    # 2. Output plan / Dry Run
    plan_text = format_backfill_plan(plan, store_uri=args.store)
    print(plan_text)

    if args.dry_run:
        return 0

    if not plan.outstanding:
        print("\nAll target snapshots already exist in store. Nothing to fetch.")
        return 0

    # 3. Live Execution
    print(f"\nProceeding with live fetch (Budget: {args.budget} calls)...")
    client = CfbdClient(fetch=http_fetch(), budget=args.budget)

    def _progress(item, idx, total):
        print(
            f"[{idx}/{total}] Fetching {item.season} week={item.week} "
            f"{item.resource} ({item.path})..."
        )

    result = execute_backfill(
        store=store,
        client=client,
        plan=plan,
        max_calls=args.budget,
        now=now,
        progress_callback=_progress,
    )

    print("\nBackfill Run Complete:")
    print(f"  - Snapshots Written: {result.fetched_count}")
    print(f"  - Total Bytes:       {result.bytes_written:,} bytes")
    print(f"  - Calls Spent:       {client.calls_made}/{args.budget}")

    if result.errors:
        print("\nErrors encountered:")
        for item, err in result.errors:
            print(f"  - {item.season} week={item.week} {item.resource}: {err}")
        return 1

    return 0


def parse_seasons(seasons_str: str) -> list[int]:
    """Parse a range or list of seasons (e.g. '2017-2023' or '2017,2018')."""
    seasons = []
    for part in seasons_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = map(int, part.split("-"))
            seasons.extend(range(start, end + 1))
        else:
            seasons.append(int(part))
    if 2020 in seasons:
        seasons.remove(2020)
    return sorted(list(set(seasons)))


def _dispatch_fit_elo(args: argparse.Namespace, *, now: datetime | None = None) -> int:
    import json

    from cfb_model.fit.elo import load_all_games, perform_grid_search, simulate_and_evaluate

    seasons = parse_seasons(args.seasons)
    print(f"Running Elo grid search on fit window: {seasons}")

    # Walk-forward simulation includes burn-in seasons 2015-2016 to initialize rating state
    all_seasons = sorted(list(set([2015, 2016] + seasons)))
    print(f"Total walk-forward simulation timeline (including burn-in 2015-2016): {all_seasons}")

    # Pre-load games cache in memory to completely bypass disk reads during grid search loops
    print("\nPre-loading raw games into memory cache...")
    games_cache = load_all_games(sorted(list(set(all_seasons + [2024, 2025]))))
    print(f"Loaded {len(games_cache)} seasons of games successfully.")

    # 1. Free Regression-to-Mean search
    print("\n--- Phase 1: Grid Search with FREE Regression to Mean ---")
    best_free, metrics_free = perform_grid_search(seasons=all_seasons, games_cache=games_cache)
    print(f"Best Free Params: {best_free}")
    print(f"Metrics (MAE: {metrics_free['mae']:.4f}, Brier: {metrics_free['brier']:.4f})")

    # 2. Pinned Regression-to-Mean search (pinned at 1/3)
    print("\n--- Phase 2: Grid Search with PINNED Regression to Mean (1/3) ---")
    best_pinned, metrics_pinned = perform_grid_search(
        seasons=all_seasons,
        fixed_regression=1.0 / 3.0,
        games_cache=games_cache,
    )
    print(f"Best Pinned Params: {best_pinned}")
    print(f"Metrics (MAE: {metrics_pinned['mae']:.4f}, Brier: {metrics_pinned['brier']:.4f})")

    # 3. Decision test: Did other constants move materially?
    # Thresholds for "material" change:
    # elo_per_point > 2.0, k > 5.0, hfa > 0.5, floor > 0.2
    material_change = (
        abs(best_free["elo_per_point"] - best_pinned["elo_per_point"]) > 2.0 or
        abs(best_free["k"] - best_pinned["k"]) > 5.0 or
        abs(best_free["hfa"] - best_pinned["hfa"]) > 0.5 or
        abs(best_free["mov_denominator_floor"] - best_pinned["mov_denominator_floor"]) > 0.2
    )

    if not material_change:
        print("\n[Decision] Pinned regression parameter is selected because the other constants")
        print(
            "           did not move materially between free and pinned runs "
            "(avoiding overfitting the 2020 gap)."
        )
        optimal_params = best_pinned
        optimal_metrics = metrics_pinned
        reg_mode = "pinned"
    else:
        print(
            "\n[Decision] Free regression parameter is selected "
            "because other constants moved materially."
        )
        optimal_params = best_free
        optimal_metrics = metrics_free
        reg_mode = "free"

    # 4. Sensitivity Fit (excluding Weeks 1-3)
    print("\n--- Phase 3: Run Sensitivity Fit (Excluding Weeks 1-3) ---")
    fixed_reg = 1.0 / 3.0 if reg_mode == "pinned" else None
    sensitivity_params, sensitivity_metrics = perform_grid_search(
        seasons=all_seasons,
        exclude_weeks_1_3=True,
        fixed_regression=fixed_reg,
        games_cache=games_cache,
    )
    print(f"Best Sensitivity Params: {sensitivity_params}")
    print(
        f"Sensitivity Metrics (MAE: {sensitivity_metrics['mae']:.4f}, "
        f"Brier: {sensitivity_metrics['brier']:.4f})"
    )

    # 5. Held-Out Evaluation (2024-2025)
    # Includes all seasons to build rating state sequentially, but only evaluates on [2024, 2025]
    heldout_timeline = sorted(list(set(all_seasons + [2024, 2025])))
    print("\n--- Phase 4: Evaluate on Held-Out Validation Seasons (2024-2025) ---")
    heldout_metrics = simulate_and_evaluate(
        optimal_params,
        heldout_timeline,
        eval_seasons=[2024, 2025],
        games_cache=games_cache,
    )
    print(
        f"Held-Out Metrics (MAE: {heldout_metrics['mae']:.4f}, "
        f"Brier: {heldout_metrics['brier']:.4f})"
    )
    print(f"7-Point Favorite Win Rate on held-out: {heldout_metrics['seven_point_win_rate']:.2%}")

    # Build the tracking JSON output
    moment_obj = now or datetime.now(UTC)
    result_data = {
        "optimizer": "grid_search",
        "generated_at": moment_obj.isoformat(),
        "fit_window": {
            "seasons": seasons,
            "burn_in_seasons": [2015, 2016],
        },
        "regression_mode": reg_mode,
        "optimal_params": optimal_params,
        "training_metrics": optimal_metrics,
        "sensitivity_fit": {
            "optimal_params": sensitivity_params,
            "metrics": sensitivity_metrics,
        },
        "held_out_metrics": {
            "seasons": [2024, 2025],
            "mae": heldout_metrics["mae"],
            "brier": heldout_metrics["brier"],
            "seven_point_win_rate": heldout_metrics["seven_point_win_rate"],
            "seven_point_count": heldout_metrics["seven_point_count"],
        },
    }

    # Save to experiments directory
    exp_dir = Path("research/experiments")
    exp_dir.mkdir(parents=True, exist_ok=True)
    filename = f"elo-{moment_obj.strftime('%Y-%m-%dT%H%MZ')}.json"
    filepath = exp_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)

    print(f"\nOptimal constants written successfully to {filepath}")
    return 0


def _dispatch_fit_ridge(args: argparse.Namespace, *, now: datetime | None = None) -> int:
    import json

    import numpy as np

    from cfb_model.fit.features import build_season_feature_matrix
    from cfb_model.fit.ridge import (
        calculate_calibration_slope,
        fit_walk_forward_ridge,
        get_elo_predictions_for_eval,
    )

    train_seasons = parse_seasons(args.seasons)
    eval_seasons = [2024, 2025]
    print(f"Running Ridge model fitting on training window: {train_seasons}")
    print(f"Evaluation window: {eval_seasons}")

    # Walk-forward timeline
    all_timeline = sorted(list(set([2015, 2016] + train_seasons + eval_seasons)))
    print(f"Extracting features across full walk-forward timeline: {all_timeline}")

    features_by_season = {}
    for season in all_timeline:
        print(f"  - Extracting features for season {season}...")
        features_by_season[season] = build_season_feature_matrix(season)

    # 1. Fit and evaluate Ridge walk-forward models
    print("\nFitting walk-forward Ridge regression models...")
    ridge_res = fit_walk_forward_ridge(
        train_seasons=train_seasons,
        eval_seasons=eval_seasons,
        features_by_season=features_by_season,
        elo_per_point=16.0,
    )

    # 2. Get Elo predictions for the same evaluation seasons [2024, 2025]
    print("Generating walk-forward Elo baseline predictions for evaluation...")
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
        eval_seasons=eval_seasons,
        params=optimal_elo_params,
    )

    # 3. Find the exact intersection of games both predicted
    aligned_ridge_margins = []
    aligned_elo_margins = []
    aligned_actual_margins = []

    aligned_ridge_probs = []
    aligned_elo_probs = []
    aligned_outcomes = []

    intersection_predictions = []

    for r_pred in ridge_res["predictions"]:
        game_id = r_pred["game_id"]
        if game_id in elo_preds:
            e_pred = elo_preds[game_id]

            aligned_ridge_margins.append(r_pred["pred_margin"])
            aligned_elo_margins.append(e_pred["pred_margin"])
            aligned_actual_margins.append(r_pred["actual_margin"])

            aligned_ridge_probs.append(r_pred["pred_prob"])
            aligned_elo_probs.append(e_pred["pred_prob"])
            aligned_outcomes.append(r_pred["actual_outcome"])

            intersection_predictions.append({
                "game_id": game_id,
                "season": r_pred["season"],
                "week": r_pred["week"],
                "home_team": r_pred["home_team"],
                "away_team": r_pred["away_team"],
                "ridge_pred_margin": r_pred["pred_margin"],
                "ridge_pred_prob": r_pred["pred_prob"],
                "elo_pred_margin": e_pred["pred_margin"],
                "elo_pred_prob": e_pred["pred_prob"],
                "actual_margin": r_pred["actual_margin"],
                "actual_outcome": r_pred["actual_outcome"],
            })

    print(f"\nAligned intersection predictions: {len(intersection_predictions)} games.")
    if not intersection_predictions:
        print("Error: Aligned intersection is empty.")
        return 1

    # Convert to numpy arrays for calculation
    ridge_m_np = np.array(aligned_ridge_margins)
    elo_m_np = np.array(aligned_elo_margins)
    actual_m_np = np.array(aligned_actual_margins)

    ridge_p_np = np.array(aligned_ridge_probs)
    elo_p_np = np.array(aligned_elo_probs)
    outcomes_np = np.array(aligned_outcomes)

    # 4. Calculate metrics on the intersection
    ridge_mae = float(np.mean(np.abs(ridge_m_np - actual_m_np)))
    elo_mae = float(np.mean(np.abs(elo_m_np - actual_m_np)))

    ridge_brier = float(np.mean((ridge_p_np - outcomes_np) ** 2))
    elo_brier = float(np.mean((elo_p_np - outcomes_np) ** 2))

    ridge_slope = calculate_calibration_slope(ridge_p_np, outcomes_np)
    elo_slope = calculate_calibration_slope(elo_p_np, outcomes_np)

    # 5. Evaluate the Gate (SPEC-phase2 §5.6)
    mae_passed = ridge_mae < elo_mae
    brier_passed = ridge_brier <= (elo_brier * 1.02)
    slope_passed = 0.90 <= ridge_slope <= 1.10
    gate_passed = mae_passed and brier_passed and slope_passed

    print("\n=======================================================")
    print("THE GATE EVALUATION")
    print("=======================================================")
    print(f"Ridge MAE:          {ridge_mae:.4f}  | Elo MAE:          {elo_mae:.4f}  | Passed: {mae_passed}")
    print(f"Ridge Brier:        {ridge_brier:.4f}  | Elo Brier:        {elo_brier:.4f}  | Passed: {brier_passed}")
    print(f"Ridge Calibration:  {ridge_slope:.4f}  | Elo Calibration:  {elo_slope:.4f}  | Passed: {slope_passed}")
    print("-------------------------------------------------------")
    print(f"OVERALL GATE VERDICT: {'PASSED' if gate_passed else 'FAILED'}")
    print("=======================================================")

    # 6. Save results
    moment_obj = now or datetime.now(UTC)
    result_data = {
        "model": "ridge_regression",
        "generated_at": moment_obj.isoformat(),
        "train_window": {
            "seasons": train_seasons,
            "burn_in_seasons": [2015, 2016],
        },
        "evaluation_window": {
            "seasons": eval_seasons,
            "aligned_games": len(intersection_predictions),
        },
        "gate_evaluation": {
            "verdict": "passed" if gate_passed else "failed",
            "mae_passed": bool(mae_passed),
            "brier_passed": bool(brier_passed),
            "slope_passed": bool(slope_passed),
        },
        "ridge_metrics": {
            "mae": ridge_mae,
            "brier": ridge_brier,
            "calibration_slope": ridge_slope,
        },
        "elo_metrics": {
            "mae": elo_mae,
            "brier": elo_brier,
            "calibration_slope": elo_slope,
        },
        "predictions": intersection_predictions,
    }

    exp_dir = Path("research/experiments")
    exp_dir.mkdir(parents=True, exist_ok=True)
    filename = f"ridge-{moment_obj.strftime('%Y-%m-%dT%H%MZ')}.json"
    filepath = exp_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)

    print(f"\nRidge regression experiment results written successfully to {filepath}")
    return 0


def _dispatch_models(args: argparse.Namespace, *, now: datetime | None = None) -> int:
    from cfb_model.publish.models import generate_models_json

    print(f"Generating models.json for season {args.season}...")
    try:
        generate_models_json(args.season, store_uri=args.store)
        return 0
    except Exception as exc:
        print(f"Error generating models.json: {exc}", file=sys.stderr)
        return 1


def _dispatch_report(args: argparse.Namespace, *, now: datetime | None = None) -> int:
    from cfb_model.publish.report import generate_html_report

    print("Generating local standalone HTML diagnostic report...")
    try:
        generate_html_report()
        return 0
    except Exception as exc:
        print(f"Error generating diagnostic report: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    """Run CLI command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    moment = now or datetime.now(UTC)

    try:
        if args.command == "backfill":
            return _dispatch_backfill(args, now=moment)
        elif args.command == "fit":
            if args.subcommand == "elo":
                return _dispatch_fit_elo(args, now=moment)
            elif args.subcommand == "ridge":
                return _dispatch_fit_ridge(args, now=moment)
        elif args.command == "models":
            return _dispatch_models(args, now=moment)
        elif args.command == "report":
            return _dispatch_report(args, now=moment)
        parser.error(f"unknown command {args.command}")
        return 2
    except (CfbError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
