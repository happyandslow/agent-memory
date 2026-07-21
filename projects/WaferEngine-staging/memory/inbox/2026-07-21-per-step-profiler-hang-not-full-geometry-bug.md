# Full-size KV profiler hangs at decode — it's the per-step profiler, not a full-geometry transfer bug — 2026-07-21

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation this applies to

The full-size (`fullT`) e2e KV-transfer profiler config reaches the device, then
flatlines: compile + runtime-load + run-start all log clean, but after
`SEEDS_SENT decode_recv_loop_start` there are **zero `DECODE_STEP` markers for
>15 min** — decode step 0's first `runtime.receive` blocks forever. Reproducible.
A smaller ladder rung (L5) ran fine earlier. Looks like a full-geometry /
full-layer KV-transfer bug. It is not.

## What happened / finding

- **Decisive isolation: `fullT` with `KV_PROFILE:0` (transfer kept, profiler off)
  completes all 256 decode steps in ~0.1 s.** So the full 512×512 / 28-layer /
  head_dim=128 KV-transfer path is fine. The hang is caused by the **new widened
  per-step profiler** (the 8→14 u32 blob + per-`kv_step`-state TSC timers + extra
  module vars in `prefill.csl`), at high layer count. Chasing a "full-geometry
  transfer bug" is chasing a phantom — flip `KV_PROFILE` off first to bisect.
- The new per-step profiler is a **task-table / `.data.hi` heavyweight**: it
  compile-overflows PE memory (`ran out of PE memory for task table` + `.data.hi`)
  on L5 (n_layers=8 but 128 heads / 64 kv_heads → large per-head `.data.hi`) and
  on an L5-dims + n_layers=28 probe. On `fullT` (only 16 heads, shorter seqs) it
  *just* fits at compile, then **deadlocks at runtime at max_layers_per_block=7 /
  n_ph=14** (the per-step reporter's emit/collect count vs 14 planes). The OLD
  coarse A/B/C profiler ran fine at L5 → the regression is the widening, not the
  transfer. (This is a *different* failure from the earlier mux emit-count hang
  already in the topic note.)
- Ruled out by device runs + code read: `head_dim` (kv_dim_per_pe=4 in both L5 &
  fullT, so the kv_transform tile is identical), `WARMUP` (pure TSC-window
  control), and n_ph=14 alone (profiler-off with n_ph=14 runs clean).
- **Answer to the "is it reformat, not transfer?" question (sim, idealized):**
  reformat is NOT the bottleneck. `kv_transform` = **1.54% of stage A**; A is
  ~5.7% of A+B → reformat ≈ 0.09% of the whole transfer. Within A the cost is
  **E/W-funnel-dominated** (states 0+1 = 86% of A); the north shift (B) is 94% of
  A+B. On real silicon A ≤ ~7% of A+B already caps all reformat, so transport
  dominates regardless. Device per-state numbers were NOT taken — Le dismissed
  fixing the profiler once the sim answer + the A≤7% bound settled it.

## Implications / next actions

- [ ] If the exact-silicon per-state breakdown is ever wanted, the per-step
      profiler needs a diet (fewer task-table slots / `.data.hi` bytes on prefill)
      **and** a fix to its emit/collect count at n_ph=14 — then it runs on the
      known-good `fullT` transfer path. Currently parked.

## Pointers

- Worktree `/home/lexu/we-p2` (branch `lexu/staging/kv-prof-p2`), model
  `models/qwen3_1p7b-e2e`. Uncommitted per-step instrumentation in
  `src/prefill/prefill.csl`, `src/decode/{decode,ht_tail}.csl`, `launch.py`
  (blob 8→14; sim-validated at L0 only).
- Configs `model_config/test_device_2x2blk_kv_prof_{L5,fullT}.json`.
- Relevant skills: `csl-pe-data-memory-shared-pool` (task-table vs `.data.hi`
  caps), `csl-odd-extent-fabric-forward-hang`, `cerebras-debugging`.
- Topic: `memory/topics/prefill-decode-transfer-bandwidth.md`.
