# M1b-S0 Part 1 committed; Part 2 exists but is not integration-eligible — 2026-09-02

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

- M1b-S0 Part 1 completed its full validation chain: 53/53 simulator
  per-function and chained scenarios, 23/23 mutation faults, integrated
  P1-I1 through P1-I5, exact equal-position comparison with `origin/main`,
  full-scale 28-layer NumPy comparisons, and real-CS-3 ragged correctness.
  The ragged `[256,512]` case matched both lanes bit-exactly for all 40 top-k
  indices and bf16 values.
- Equal-position real-CS-3 raw-TSC A/B measured S0 at 680,711.6 median
  cycles/token versus 665,007.8 for main: +2.361% (+15,704 cycles/token).
- Le committed the Part 1 implementation, tests, and durable records as
  `5bb850489936cfb5f613292694b7fa45296dd693` (`ragged input kernel and tests`)
  on `lexu/staging/m1b-s0-inner-batch-cb`. The local
  `origin/lexu/staging/m1b-s0-inner-batch-cb` tracking ref resolved to the same
  commit when checked on 2026-09-02; this is a local-ref observation, not a
  fresh remote fetch.
- Part 2 heterogeneous metadata/KV ingress has a parallel implementation in
  detached worktree `/home/lexu/we-m1b-s0-part2-metadata-ingress`; 31/31
  focused host tests pass. Its exact status is
  `PARALLEL_PREPARED_NOT_INTEGRATION_ELIGIBLE`, not complete: independent
  review found `tests/s0_ingress_packet.py` missing from the source-hash
  closure and a verify-then-reread TOCTOU window for source `launch.py`.
  No Part 2 CSL compile, simulator, or CS-3 gate has run.

## Implications / next actions

- [ ] Fix the two Part 2 P1 artifact-closure defects and obtain a clean
  independent re-review before authorizing compile-smoke.
- [ ] Run the separately reviewed Part 2 compile, simulator, and real-CS-3
  gates before checking M1b-S0 complete.
- [ ] Keep M1b-S1 per-lane EOS and all later lifetime/scheduling state outside
  the Part 2 repair.

## Pointers

- `WaferEngine-staging/docs/analysis/2026-09-01-m1b-s0-validation-results.md`
- `WaferEngine-staging/milestones/M1b-decode-continuous-batching.md`
- `/home/lexu/we-m1b-s0-part2-metadata-ingress/docs/analysis/2026-09-02-m1b-s0-part2-metadata-ingress-session-output.md`
- Related: `2026-09-02-m1b-s0-part1-ragged-validation-complete.md`
