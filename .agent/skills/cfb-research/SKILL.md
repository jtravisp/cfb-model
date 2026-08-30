---
name: cfb-research
description: Session-close loop and research log protocol for the college football modeling repo. Use at the end of every research session, after running fits or experiments, to document what was tried, what succeeded, what failed, and the next steps in research/README.md.
---

# CFB Research Session-Close Loop

This skill defines the mandatory protocol to follow when ending a research session or completing an experimental cycle in `cfb-model`.

## 1. The Session-Close Protocol

At the end of every research iteration or user session:

1. **Verify Experiment Artifacts:**
   - Ensure every fit or grid search produced a structured JSON document in `research/experiments/` (e.g. `experiments/elo-<ts>.json` or `experiments/ridge-<ts>.json`).
   - Check that experiment files include full provenance: model type, hyperparameters, training window, cross-validation scores, and held-out evaluation metrics.

2. **Document Findings in `research/README.md`:**
   - Update Section 5 ("Research Log & Findings") of `research/README.md`.
   - Record:
     - Date
     - Model / Experiment name
     - Training / validation window
     - Key metrics (MAE, Brier score, calibration slope, etc.)
     - Outcome: whether the hypothesis was validated, inconclusive, or failed.
     - **Failures and negative results must be explicitly documented** so dead ends are never repeated.

3. **Check Git Cleanliness:**
   - `research/raw/`, `research/derived/`, and `research/reports/` must remain untracked (gitignored).
   - Only `research/experiments/*.json`, `research/README.md`, specs, and code are staged.

4. **Summarize Next Steps:**
   - State the single next question or hypothesis to test in the following session.
