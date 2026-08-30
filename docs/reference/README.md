# Reference Specifications

This directory contains read-only snapshots of upstream specification documents from `travispollard.com`. The original files in `travispollard.com/cfb/docs/` govern all architecture and design decisions unless explicitly overridden by `docs/PRD.md` in this repository.

## Upstream Provenance

- **Source Repository:** `travispollard.com/cfb/docs/`
- **Source Commit:** `46a9421ed103082826584e460152d84a5edb949e`
- **Commit Message:** `SPEC-phase2: decide the ambiguous fit, and name the double duty`
- **Recorded Date:** 2026-08-30

## Tracked Files

- `SPEC-phase0.md` — Phase 0 collector implementation spec
- `SPEC-phase1.md` — Phase 1 v1 implementation spec
- `SPEC-phase2.md` — Phase 2 depth implementation spec
- `live_pipeline_model.md` — Architecture, mathematical formulas, and parameters of the live Elo pipeline
- `modeling_landscape.md` — Synthesis of CFB prediction literature, modeling paradigms, opponent adjustments, and benchmarks

## Tracking Staleness

To check if the upstream specifications have evolved:

```bash
git -C ../travispollard.com log 46a9421ed103082826584e460152d84a5edb949e..HEAD -- docs/
```
