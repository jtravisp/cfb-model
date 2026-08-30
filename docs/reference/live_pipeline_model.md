# Upstream Live Pipeline & Model Architecture

This document synthesizes the design, mathematical model, and operational rules of the live forecasting pipeline at `../travispollard.com/cfb`. It serves as the baseline context and domain contract for all Phase 2 research in this repository.

---

## 1. High-Level Architecture & Principles

```
  Sagarin Page (HTTP)                CFBD REST API (/games, /lines, /calendar, /teams)
          │                                                  │
          ▼                                                  ▼
   raw/sagarin/                                          raw/cfbd/
          └────────────────────────┬─────────────────────────┘
                                   │
                    Immutable S3 raw snapshots (write-once)
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
        elo/ (state)       predictions/ (pre-kickoff)   scored/ (Sunday accuracy)
       (cache; rebuildable)        │                    │
              │                    └──────────┬─────────┘
              ▼                               ▼
       cfb/data/*.json ──► CloudFront ──► Next.js Webapp (/cfb, /cfb/slate, /cfb/accuracy)
```

### Core Pipeline Axioms
1. **Raw data is immutable:** Every fetch writes raw bytes to S3 before parsing. Never parse-and-discard.
2. **Never drop a row silently:** Validation failures raise (`models.validating`). An unmapped team name raises in `crosswalk/`.
3. **No fabricated certainty:** Null on empty weeks; every metric carries its denominator ($N$).
4. **State is a cache:** `EloState` can always be deterministically rebuilt from `raw/` snapshots using `cfb replay`.

---

## 2. The Elo Model Specification

The live model uses conventional (unfitted) constants pinned in `cfb/src/cfb/elo/__init__.py`.

### 2.1 Model Seeding (`elo/seed.py`)
Preseason ratings are initialized from Jeff Sagarin's published ratings:
$$\text{Elo}_{\text{seed}} = 1500 + (\text{Rating}_{\text{Sagarin}} - \overline{\text{Rating}}_{\text{FBS}}) \times \text{ELO\_PER\_POINT}$$
- Centered at 1500 for the average FBS team.
- **Seed Disclosure:** Correlation with Sagarin begins at $1.0$. The webapp displays a seed disclosure until the Pearson correlation between live ratings and preseason seed drops below $0.90$.

### 2.2 Point Margin & Win Probability Prediction (`elo/__init__.py`)
- **Predicted Margin (Home perspective):**
  $$\text{Predicted Margin} = \frac{\text{Elo}_{\text{Home}} - \text{Elo}_{\text{Away}}}{\text{ELO\_PER\_POINT}} + \text{HFA}_{\text{Home}}$$
  - $\text{ELO\_PER\_POINT} = 20$ (represents the scale factor where 20 Elo $\approx$ 1 point of margin).
  - $\text{HFA}_{\text{Home}}$ is dynamic from the newest Sagarin snapshot ($0.0$ at neutral sites).
- **Win Probability (Logistic curve):**
  $$P(\text{Home Win}) = \frac{1}{1 + 10^{-\frac{\text{Predicted Margin} \times \text{ELO\_PER\_POINT}}{400}}} = \frac{1}{1 + 10^{-\frac{\Delta \text{Elo}_{\text{adj}}}{400}}}$$
- **Clamping:** Raw unclamped probabilities are saved to prediction logs; published UI clamps display to $[0.01, 0.99]$.

### 2.3 Game Outcome Update Step (`elo/update`)
After games conclude, Elo ratings update zero-sum with a margin-of-victory (MOV) multiplier:
$$\text{Expected} = \frac{1}{1 + 10^{-\frac{(\text{Elo}_{\text{Home}} + \text{HFA} \times 20 - \text{Elo}_{\text{Away}})}{400}}}$$
$$\text{Actual} = \begin{cases} 1.0 & \text{if Home wins} \\ 0.0 & \text{if Away wins} \end{cases} \quad (\text{ties raise } \text{EloDomainError})$$
$$\text{Margin} = \text{Score}_{\text{Home}} - \text{Score}_{\text{Away}}$$
$$\Delta \text{Elo}_{\text{Winner}} = \text{Signed difference between winner and loser Elo}$$
$$\text{mov\_mult} = \ln(|\text{Margin}| + 1) \times \frac{\text{MOV\_DAMPING}}{\max(\Delta \text{Elo}_{\text{Winner}} \times 0.001 + \text{MOV\_DAMPING}, \text{MOV\_DENOMINATOR\_FLOOR})}$$
$$\Delta = K \times \text{mov\_mult} \times (\text{Actual} - \text{Expected})$$
$$\text{Elo}_{\text{Home}} \leftarrow \text{Elo}_{\text{Home}} + \Delta, \quad \text{Elo}_{\text{Away}} \leftarrow \text{Elo}_{\text{Away}} - \Delta$$

#### Live Conventional Parameter Values
| Constant | Value | Purpose |
|---|---|---|
| `ELO_PER_POINT` | `20` | Converts Elo points to score margin (calibrated to $\sigma \approx 15$) |
| `K` | `20` | Base update step magnitude |
| `MOV_DAMPING` | `2.2` | Damps runaway blowout inflation |
| `MOV_DENOMINATOR_FLOOR` | `0.25` | Guard against denominator inversion on massive upsets |
| `_LOGISTIC_DIVISOR` | `400` | Standard logistic scale |

---

## 3. Evaluation & Benchmarks (`elo/scoring.py`)

The pipeline evaluates predictions on Sunday mornings:
- **MAE (Mean Absolute Error):** $|\text{Actual Margin} - \text{Predicted Margin}|$
- **Brier Score:** $(\text{Actual Win} - P(\text{Win}))^2$
- **ATS (Against The Spread):** Binary cover classification vs consensus closing spread from CFBD `/lines`.

---

## 4. Phase 2 Research Mission & Objectives

The research in `cfb-model` builds directly on this foundation:
1. **Fit Elo Constants:** Empirically optimize `ELO_PER_POINT`, `K`, `MOV_DAMPING`, and seasonal regression-to-the-mean factor using historical backfills (2015–2023).
2. **Efficiency / Ridge Regression Model:** Build rolling as-of-week feature matrices using CFBD advanced metrics (per-week adjusted EPA/PPA, success rate, explosiveness) to test whether efficiency models beat Elo.
3. **Bake-Off:** Compare fitted Elo vs efficiency vs Sagarin PREDICTOR vs Vegas spreads.
4. **Held-Out Discipline:** Freeze model candidates on 2015–2023; evaluate final models on held-out 2024–2025.
