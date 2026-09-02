"""Script to dynamically generate historical crosswalk files (teams-YYYY.yaml) for 2015-2025.

It parses our synced teams raw snapshots locally, extracts the FBS teams, slugifies
their names to mint canonical IDs, and outputs YAMLs with sources: [cfbd].
"""

import json
import re
from pathlib import Path

import yaml


def slugify(name: str) -> str:
    """Standard slugification helper matching project conventions."""
    s = name.lower()
    s = s.replace(" & ", "-and-")
    s = re.sub(r"[\s/_.]+", "-", s)
    s = re.sub(r"[^a-z0-9\-]+", "", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def main() -> None:
    raw_dir = Path("research/raw/cfbd")
    out_dir = Path("data/crosswalk")
    out_dir.mkdir(parents=True, exist_ok=True)

    target_seasons = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]

    print("Generating baseline historical team crosswalks...")

    for season in target_seasons:
        teams_dir = raw_dir / f"season={season}" / "week=season" / "teams"
        if not teams_dir.exists():
            print(f"[Warning] No teams directory found for season {season}. Skipping.")
            continue

        json_files = [f for f in teams_dir.glob("*.json") if not f.name.endswith(".meta.json")]
        if not json_files:
            print(f"[Warning] No teams JSON snapshot found for season {season}. Skipping.")
            continue

        print(f"Processing season {season} from {json_files[0].name}...")
        with open(json_files[0], encoding="utf-8") as f:
            teams_data = json.load(f)

        fbs_teams = {}
        for team in teams_data:
            if team.get("classification") == "fbs":
                school = team["school"]
                slug = slugify(school)
                fbs_teams[slug] = {
                    "cfbd": school,
                    "division": "FBS",
                }

        # Sort teams alphabetically by canonical ID to keep YAML neat
        sorted_teams = {k: fbs_teams[k] for k in sorted(fbs_teams.keys())}

        output_data = {
            "season": season,
            "sources": ["cfbd"],
            "teams": sorted_teams,
        }

        output_file = out_dir / f"teams-{season}.yaml"
        # Write custom YAML formatted cleanly with safe_dump
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(output_data, f, sort_keys=False, default_flow_style=False)

        print(f"  -> Generated {output_file.name} with {len(sorted_teams)} FBS teams.")

    print("\nHistorical crosswalks seeding complete!")


if __name__ == "__main__":
    main()
