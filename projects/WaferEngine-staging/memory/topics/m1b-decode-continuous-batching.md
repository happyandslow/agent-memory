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

## Updates — 2026-09-17: S0 closure and evidence boundaries

- When restarting from the historical subsection above: **S0/D0 is COMPLETE; S1/D1 requires separate review.** Full-scale CS-3 correctness plus final raw-TSC performance were already accepted; the remaining production resource-report gate passed on 2026-09-17. M1-S4 and the full M1b milestone remain open.
- Correction to the earlier Part 1 summary: Part 1 fixture/kernel validation is not the Part 2/3 production-ingress closure. Final production ingress covers equal-position byte-exact vs main, ragged/swapped full-scale NumPy bf16 values, peer isolation, two-round rearm, and row wrap. These are full Qwen3-1.7B dimensions with seeded synthetic tensors, not pretrained-weight/model-quality evidence.
- Final equal-position overhead is **+2.323%**: 665,008 -> 680,457 median raw cycles/token, n=12/10 successful CS-3 runs (502 failures excluded). It supersedes the intermediate +2.36% Part 1 figure. It measures timed decode, not initial metadata/KV ingress latency.
- Same-source/config/request local SDK 2.10 full-geometry WSE-3 compile-only: 286 PE ELFs each; decode-role max shared data 11,704 -> 11,752 B (+48), max text 28,200 -> 29,592 B (+1,392), other role maxima unchanged. Data min delta is +112 B: +48 is not a uniform per-coordinate cost. Task reservation is unchanged at 1,024 B; production `s0_verify_round` is absent. No simulator/device execution in this resource pass; do not equate these ELFs with historical appliance artifacts.
- Compare resource-role extrema with explicit witness ELFs, not unstable numeric ELF IDs. All-ALLOC includes MMIO/config; never subtract it from nominal SRAM to infer headroom. Source named-state subtotal is +40 B, not the full linked +48 B maximum delta.
- Verified checkout: `/home/lexu/WaferEngine-staging`, branch `lexu/staging/m1b-s0-inner-batch-cb`, HEAD `5bb85048`, empty index, Part 2/3 changes uncommitted. Frozen main baseline is `b136ab64`, not a current-remote-tip assertion. No Git mutation or external sync is implied by closure.
- Source of truth: repo `docs/analysis/2026-09-03-m1b-s0-part23-validation-results.md` and `docs/analysis/2026-09-17-m1b-s0-production-resource-report.md`; full capture `memory/inbox/2026-09-17-m1b-s0-resource-closure.md`. S0 remains static-membership execution; S1 owns EOS, S2 continuation, S3/S4 removal/admission, S5/K0 fixed-slot integration. Only the later joint S0/S1/K0 gate can close M1-S4.
