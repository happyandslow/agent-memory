# On-chip SRAM offload search use case — 2026-08-28

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured   <!-- captured | drained -->

## What happened / finding

- Le added a second required use case for this project: model and search the
  trade-offs of progressively offloading KV cache from compute PEs into spare
  on-wafer SRAM. The intended generalization is any SRAM-backed store whose
  placement and communication-algorithm choices jointly affect capacity,
  movement cost, resource pressure, interference, and reuse value.
- The live WaferEngine-staging evidence branch is
  `lexu/staging/m3-on-chip-kv-offload-study@255dab72c4231f85c28a82007bf4c2830696537d`.
  It contains device-measured v3 single-row, v4 GO-chain, and v5 cascade
  park/reload witnesses plus raw results and fitted models. Its own tracking
  still marks live decode placement/resource closure and concurrent-compute
  interference as open.
- The current WSE-3 performance-model plan has useful seams for this use case:
  implementation-specific communication witnesses, explicit residency and
  ownership, SRAM/fabric/protocol checkers, and Pareto output. As written,
  however, it scopes providers to compute+communication and the search
  vocabulary to decode/prefill role placement; it does not yet make storage
  profiles, park/reload lifecycle actions, workload/reuse state, or runtime
  policy search first-class.
- [unverified proposal] Preserve a two-level boundary: Wavel searches a finite
  set of static/precompiled storage-placement and movement-witness profiles;
  a separate trace/workload policy layer chooses retain, park, reload, host
  offload, or recompute over time. Do not model runtime arbitrary destination
  routing as a Wavel capability.

## Implications / next actions

- [ ] Ask Le to approve expanding M1-S2/S3/S4 from compute+communication role
  placement to compute+storage+communication static profiles and witnesses.
- [ ] If approved, add an explicit post-calibration milestone for trace-driven
  offload/scheduling policy search instead of hiding dynamic policy inside the
  static Wavel A* state.

## Pointers

- `/home/lexu/wse3-performance-model/ROADMAP.md`
- `/home/lexu/wse3-performance-model/milestones/M1-wavel-pipeline-placement-plan.md`
- `/home/lexu/WaferEngine-staging/milestones/M3-idle-pe-tier.md`
- `/home/lexu/agent-memory/projects/WaferEngine-staging/memory/topics/m3-idle-pe-tier.md`
