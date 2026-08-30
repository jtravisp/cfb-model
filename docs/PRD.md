# Phase 2, run locally — product requirements

**Status:** draft
**Basis:** `SPEC-phase2.md`, which supplies all substance. This document changes only *where the
work runs* and *how it is watched*.
**Supersedes in SPEC-phase2:** §6 (the `/cfb/models` route), §8's upload behaviour, §11's steps 4
and 6. Everything else carries forward unchanged and is not restated.

---

## 1. Why local, stated as a decision rather than a convenience

Phase 0 and Phase 1 were pipeline work: the deliverable was a thing that runs unattended, and the
architecture exists to make failure loud. Phase 2 is research. Its deliverable is *an answer* —
whether a fitted Elo beats an asserted one, whether efficiency beats Elo — and research fails
differently.

**A pipeline fails by going red. Research fails by producing a number you believe.** Leakage does
not raise; it produces the best MAE the project has ever seen. A constant fitted on the games it is
evaluated on looks like a triumph. Those failures are caught by iteration speed and by looking at
things, not by a cron and an email.

Three concrete reasons this belongs off the deployed path:

- **The live pipeline is running and must not be disturbed.** As of 2026-08-30 it publishes on a
  Thursday and Friday against a real SLO, and the first full unattended cycle has not happened yet.
  Phase 2 touches `EloState`'s schema, the crosswalk resolver, and the constants every prediction is
  made from. Doing that to a live system mid-season, before it has completed one clean week, trades
  a working thing for an unproven one.
- **The iteration loop is minutes, not a deploy.** A grid search that gets rerun forty times cannot
  live behind a PR, a CodeBuild, and a CloudFront invalidation. The cost is not the wait; it is that
  a slow loop makes you run fewer variations and accept the first answer that looks reasonable.
- **Most of Phase 2 produces no artifact a visitor sees.** Nine of the eleven components in the
  estimate are backfill, fitting and validation. The page is the last thing and it is the smallest.

**What this does not buy:** it does not de-risk the operational half. §7 says which risks survive
going local, because the framing "prove it locally, then roll it in" quietly implies they all go
away, and they do not.

---

## 2. What stays disciplined, and what is deliberately relaxed

The danger in a research mode is that the habits protecting this project get treated as pipeline
ceremony and dropped — and then a model "proven" locally arrives in production carrying assumptions
that never survived contact with anything.

### 2.1 Non-negotiable, unchanged from SPEC-phase2

| Discipline | Why it survives going local |
|---|---|
| `raw/` lives in S3, immutable, write-once | §3 below. This is the one irreversible cost in the phase |
| `LeakageError` and as-of-week aggregation (§5.3) | The failure that produces the best numbers this project has ever seen |
| An unmapped team raises (`cfb/CLAUDE.md`) | A silently dropped game makes every downstream figure fiction |
| Walk-forward validation, never a random split (§5.4) | A random k-fold describes a model that cannot exist |
| Held-out seasons untouched until constants are frozen (§4.2) | A constant fitted on its evaluation set is a description, not a prediction |
| The gate is three conditions and failing is legitimate (§5.6) | A gate you can talk yourself past is not a gate |
| Fits are traceable to the run that produced them (§8) | A fitted constant with no provenance is an assertion |

### 2.2 Relaxed on purpose

| Relaxed | In place of |
|---|---|
| No Terraform, no IAM changes, no new AWS resources | The existing bucket and role, unchanged |
| No workflows, no crons, no SLO | Commands run by hand when you want an answer |
| No `PUBLISHED_SCHEMA_VERSION`, no routes, no CloudFront | A local HTML report (§5) |
| Derived artifacts are not write-once | They regenerate from `raw/` in minutes; immutability protects irreplaceable things |
| Derived artifacts are gitignored | Except `experiments/`, which holds findings (§4) |

**The distinction that decides which list a thing lands in: can it be regenerated?** `raw/` cannot —
it costs CFBD calls against a monthly limit. An Elo state, a backtest, a feature matrix all can, from
data already in the bucket, for free. Immutability is a property irreplaceable things need and
regenerable things pay for.

---

## 3. Raw data goes to S3 anyway, and this is the one place local loses

**The backfill writes to `s3://travispollard-cfb-data/raw/cfbd/` exactly as SPEC-phase2 §3.6
describes.** Not to a local store. This is the single exception to "local means local" and it is the
most important decision in this document.

SPEC-phase2 §3.5 estimates ~510 CFBD calls for the window, against a monthly figure that may really
be 1,000 and is not vendor-backed. The live season spends ~20 a week on top. **The margin is thin
enough that re-pulling the window costs a month of wall-clock**, and a laptop that dies, a directory
deleted while cleaning up, or a `--store` typo would all cost exactly that.

So: fetch once, to the durable place, then work against a local mirror.

```bash
uv run cfb backfill --from 2015 --to 2025            # writes to s3://, ~21 runs
aws s3 sync s3://travispollard-cfb-data/raw/cfbd/ ./research/raw/cfbd/ --profile tp-site
```

The mirror is a cache and says so: gitignored, regenerable by one command, and never the thing any
code treats as authoritative when S3 is reachable. Roughly 50 MB for the window, so the sync is
seconds and the disk cost is nothing.

**Everything else in the phase reads the mirror.** Fitting, feature building, backtesting and
reporting all run against `file://./research/raw`, which is why the loop is fast: no network, no
credentials, no round trip.

**One consequence worth stating.** The backfill itself is the only part of Phase 2 that touches the
network or spends anything, so it is the only part that should be run deliberately rather than
casually. SPEC-phase2 §3.6's `--dry-run` and the pilot in §6.2 exist for that.

---

## 4. Layout

```
cfb/
├── research/                       # new; the whole local surface
│   ├── raw/                        # gitignored — mirror of s3://…/raw/cfbd/
│   ├── derived/                    # gitignored — elo states, backtests, feature matrices
│   ├── experiments/                # TRACKED — fit results, one JSON per run
│   │   ├── elo-2026-09-20T1412Z.json
│   │   └── ridge-2026-09-21T0903Z.json
│   ├── reports/                    # gitignored — generated HTML
│   └── README.md                   # TRACKED — how to run the loop
└── src/cfb/
    ├── backfill.py                 # §3.6
    ├── fit/
    │   ├── elo.py                  # §4.2 grid search
    │   ├── ridge.py                # §5 features, fit, validation
    │   └── report.py               # §5 below — the local renderer
    └── …                           # everything else unchanged
```

**`experiments/` is tracked and the rest is not**, because a fit result is a finding. It is small
JSON, it is the thing that graduates to production, and a fit that cannot be traced to the run that
produced it is an assertion (SPEC-phase2 §8). Git is doing here what write-once storage does in the
pipeline: making the record of what was tried survive the person who tried it.

`derived/` is gitignored and regenerable. If it is ever unclear whether an artifact belongs there or
in `experiments/`, the question is whether deleting it loses information you could not recompute.

---

## 5. Monitoring: JSON documents and a static report, not a notebook

### 5.1 The shape

Every command writes a JSON document to `research/experiments/`. A separate command renders one or
more of those documents into a single self-contained HTML file:

```bash
uv run cfb fit elo --seasons 2017-2023          # → experiments/elo-<ts>.json
uv run cfb fit ridge --seasons 2017-2023        # → experiments/ridge-<ts>.json
uv run cfb report                               # → reports/index.html
```

`cfb report` opens with no server, no port, and no dependencies beyond a browser. It renders:

- **The experiment index** — every run, its constants, its held-out figures, newest first.
- **The §4.3 calibration table**, regenerated with observed rates and their counts.
- **Predicted-vs-actual scatter and a residual plot**, which SPEC-phase2 does not require and should:
  the CFBD guidance's ninth tip is that MAE hides trends a residual plot shows immediately, and
  systematic misses on service academies or triple-option teams are exactly that shape.
- **A diff against the previous run of the same kind**, so "did anything move" is answerable at a
  glance rather than by comparing two files by eye.

### 5.2 Why not a notebook

Notebooks are the obvious research answer and they are wrong here for one reason: **this project's
entire credibility rests on reproducibility.** `cfb elo replay` exists to prove state is a cache
rather than a source of truth. A notebook is the opposite artifact — out-of-order execution, hidden
state, results that depend on what was run before, and nothing testable.

Use one for genuine exploration if it helps. Do not let a number reach `experiments/` from one.

### 5.3 Why a static file rather than Streamlit

A dashboard is a server: a port, a process to remember to kill, a dependency, and a thing that cannot
be committed or attached to a session summary. A single HTML file can be opened, kept, diffed, and
handed to someone. It also renders through the same generator-then-render split the publish path
already uses, which is what makes §6 cheap.

---

## 6. The three seams that make graduation cheap

The point of running locally is not to avoid production. It is to defer it until there is something
worth deploying. So the design constraint is that **graduation must not be a rewrite**, and it is
not, because three seams already exist.

### 6.1 `SnapshotStore` — already built

Phase 0 §2.3 made the store a protocol with `MemorySnapshotStore`, `FileSnapshotStore` and
`S3SnapshotStore` behind it, precisely so tests could stay offline. That same seam is what makes the
research mode work: `--store file://./research/derived` locally, `s3://` in production, and **not one
line of model code knows the difference.**

Nothing new is needed here. It is worth naming because it is the reason this document is short.

### 6.2 The generator/upload split — already built

`cfb publish` computes documents and then uploads them, and Phase 1 §6 is explicit that the
generator recomputes nothing. So `cfb models --season 2026` can write `models.json` to a local path
now and to S3 later, with the difference being the store argument and nothing else.

**`models.json`'s shape is fixed now, at SPEC-phase2 §6.2, even though nothing publishes it.**
Writing the local report against the production document shape means graduation is: point the store
at S3, add a route that fetches it, bump `PUBLISHED_SCHEMA_VERSION`. The report and the route render
the same document.

### 6.3 The constants live in the state document — already specified

SPEC-phase2 §4.1 puts the fitted constants inside each `EloState`. That was decided for replay
correctness, and it has a second effect: **a fitted constant graduates by being written into a state
document, not by being edited into a module.** A locally-fitted `ELO_PER_POINT` reaches production
the same way any other value does, and `replay` checks it the same way.

### 6.4 What graduation actually costs

| Step | Cost |
|---|---|
| Point the store at `s3://` | An argument |
| Publish `models.json` | Exists; §6.2 |
| Add the `/cfb/models` route | ~350 lines tsx, ~250 spec — the fourth route in an established pattern |
| Adopt fitted constants | A season boundary (§4.1), plus one commit |
| Wire per-week feature aggregation into the Thursday run | **The one that is not cheap. See §7** |

---

## 7. What running locally does not de-risk

Three risks survive intact, and the "prove it locally" framing hides all three.

### 7.1 As-of-week aggregation is easy on a finished season and hard on a live one

Locally, "weeks 1 through N−1" is a filter over data that already exists. In production on a
Thursday in October, week 8's features must be built from data CFBD has actually posted by then —
and advanced metrics may lag the games, may be revised after first publication, and may simply not
be there when the cron fires.

**A model that validates perfectly on complete seasons can be unrunnable on a Thursday**, and no
amount of local work surfaces that. The check is cheap and should happen early: during the live
2026 season, fetch the advanced-metric endpoint on a Thursday and see what week it actually covers.
That is one call and it belongs alongside §12's endpoint verification.

### 7.2 The fitted constants describe a differently-seeded model

SPEC-phase2 §1 and §4.4 already say this and it does not change. Worth repeating here only because
the local phase produces the constants and the live season is the only thing that can check them —
so the two halves are now in different places, and the check has to be deliberate rather than
incidental.

### 7.3 A research directory is where discipline goes to die

`research/` is gitignored except for `experiments/`, has no CI, no schema version, and no review.
That is the point, and it is also how a hack becomes permanent. Two guards:

- **Anything that graduates gets tests written against it in `cfb/tests/`, at the standard the rest
  of the project holds.** The research code that produced a result is not the code that ships it.
- **`research/README.md` records what was tried and what it said**, including the runs that failed.
  A phase that reports only its successes is a phase that fitted on its evaluation set.

---

## 8. Sequencing

Phase 2 does not start first. Two things ahead of it, both from the estimate:

1. **The coming-week fetch gap**, which fires Thu 10 Sep and breaks the live pipeline. One unit,
   hard deadline.
2. **Sunday 13 Sep**, Phase 1's first real end-to-end run. §11's five steps have never all happened
   at once, and §4.4's validation strategy leans on 2026 being a clean live season to check the
   fitted constants against. Starting the backfill before knowing the live pipeline works means
   debugging both at once.

Then, in order:

| # | Step | Why here |
|---|---|---|
| 1 | Verify the CFBD advanced-metric endpoints (§12) | A handful of calls. If per-week efficiency is not available to 2015, §5 needs rewriting rather than adjusting — and the ridge model is the largest component |
| 2 | `cfb backfill --dry-run`, then **one season as a pilot** | The plan and its real cost, measured. A wrong endpoint discovered here costs one season's calls; discovered after the full pull it costs a month |
| 3 | The full backfill, ~21 runs | The only irreversible spend in the phase |
| 4 | `seed_history`, crosswalks, constants-in-state | Foundations; nothing fits without them |
| 5 | `cfb fit elo` and the §4.3 table | The refit is the phase's floor — it delivers value whether or not the ridge model does |
| 6 | Ridge: features, leakage guard, fit, gate | The largest surface, and the one that can legitimately fail |
| 7 | `models.json` + `cfb report` | Local only |
| 8 | Graduation, if earned | §6.4 |

Steps 1 and 2 are insurance and should not be skipped for being unglamorous. Step 3 is the one that
cannot be taken back.

---

## 9. What "proven" means

The local phase ends with a decision, and the criteria are stated in advance so the decision is not
made by whichever number looked best.

**The refit graduates when:**

- Every backfilled season replays to its stored state on its own constants (SPEC-phase2 §11 step 3).
- The §4.3 calibration table's 7-point bucket lands near the published ~67% figure. Far from it means
  the fit is wrong before anything reaches a page.
- The primary and sensitivity fits are both reported, and §4.4's shipping rule has been applied
  rather than argued.

**The ridge model graduates when:**

- It clears §5.6's three conditions on held-out seasons.
- Its as-of-week feature pipeline has been demonstrated against a *live* Thursday, per §7.1 — not
  against a completed season.
- Its residual plot has been looked at by a person and shows no systematic miss anyone can name.

**And the live check, which is the one that matters (§11 step 4):** the fitted constants, applied to
the 2026 Sagarin-seeded season, produce a calibration curve matching the one the backfill predicts.
If they do not, the seeding difference mattered, and that is a finding to publish rather than a
problem to route around.

**Failing any of this is a legitimate outcome.** SPEC-phase2 §5.6 already says so for the gate; it
holds for the whole phase. A negative result — the constants barely move, or efficiency does not beat
Elo — is a real finding about the baseline, and it is a better write-up than a marginal improvement
nobody can distinguish from noise.

---

## 10. Out of scope

Everything SPEC-phase2 §10 excludes, plus:

- Any change to the live pipeline's behaviour before §9's criteria are met
- Any new AWS resource, IAM statement, workflow or route
- A server, a dashboard process, or anything requiring a port
- Notebooks as the source of any number that reaches `experiments/`
- Publishing `models.json` to `/cfb/data/` (that is graduation, §6.4)
  