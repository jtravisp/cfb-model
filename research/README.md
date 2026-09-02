# College Football Model Research

This directory contains the local research, parameter fitting, feature engineering, and model evaluation workflow for college football game predictions.

The local workflow exists to enable rapid model iteration, backtesting, and diagnostic analysis without disturbing the live unattended pipeline running in `travispollard.com/cfb`.

---

## 1. AWS & Infrastructure Facts

- **AWS Account:** `679878703800`
- **AWS Region:** `us-east-1`
- **AWS CLI Profile:** `tp-site` (must be set per shell session via `export AWS_PROFILE=tp-site` or `$env:AWS_PROFILE="tp-site"`; do NOT use `jtravisp` which maps to a different account)
- **S3 Snapshot Bucket:** `s3://travispollard-cfb-data/`
- **Raw CFBD Prefix in S3:** `s3://travispollard-cfb-data/raw/cfbd/`
- **SSM Parameter for CFBD API Key:** `/travispollard/cfb/cfbd_api_key` (SecureString)

---

## 2. Directory Layout & Artifact Rules

```
research/
├── raw/            # GITIGNORED: Local mirror of S3 raw snapshots (s3://travispollard-cfb-data/raw/cfbd/)
├── derived/        # GITIGNORED: Intermediate caches (feature matrices, Elo states, replay tables)
├── experiments/    # TRACKED: Structured JSON results of fits, searches, and backtests
│   └── .gitkeep
├── reports/        # GITIGNORED: Rendered standalone HTML diagnostic reports
└── README.md       # TRACKED: This guide and running research log
```

- **`raw/`**: Mirror of S3. Authoritative immutable snapshots live in S3 to conserve CFBD API quota. Never modified directly.
- **`derived/`**: Disposable caches. Anything here can be recomputed deterministically from `raw/`.
- **`experiments/`**: Findings and proven model parameters. Every run writes a timestamped JSON document with hyperparameter provenance, training metrics, and held-out evaluation scores.
- **`reports/`**: Static HTML reports generated from `experiments/` for visual analysis (calibration tables, residual plots, scatter).

---

## 3. The Sync-Fit-Report Workflow Loop

```
+------------------+       aws s3 sync       +-------------------+
|  S3 Raw Snapshots| ----------------------> | Local Raw Mirror  |
|  (Authoritative) |                         | (research/raw/)   |
+------------------+                         +-------------------+
                                                       |
                                                       | local reads
                                                       v
+------------------+      report render      +-------------------+
|  Static HTML     | <---------------------- |   Fit / Search    |
| (research/reports)                          | (experiments/*.json)
+------------------+                         +-------------------+
```

### Step 1: Sync Raw Mirror from S3

Fetch any new or backfilled raw CFBD snapshots to the local disk mirror:

```bash
aws s3 sync s3://travispollard-cfb-data/raw/cfbd/ ./research/raw/cfbd/ --profile tp-site
```

### Step 2: Run Fitting or Feature Evaluation

Run grid searches, regression fits, or walk-forward validation runs locally against `./research/raw/`. No network calls or API quotas are spent during fitting:

```bash
# Example fits producing experiments/<type>-<timestamp>.json
uv run cfb fit elo --seasons 2017-2023
uv run cfb fit ridge --seasons 2017-2023
```

### Step 3: Render Diagnostic Report

Generate the static HTML report to inspect calibration, residual distributions, and comparative diffs:

```bash
uv run cfb report
# Opens ./research/reports/index.html in default browser
```

---

## 4. Research Discipline & Guardrails

1. **Zero Leakage:** Walk-forward validation only. Features for Week $N$ must strictly use data available as of Week $N-1$.
2. **Frozen Held-Out Evaluation:** 2024–2025 seasons remain strictly held out until model architecture and parameter grids are finalized.
3. **No Unmapped Teams:** Every team name must resolve via the crosswalk; unmapped teams raise errors rather than failing silently.
4. **Reproducibility:** Experiments are tracked as JSON artifacts, not ephemeral notebook cells. Every constant must trace to an experiment record.

---

## 5. Research Log & Findings

| Date | Model / Experiment | Window | Summary & Key Metrics | Status / Next Steps |
|---|---|---|---|---|
| 2026-08-30 | Initial Setup | 2015–2025 | Repo bootstrapped, specs referenced, CFBD endpoints verified | Ready for backfill pilot |
| 2026-08-30 | Backfill Pilot (2015) & Endpoint Audit | 2015 | Backfilled 2015 season data (51 calls). Audited stats_game_advanced endpoint across all 16 weeks (1,808 game records). Verified 100% completeness for offense/defense ppa, successRate, and explosiveness. | PROVEN: Endpoint is 100% complete and ready for Ridge model feature extraction. |
| 2026-08-30 | Full Historical CFBD Backfill | 2015–2025 (less 2020) | Fully backfilled 10 seasons (2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025). Excluded 2020 successfully as a structural break (SPEC-phase2 §3.2). Synced 510 raw snapshots and 510 manifests to S3, and mirrored locally. | PROVEN: 10 seasons are fully backfilled, locally mirrored, and verified complete with 0 errors. Ready for parameter fitting (Step 4 & Step 5). |
| 2026-08-30 | Elo Grid Search Parameter Fit | 2017–2023 (Fit) / 2024–2025 (Held-out) | Run walk-forward simulation grid search. Regression-to-mean free vs pinned (1/3) yielded identical constants (elo_per_point=16.0, k=30.0, hfa=3.0, floor=0.05). Selected pinned to avoid 2020 gap overfitting. Held-out MAE: 13.1988, Brier: 0.1939, 7-Pt Win Rate: 71.29%. | PROVEN: Seeding-insensitive optimal fit locked. Ready to design and fit the opponent-adjusted Ridge model (Step 6). |
| 2026-08-30 | Ridge Regression on EPA/Success Rate | 2017–2023 (Train) / 2024–2025 (Eval) | Fitted symmetrical opponent-adjusted Ridge model with temporal L2 penalty selection. Evaluated on 1,696 games (the exact intersection) against refitted Elo. Ridge MAE: 13.7648, Brier: 0.2125, Calibration Slope: 0.5287. Elo MAE: 13.0767, Brier: 0.1915, Calibration Slope: 1.1070. | FAILED: Ridge failed all three gate criteria. Refitted Elo remains the superior predictive baseline. Negative result documented per SPEC-phase2 §5.6. |
