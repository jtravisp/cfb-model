"""Seeding Elo ratings for historical backfilled seasons (SPEC-phase2 §3.3)."""

import json
from pathlib import Path

from cfb_model.elo.state import EloState


def seed_history(
    previous: EloState | None,
    *,
    gap_seasons: int = 1,
    raw_dir: Path = Path("research/raw/cfbd"),
) -> dict[str, float]:
    """Preseason seeding logic for historical backfilled seasons (SPEC-phase2 §3.3).

    If previous is None, represents the cold start of 2015: return 1500.0 for all FBS teams.
    If previous exists: carry forward prior ratings, regressed to mean, and enter new FBS
    teams at 1500.0.
    """
    if previous is None:
        season = 2015
    else:
        season = previous.season + gap_seasons

    # Load list of FBS schools from raw teams snapshot if available
    fbs_teams = set()
    teams_dir = raw_dir / f"season={season}" / "week=season" / "teams"
    if teams_dir.exists():
        json_files = [f for f in teams_dir.glob("*.json") if not f.name.endswith(".meta.json")]
        if json_files:
            try:
                with open(json_files[0], encoding="utf-8") as f:
                    teams_data = json.load(f)
                    for team in teams_data:
                        if team.get("classification") == "fbs":
                            fbs_teams.add(team["school"])
            except Exception:
                pass

    if previous is None:
        # Cold start (e.g. 2015): return uniform 1500 for all FBS teams
        return {team: 1500.0 for team in sorted(fbs_teams)}

    # previous exists: regress previous ratings toward 1500
    REGRESSION_TO_MEAN = 1.0 / 3.0
    factor = (1.0 - REGRESSION_TO_MEAN) ** gap_seasons

    ratings = {}
    # Carry forward and regress existing ratings
    for team, r in previous.ratings.items():
        ratings[team] = 1500.0 + (r - 1500.0) * factor

    # Any new FBS team that was not rated in the previous state enters at 1500.0
    for team in fbs_teams:
        if team not in ratings:
            ratings[team] = 1500.0

    return ratings
