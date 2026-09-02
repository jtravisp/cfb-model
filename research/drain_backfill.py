"""Helper script to repeatedly invoke the CFBD backfill CLI until all items are fetched.

This allows us to respect the per-run budget guardrail while fully automatedly
draining the ~459 outstanding calls across 2016-2025 (excluding 2020).
"""

import os
import subprocess
import sys
import time


def main() -> None:
    # Build environment dictionary to ensure AWS profile and pythonpath are set correctly
    env = os.environ.copy()
    env["AWS_PROFILE"] = "tp-site"
    env["PYTHONPATH"] = "src"

    command = [
        "uv",
        "run",
        "python",
        "-m",
        "cfb_model.cli",
        "backfill",
        "--from",
        "2016",
        "--to",
        "2025",
    ]

    print("Starting automated backfill drain for seasons 2016-2025...")
    print(f"Command: {' '.join(command)}")

    attempt = 1
    while True:
        print(f"\n=== Running Backfill Batch #{attempt} ===")
        # Run command and capture stdout/stderr to inspect output
        res = subprocess.run(command, capture_output=True, text=True, env=env)

        # Print stdout to the terminal so we can see progress
        print(res.stdout)
        if res.stderr:
            print(res.stderr, file=sys.stderr)

        # Check if we finished
        if "Nothing to fetch" in res.stdout or "All target snapshots already exist in store" in res.stdout:
            print("\nSuccess: No outstanding calls remaining. Backfill is fully drained and up to date!")
            break

        # Extract Snapshots Written from stdout
        snapshots_written = 0
        for line in res.stdout.splitlines():
            if "Snapshots Written:" in line:
                try:
                    snapshots_written = int(line.split(":")[-1].strip())
                except ValueError:
                    pass

        if res.returncode != 0:
            # If we wrote some snapshots, we made progress, so we can continue!
            if snapshots_written > 0:
                print(
                    f"\n[Warning] Batch exited with code {res.returncode} but successfully wrote "
                    f"{snapshots_written} snapshots. Continuing to next batch..."
                )
            else:
                print(f"Error: Backfill exited with code {res.returncode} and made no progress. Stopping drain.")
                sys.exit(res.returncode)

        # Safety pause between batches
        print("Batch complete. Pausing for 1 second before the next batch...")
        time.sleep(1)
        attempt += 1


if __name__ == "__main__":
    main()
