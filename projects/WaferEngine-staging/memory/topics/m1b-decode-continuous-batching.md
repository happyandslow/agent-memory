# M1b Decode Continuous Batching

One-topic packet for the M1b decode continuous-batching milestone and M1b-S0 correctness evidence.

## Summary

- M1b formalizes the O1 decode continuous-batching roadmap. It is decode-only; full prefill/continuous prefill and early close are separate later work.
- The approved order is D0 -> D1 -> D2 -> K0/PF, with D0/D1/D2 based on `origin/main` at `S=M`. Formal stage aliases: M1b-S0/D0, S1/D1, S2/D2a, S3/D2b, S4/D2c, S5/K0.


## Updates — 2026-09-07 maintenance drain: M1b-S0 evidence

- Drained the approved O1/M1b roadmap captures and M1b-S0 evidence captures. M1b is tracked as a formal decode-only milestone, not a branch-creation license. K0/M1b-S5 starts only after reviewed D2 and semantically ports or deliberately replays prior cleanup; M1-S3 cleanup is a closure prerequisite for K0, not a blocker for early M1b-S0/D0 substrate work.
- M1b-S0 Part 1 ragged validation is complete on real CS-3: production-ingress ragged metadata/position path was bit-exact and measured about +2.36% overhead. The stateless-position refactor must retain/replay the old saturating guard, and future position-derived helpers need a source-boundary test.
- M1b-S0 low-amplitude red controls need arithmetic-specific signatures: the missing-alpha fault required finite power-of-two amplification to become independently observable; do not reuse a generic `E/4` heuristic mechanically.
- Simulator-overlay execution consumed four candidates before closing: bind production symbols before layout, keep exact signed address semantics, preserve production DSD/source binding, and ensure readback actually observes the target cells. `read_symbol` remains simulator-only context, not device proof.
- Softmax scalar stage defect: a `save_address` source DSR hot-path dropped the first live cell in every `L>=2` group; use exact raw checks for reductions and rerun fresh stage-3 gates before score-v/stage-4 claims.
- Part 2+3 correctness reached production-ingress bit-exact on CS-3 by 2026-09-04; performance sweep was still in flight at capture time, so do not claim performance closure from memory alone.
