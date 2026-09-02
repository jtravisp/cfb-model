# Phase 3, run locally — product requirements

**Status:** draft
**Basis:** `SPEC-phase3.md`, which supplies all substance. This document changes only *where the
work runs* and *how it is watched*.
**Supersedes in SPEC-phase3:** §4 in full (this repo owns the model), and §5's *implementation*
while leaving its criteria untouched. Everything else carries forward unchanged and is not restated.

---

## 1. What changed since Phase 2, and what did not

Phase 2's argument for running research locally holds without amendment: **a pipeline fails by going
red, and research fails by producing a number you believe.** Leakage does not raise. Nothing below
revisits that.

Two things *have* changed, and both narrow this document rather than widen it.

**The live pipeline has now completed a clean cycle and carries a second document.** As of
2026-09-01 it publishes four routes, replays its own state across a refit, and has a schema that
records which constants produced which ratings. It is more robust than it was when Phase 2 argued
for staying away from it — and that is a reason to keep the boundary rather than to relax it. The
thing worth protecting got more valuable.

**Phase 3's production surface is real, and it is not this repo's.** Phase 2 crossed into production
as four numbers. Phase 3 needs a collector, a workflow, a schema bump and two CLI commands
(SPEC-phase3 §3, §8, §9) — none of which is fitted, and none of which belongs here. That work is
listed in `travispollard.com/cfb/docs/PHASE-3.md` and this document does not duplicate it.

---

## 2. The division, stated once so it needs no case-by-case judgement

> **`travispollard.com/cfb` owns anything that runs unattended or reaches a reader.** Collectors,
> workflows, schemas, the CLI, the published JSON contract, and the specs themselves.
>
> **This repo owns anything that is *fitted*.** Features, shrinkage constants, estimators,
> hyperparameters, the evaluation implementation, and the experiment record.

**One question decides any item:** does it run on a schedule or reach a page? Production. Does it
produce a number by fitting? Research.

**The seam is a committed artifact plus a registry entry**, which is exactly what Phase 2 proved. An
entire grid search over eleven seasons, two model architectures and a held-out evaluation crossed
into the live pipeline as four constants and one line in `constants_for`. Phase 3 uses the same seam
and nothing wider — a fitted model reaches production as a serialised artifact and a registry entry,
never as code that runs here.

**The dependency arrow is one-way and enforced by the package manager.**

```bash
uv add --editable ../travispollard.com/cfb
```

This repo imports the *shipped* Elo rather than reimplementing it. SPEC-phase2 §5.5 requires the
baseline be regenerated on identical games; a research baseline that drifted from production by even
one constant would make the bake-off measure nothing. It also means a change to live Elo correctly
invalidates every baseline built here, which is the behaviour we want.

---

## 3. What this repo delivers in Phase 3

| | Deliverable | SPEC-phase3 |
|---|---|---|
| **3.1** | An as-of-week feature pipeline with a leakage guard that raises | §4.2 |
| **3.2** | Empirical Bayes shrinkage with `k` fitted per metric | §4.3 |
| **3.3** | A preseason prior model, benchmarked against Sagarin's preseason page | §4.3 |
| **3.4** | Two estimators — LightGBM two-stage and NGBoost Student-t | §4.5 |
| **3.5** | The gate implementation: PIT, 80% coverage, week buckets | §5 |
| **3.6** | A serialised model artifact production can load without importing this repo | §6 |

**3.6 is the one that is easy to get wrong.** A model that only runs inside this repo cannot be
shadow-run by the live pipeline, and shadow mode is the phase's critical path. The artifact format
is decided *before* the estimators are, not after.

---

## 4. What "done" means here, and what it does not

**Done here is a gate verdict, not a promotion.** This repo produces the number and the record;
SPEC-phase3 §6 decides what happens next, and clearing the gate changes no page.

**A rejection is a completed deliverable.** SPEC-phase2 §5.6 is explicit that failing is a
legitimate outcome and that shipping anyway "would make the rule decorative." The ridge model's
rejection is currently the most rigorous thing this project has produced. If the distributional
model loses too, the finding is that Elo is harder to beat than the field assumes — worth publishing,
and cheaper to learn here than in production.

**Every constant traces to an experiment record.** Unchanged from Phase 2 §4 of `PRD.md`: a number
that cannot name the run that produced it does not cross the seam.

---

## 5. What is out of scope for this repo

- **The roster collector, its workflow and its schema** (SPEC-phase3 §3.2). It runs unattended and
  writes to `raw/`. Production.
- **The shadow-mode schema bump** (§3.3). It changes a document the live pipeline writes. Production.
- **`PROBABILITY_SCALE`'s constant** (§3.1). This repo *fits* it and writes the experiment record;
  production holds the value and applies it at the 2027 boundary.
- **Anything that publishes.** No process in this repo writes to `cfb/data/`, and the Phase 2 PRD's
  §6 supersession stands.

---

## 6. Open questions this repo owns

- **What `ν` does the margin distribution want?** A large fitted value says the Normal was adequate
  and simplifies the model. Cheap to answer early and worth doing first.
- **Does the intersection flatter the market?** SPEC-phase3 §12's first question. The market's MAE on
  the full priced slate versus the intersection is a two-hour job and it decides whether 11.813 is a
  target or an artifact.
- **Is a week-gated hybrid one model or two?** The answer changes the artifact format, so it is
  settled here before 3.6 is built rather than after.
