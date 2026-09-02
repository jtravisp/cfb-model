"""Verification script to audit the integrity and completeness of the local raw mirror.

It checks the number of JSON files and manifests per season to ensure that
all 10 targeted seasons are fully synchronized, and that 2020 was excluded.
"""

from pathlib import Path


def main() -> None:
    raw_dir = Path("research/raw/cfbd")
    if not raw_dir.exists():
        print(f"Error: Directory {raw_dir} does not exist.")
        return

    print("=== Raw Mirror Synchronization Audit ===")

    # Define target seasons (excluding 2020)
    target_seasons = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
    all_seasons = sorted([int(p.name.split("=")[-1]) for p in raw_dir.glob("season=*")])

    total_data_files = 0
    total_manifest_files = 0
    error_count = 0

    for season in all_seasons:
        season_dir = raw_dir / f"season={season}"
        json_files = sorted(list(season_dir.glob("**/*.json")))

        data_files = [f for f in json_files if not f.name.endswith(".meta.json")]
        manifest_files = [f for f in json_files if f.name.endswith(".meta.json")]

        print(f"Season {season}:")
        print(f"  - Raw Data Snapshots: {len(data_files)}")
        print(f"  - Manifest Metadata:  {len(manifest_files)}")

        if season == 2020:
            print("  - ERROR: Season 2020 should have been excluded but files exist!")
            error_count += 1
        elif season in target_seasons:
            # We expect exactly 51 data snapshots and 51 metadata manifests
            if len(data_files) == 51 and len(manifest_files) == 51:
                print("  - Status: OK (100% complete - 51/51 snapshots)")
            else:
                print(f"  - WARNING: Expected 51 snapshots, found {len(data_files)}")
                error_count += 1
        else:
            print("  - Note: Extra/unplanned season found")

        total_data_files += len(data_files)
        total_manifest_files += len(manifest_files)

    print("\n=== Global Mirror Summary ===")
    print(f"Total Seasons Synchronized:  {len(all_seasons)} (2020 excluded successfully: {2020 not in all_seasons})")
    print(f"Total Unique Data Snapshots: {total_data_files}")
    print(f"Total Metadata Manifests:   {total_manifest_files}")
    print(f"Total JSON Files in Mirror:  {total_data_files + total_manifest_files}")

    # Count snapshots only within our target historical seasons
    target_data_files = 0
    target_manifest_files = 0
    for season in target_seasons:
        season_dir = raw_dir / f"season={season}"
        if season_dir.exists():
            target_data_files += len([f for f in season_dir.glob("**/*.json") if not f.name.endswith(".meta.json")])
            target_manifest_files += len([f for f in season_dir.glob("**/*.json") if f.name.endswith(".meta.json")])

    expected_snapshots = len(target_seasons) * 51
    if target_data_files == expected_snapshots and target_manifest_files == expected_snapshots and error_count == 0:
        print("\nPROVEN: Full backfill is 100% complete and verified locally with 0 errors!")
    else:
        print(f"\nAUDIT FAILED: Found {error_count} errors or unexpected snapshot counts (Expected {expected_snapshots} target snapshots, found {target_data_files}).")


if __name__ == "__main__":
    main()
