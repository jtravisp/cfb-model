# Reference specifications

Read-only snapshots of the specs from `travispollard.com/cfb/docs/`. **The originals govern**, except
where `docs/PRD.md` (Phase 2) or `docs/PRD-phase3.md` explicitly supersedes a section — each says which.

Nothing in this directory is edited by hand. Every file is written by `scripts/sync-specs.sh` and
carries a header naming the upstream commit it was taken at.

## Keeping them current

```bash
scripts/sync-specs.sh              # refresh from ../travispollard.com and re-pin
CHECK=1 scripts/sync-specs.sh      # report drift, change nothing, exit 1 if stale
```

`CHECK=1` is the form to put in front of a research session, or in CI. It exits non-zero when the
copies are behind, which is the only version of this that is worth having.

**Why a script rather than a documented command.** The first sync was done by hand and pinned commit
`46a9421`. By the time Phase 2 shipped, `SPEC-phase2.md` here was 77 lines behind the original and
still recorded `ELO_PER_POINT` as 20 — after the refit had made it 16.0 and deployed it.

The staleness check documented here was:

```bash
git -C ../travispollard.com log 46a9421..HEAD -- docs/
```

**It could not have caught that.** From the upstream repo root the specs live at `cfb/docs/`, not
`docs/`, so the command matched nothing and reported no drift no matter how far behind the copies
got. A guard that cannot fire is worse than no guard, because it is trusted. The script reads the
path from one place and compares file contents rather than commit ranges, so it cannot be wrong about
where to look.

## What is here

| File | What it is |
|---|---|
| `SPEC-phase0.md` | Collection, storage, the crosswalk |
| `SPEC-phase1.md` | The model, the prediction log, scoring, the JSON contract |
| `SPEC-phase2.md` | The backfill, the refit, the second model, the bake-off |
| `SPEC-phase3.md` | The challenger: a distributional model on the Elo baseline |
| `live_pipeline_model.md` | Architecture, formulas and parameters of the live Elo pipeline |
| `modeling_landscape.md` | CFB prediction literature, paradigms, opponent adjustment, benchmarks |

The last two are authored **here**, not upstream, and the sync script does not touch them.
