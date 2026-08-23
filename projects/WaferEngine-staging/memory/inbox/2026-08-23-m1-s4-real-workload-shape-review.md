# M1-S4 real-workload shape review — 2026-08-23

**Project:** WaferEngine-staging
**Author:** hermes
**Status:** captured

## What happened / finding

- TraceLab v0.0.2 was hash-verified and profiled separately from Mooncake:
  665,453 rounds / 8,058 sessions; SHA-256
  `11ce51ec0a25e3d1d95b025bca2f7d1647e47571eb7cc968acd5fc64d4b4fb65`.
  `prefix_tokens` is provider-cache telemetry, not exact Qwen LCP.
- TraceLab is far outside the current 1,792-token device envelope. Only 29
  requests pass prefix geometry, 28 also satisfy `P+G-1 <= 1792`, and no FIFO
  `bsz=2/4` batch is geometrically executable. Raw public rows therefore cannot
  be presented as current-S3 device requests.
- TraceLab still supplies useful shape: FIFO `bsz=2`, 10-ms batches have
  `delta R` p50/p95 of 3,072/181,248 tokens; session recurrence p50/p95 is
  0/18 strictly intervening requests. System, conversation, and tool prefixes
  cannot be distinguished.
- Mooncake FAST'25 ToolAgent has 23,608 requests and exact 512-token block-hash
  history evidence, but `output_length` is capped at 2,000 and first-block
  grouping collapses to four proxy groups. Its prefix-geometry/full-round
  counts are 2,342/1,899; one FIFO `bsz=2` batch passes the proxy geometry.
- The delegated draft had two corrected defects before persistence: recurrence
  distance counted the recurrence hop instead of strictly intervening requests,
  and Mooncake prefix geometry was mistyped as 2,302 rather than 2,342.
- The workload decision is a shape-preserving projection: preserve FIFO batch
  membership and joint ranks/correlations, map to legal `(S,K)` cells, report
  out-of-range values as right-censored, and keep TraceLab/Mooncake separate.
  Cache affinity remains a separately priced scheduler counterfactual.

## Implications / next actions

- [ ] Materialize and review the projected request set; the current profiler
      establishes source shape but does not yet choose final device weights.
- [ ] Use TraceLab for uncapped generation/EOS shape and Mooncake only as a
      capped legacy/lower sensitivity for generation.
- [ ] Do not claim device speedup from trace token-work; integrate trace weights
      only after the C1 CS-3 cost surface is measured.

## Pointers

- Branch `lexu/staging/m1-ragged-execution-study` at reviewed HEAD `77d6d407`
- `docs/analysis/m1-s4-real-workload-shape.md`
- `docs/analysis/m1-s4-c1-workload-step-review.md`
- `tools/m1_ragged_study/workload_profile.py`
- `tools/m1_ragged_study/results/m1-s4-real-workload-shape-v1.json`
- Related topics: `a7-Lp-vs-Lg-settled-on-tracelab.md`,
  `agentic-kv-trace-datasets.md`

