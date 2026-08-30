# College Football Modeling Landscape, Literature & Methodology

This document synthesizes core domain research, academic literature, empirical benchmarks, and modeling best practices for college football game prediction. It establishes the theoretical context, realistic performance targets, and architectural decisions for `cfb-model`.

---

## 1. Defining "Good": The Empirical Performance Ceiling

Any serious modeling effort must be anchored against what is actually achievable in college football:

| Benchmark | Metric | Value / Range | Context |
|---|---|---|---|
| **Vegas Closing Line** | MAE | **~12.6 points** | The gold standard. Consistently lowest MAE of any tracked system in *The Prediction Tracker*. |
| **SP+ (Bill Connelly)** | ATS Win % | **51% – 54%** | Break-even at standard -110 juice is **52.38%**. Top public models hover near coin-flip against the closing spread. |
| **Outright Favorite Base Rate** | Straight-Up Win % | **~75%** | Simply picking the favorite straight-up wins 3 out of 4 FBS games. |
| **Market Line Evolution** | Metamodel Signal | Opening $\rightarrow$ Thursday $\rightarrow$ Closing | Studies (Journal of Sports Analytics, 2025) show opening lines contain extractable inefficiencies; closing lines do not. The pipeline's Thursday `market_line` sits in between. |

### The Target for `cfb-model`
- **Objective:** Achieve an MAE within **~1.0 point of the market** (e.g., 13.0–13.5) with strictly calibrated probabilities.
- **The Non-Goal:** Claiming sustained >60% ATS records or beating the closing market, which represents overfitting, un-tracked variance, or data leakage.

---

## 2. Evaluation of Existing Approaches & Common Pathologies

| Approach / Source | Headline Claim | Critical Reality & Failure Mode | Key Takeaway for `cfb-model` |
|---|---|---|---|
| **`deepCFB` (Brian Szekely)** | "84% DNN validation accuracy" | Base rate for favorites is ~75%. Sample outputs exhibit extreme overconfidence ($99.999\%$ win probs). Author notes bad-team bias where top-25 teams are assumed to always win. | Avoid complex deep nets; enforce well-scaled probabilistic mappings. |
| **Reddit Play-by-Play Sims** | "34–10 ATS (77%) in Week 1" | Pure single-week sample variance. Flipped efficiency adjustments caught mid-season; no out-of-sample discipline. | Single-week ATS runs are statistical noise. Sustained edge requires multi-season walk-forward splits. |
| **Normal-Sampling Monte Carlo** | "10k sims from mean & std dev" | Mis-specified model. Independent normals on raw season PPG without opponent adjustment treat competitive 13–10 games as "0.04% rare flukes" rather than pace/opponent effects. | Scores are correlated through pace and opponent defense. Raw PPG without opponent adjustment is invalid. |
| **NFL Turnover Regression** | "Turnovers are the #1 predictor" | Retrodiction. Uses in-game box stats not available pre-kickoff. Turnover margin is the least year-over-year persistent statistic in football. | Do not model noise. Base predictions on down-to-down opponent-adjusted efficiency. |
| **CFBD Guidelines (Radjewski)** | 10 Practical Rules | Margin first, opponent adjustment, talent composite priors, Week 5+ training split, visual residual inspection. | **Directly adopted as the core foundation of this repository.** |

---

## 3. Core Architecture: Ridge Regression on Opponent-Adjusted Efficiency

The primary research vehicle alongside Elo is **Ridge Regression predicting point margin from opponent-adjusted efficiency**:

$$\text{Predicted Margin} = \beta_0 + \beta_1 \Delta \text{AdjEPA}_{\text{net}} + \beta_2 \Delta \text{SuccessRate} + \beta_3 \Delta \text{Explosiveness} + \beta_4 \text{TalentGap} \cdot e^{-\lambda N} + \beta_5 \text{HFA}$$

### Why Ridge Regression Fits This Project:
1. **Deterministic & Replayable:** A fitted Ridge model is just a vector of coefficients ($\vec{\beta}$) stored in JSON within `research/experiments/`. This preserves the foundational axiom that **state is a cache** rebuildable from raw snapshots.
2. **Explainable:** Feature weights are directly interpretable (e.g., "defense is weighted $1.3\times$ relative to offense").
3. **Solves Elo's Structural Blindspot:** Elo knows only who won and the score margin. It cannot distinguish a team that won by 3 while outgaining its opponent by 250 yards from a team that won by 3 on two defensive fluke touchdowns. Ridge on EPA isolates true down-to-down dominance.
4. **Talent Decay Prior:** Incorporates 247Sports Team Talent Composite early in the season, smoothly decaying as completed in-season games accumulate.
5. **Quota Efficient:** Requires only one additional weekly collector call (`/stats/game/advanced` or `/stats/season/advanced`).

---

## 4. The Grand Bake-Off Design

The central scientific output of Phase 2 is an honest, multi-system bake-off scored across identical games:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        THE PHASE 2 BAKE-OFF                            │
├───────────────────────┬────────────────────────────────────────────────┤
│ System                │ Role / Nature                                  │
├───────────────────────┼────────────────────────────────────────────────┤
│ 1. Market Line        │ Gold standard benchmark (Thursday quote)       │
│ 2. Sagarin PREDICTOR  │ External competitor benchmark                  │
│ 3. Conventional Elo   │ Baseline internal model (unfitted constants)   │
│ 4. Fitted Elo         │ Empirically optimized Elo (2015–2023 grid)     │
│ 5. Ridge Efficiency   │ Opponent-adjusted EPA & talent model           │
│ 6. Meta-Ensemble      │ Multi-system combination (if justified)        │
└───────────────────────┴────────────────────────────────────────────────┘
```

---

## 5. Research Roadmap & Sequencing

1. **Step 1: Backfill & Refit Elo (2015–2023):**
   - Run backfill with `--dry-run` to safeguard API quota.
   - Optimize $K$, scale divisor, MOV damping, and season regression factor over 2015–2023.
2. **Step 2: Ridge Efficiency Model (Week 5+ Discipline):**
   - Train on games from Week 5 onward (Weeks 0–4 governed by talent/preseason priors).
   - Gate rule: Ridge must beat fitted Elo on cross-validation to graduate.
3. **Step 3: Bake-Off & Frozen Evaluation (2024–2025):**
   - Evaluate all models on held-out 2024–2025 data.
   - Generate static diagnostic reports (`research/reports/index.html`) with calibration and residual plots.
