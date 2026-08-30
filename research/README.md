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
