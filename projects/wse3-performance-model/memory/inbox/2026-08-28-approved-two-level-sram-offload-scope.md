# Approved two-level SRAM-offload scope — 2026-08-28

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured   <!-- captured | drained -->

## What happened / finding

- When Wavel must cover both role placement and progressive KV-cache movement
  from compute PEs into spare on-wafer SRAM, Le approved expanding the project
  rather than creating a separate modeling stack.
- The approved boundary is two-level: static Wavel search selects only finite,
  precompiled role/storage/movement profiles; a separate trace-driven policy
  search decides when to retain, park, reload, evict, host-offload, or
  recompute. This prevents runtime-arbitrary routing from being assumed as a
  Wavel capability.
- The roadmap now places compute/storage/communication provider calibration in
  M2, static CandidatePlan/A* integration in M3, trace-driven policy search in
  M4, and bounded materialization in M5.

## Implications / next actions

- [ ] Complete M1-S1b evidence audit for
  `lexu/staging/m3-on-chip-kv-offload-study@255dab72c4231f85c28a82007bf4c2830696537d`
  before designing the expanded M1-S2 provider contract.

## Pointers

- `/home/lexu/wse3-performance-model/GOALS.md`
- `/home/lexu/wse3-performance-model/ROADMAP.md`
- `/home/lexu/wse3-performance-model/PROGRESS.md`
- `/home/lexu/wse3-performance-model/milestones/M1-wavel-pipeline-placement-plan.md`
