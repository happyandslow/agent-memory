# Qwen3-4B decode on CS-3: batch scaling measured, pipelining wins, and the clock is 750 MHz — 2026-09-03

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

You are sizing CS-3 throughput for a 4B-class decode deployment — choosing
between in-kernel batching (`bsz > 1`) and pipelining requests across the
block-row stages — or converting device TSC cycles into seconds. Figure:
`assets/2026-09-03-bsz-scaling.png`; doc
`wse3-performance-model/docs/analysis/2026-09-03-cs3-4b-prefill-and-bsz-measurement.md`
§3b; patch + configs + logs in `analyses/2026-09-03-cs3-4b-prefill-bsz/`.

## What happened / finding

- **Measured per-step cycles (CS-3, route-table decode tree, 4B):** bsz 1
  785,826 (TOP_K 20) / 747,815 (TOP_K 4); bsz 2 @8K 1,289,187; bsz 4 @4K
  2,102,119; bsz 8 @2K, TOP_K 4 3,300,460. Near-linear: ≈ 427K + 359K × bsz.
  Aggregate at 750 MHz: 954 / 1,164 / 1,427 / 1,818 tok/s; asymptote ≈
  2,100 tok/s per wafer (2.2× single stream). Each request adds its matvec
  work on every PE plus its share of every all-reduce payload; the
  batch-independent part of a step is only ~0.43M cycles.
- **Stage pipelining is the better multiplier:** the two-wafer demo
  measured a per-wafer period of 166K cycles/token with frames queued (one
  block-row period) → ≈ 4,500 tok/s per wafer at bsz 1, > 2× the batching
  asymptote, and it needs none of the SRAM fixes below.
- **What blocked bsz > 1 and what unblocked it (experiment-only edits,
  `bsz_experiment.patch`, tracked trees untouched):** (1) SiLU scratch
  moved out of the 512 B D-cache window (costs ≲ 1 % of a step); (2) HT
  tail loops matvec → Y reduce → local top-k per batch element through one
  `V_per_pe_x` partials buffer (numerically identical). Still binding:
  bsz 16 overflows the compute PEs (KV-ingress staging tile
  `bsz×kv_cols×prefill_max_per_pe×2×9` + per-batch activations); bsz 8
  fits only with TOP_K 4 (six `TOP_K×bsz` top-k buffers). TOP_K 20 → 4 is
  −38K cycles/step (−4.8 %) at bsz 1.
- **Clock: 750 MHz, not 0.85 GHz.** The two-wafer lockstep run pins device
  period to host loop period (1,037,474 cyc ↔ 1,382.9 µs). Every launcher
  "@0.85 GHz" tok/s is 13 % optimistic; the "host first-token wait = 1.134 ×
  device span" seen in prefill runs is 850/750. Canonical: decode bsz 1 =
  954 tok/s (host-wall 965); prefill 8K 833 ms = 9,832 tok/s, 2K 220 ms =
  9,304 tok/s.
- **Two-wafer PP hop (pp-demo session, measured):** two crossings per
  token cost 342 µs total ≈ 171 µs each, network ≈ 11 µs; the rest is one
  D2H + one H2D SDK stream round trip per crossing (fixed per-call latency,
  payload-insensitive: 5 KB and 8 B cost the same). N wafers in a chain add
  ≈ 175·N µs/token (N−1 hidden-state hops + 1 token return). Shrinking it
  means fewer stream calls per token (carry several in-flight requests per
  frame), not a faster wire.

## Gotchas

- `pkill -f "<pattern>"` inside a Bash tool call matches the tool's own
  shell; write the pattern as `"launch_si[m].py"`.
- The appliance compiles decode in ~1 min; a decode device run is ~4 min
  end to end — a job that returns in 3 min is not necessarily a failure.

## Pointers

- `analyses/2026-09-03-cs3-4b-prefill-bsz/{results/bsz_scaling.json,results/bsz_scaling.png,bsz_experiment.patch,configs/,logs_v2/,run_all_cs3.sh}`
- `docs/analysis/2026-09-03-4b-two-wafer-pp-decode-demo.md` (pp-demo session)
- related: `2026-09-03-cs3-4b-prefill-measured-and-bsz-blockers.md`, `2026-09-03-mooncake-percall-latency-serving-trace.md`
