# Session "4b-wide-layer" (2026-09-02/03): what was concluded about on-chip KV, SRAM levers, and CS-3's place in agentic inference

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

You are picking up the Qwen3-4B-on-WSE-3 work (SRAM for resident KV, layout,
batching, multi-wafer) or arguing where a CS-3 fits in agentic inference, and
need the settled conclusions with their evidence class before reading the
individual captures. Each bullet names the capture/doc that holds the numbers.
Charts (all generated views, scripts in the repo):
`assets/2026-09-02-sram-supply-merit-order.png`,
`assets/2026-09-03-gc-demand-curve-v2.png` (+ `2026-09-02-gc-demand-curve.png` old),
`assets/2026-09-03-gap-sharing.png`, `assets/2026-09-03-keep-vs-reload.png`,
`assets/2026-09-03-mooncake-percall-latency.png`, `assets/2026-09-03-bsz-scaling.png`.

## Conclusions (Le-confirmed decisions marked ★)

1. ★ **SRAM levers are priced by when their cost is paid (P0 boot / P1 per
   turn / P2 per step / P3 accuracy) and ranked as a supply merit order; no
   single formula**, because a lever's price and value depend on the already
   applied set. Ladder (bsz 1): 8K shipped → 23,040 (config) → 30,464
   (route table, CS-3-verified) → ~51K (KV fp8) → ~95K (near-pool stream) →
   167K wall. `2026-09-02-sram-supply-and-kv-demand-charts.md`,
   `docs/design/2026-09-02-sram-performance-exchange-methodology.md`.
2. **Score-buffer wall ≈ 167K tokens**: 32 B per 256-token slot of softmax
   scratch on the ATTN PE cannot be parked; invisible in bf16, binding after
   KV fp8/relocation; unlock = chunked/online-softmax scoring (= the same
   design as per-step KV streaming). Geometry changes are SRAM-neutral at
   equal PE count. `2026-09-02-score-buffer-wall-and-single-request-remote-kv.md`.
3. ★ **Single-request per-step streaming (P2) and multi-request park/reload
   (P1) are different designs**; a separate session owns the former
   (`docs/session-prompts/2026-09-02-single-request-remote-kv-and-chunked-score.md`).
4. **Demand side, own Claude Code traces (1,048 contexts, 102K calls):**
   96 % of input is re-sent prefix; ~19 calls per user turn; harness base
   context p50 51.5K; intra-turn idle gap p50 3.3 s; provider keeps KV ~1 h.
   With best-effort partial residency the pool curve sits within 15–20 % of
   the single-request curve. `2026-09-03-gc-curve-v2-idle-gaps-and-keep-vs-park.md`.
5. **Keep vs park:** inside a turn, keep (gap 3.3 s < any reload); at turn
   boundaries it is a contention question a single-user trace cannot price.
   Decode tok/s cancels in the comparison. Host mirror at full channel
   bandwidth is the precondition for cheap eviction (D2H egress measured
   1.37–1.44 GB/s for 4B). Same capture.
6. ★ **Compare against GPU + host DRAM, not a lone wafer; argue positioning
   per dataset, not in general.** On the Mooncake serving trace (real,
   timed, multi-tenant): pool size 32K–1M is invisible (hit rate flat);
   CS-3 is prefill-bound, GPU decode-bound; per-request latency favours
   CS-3 ~2× under assumed GPU rates; device count is set by prefill
   throughput (≈ 2.6 prefill wafers + 0.5 decode wafer vs ~1 GPU).
   `2026-09-03-mooncake-percall-latency-serving-trace.md`.
7. **CS-3 measurements (4B):** prefill 9,832 tok/s @8K, 9,304 @2K (750 MHz);
   decode 954 tok/s bsz 1; in-kernel batching saturates ≈ 2,100 tok/s
   (needs two small kernel edits, done in an experiment copy); stage
   pipelining floor ≈ 4,500 tok/s per wafer (measured on the 2-wafer demo);
   two-wafer PP costs ≈ 171 µs per crossing, ≈ 175·N µs/token, network
   ≈ 11 µs — multi-wafer is cheap if the controller is co-located.
   `2026-09-03-cs3-4b-prefill-measured-and-bsz-blockers.md`,
   `2026-09-03-4b-batch-scaling-pipeline-and-750mhz-clock.md`.
8. **Clock is 750 MHz**, not the SDK launcher's 0.85 GHz; cycles are
   canonical, "@0.85 GHz" seconds are 13 % optimistic.
9. **Softmax exp and SiLU are a few % of a decode step today** (exp was 24 %
   before the polynomial/SIMD rewrite; the D-cache pin is ≲ 1 %); a step is
   dominated by the ~6–8 Y all-reduces per layer (~830 cycles each) and
   row hops — decode is communication-bound. From
   `OPTIMIZATION_HISTORY.md` of the route-table tree.
10. ★ **Positioning thesis to test next:** Cerebras' agentic case is many
    small-context agent loops time-sharing a wafer with host-mirrored KV
    (fast decode, cheap evict/reload, stage pipelining), not one large
    context resident on chip; the account closes only if tool-call idle time
    does not strand the lane (keep inside turns, park at boundaries) and
    prefill throughput per wafer carries the workload.

## Open items

- Price the P2 class (streaming microbenchmark, fp8 dequant); chunked-score
  design (other session); layout/stage-balance (other session); pp hop
  optimisation = fewer SDK stream calls per token (pp-demo session).
- Replace assumed GPU rates with measurements; queueing replay; Qwen3
  re-tokenisation; SWE-smith/Nebius coding-agent trajectories.
- Kernel fixes for bsz > 1 in the tracked tree (SiLU scratch, tail
  partials loop, TOP_K buffers, KV-ingress staging tile) if batching is ever
  wanted alongside pipelining.

## Pointers

- Human-readable session report (round by round, all eight figures):
  `wse3-performance-model/docs/reports/2026-09-04-4b-wide-layer-session-report.md`;
  web version with embedded figures: https://claude.ai/code/artifact/52cee6ad-bc9a-4883-bcbc-dfd2b98fe338

- ContextBase (MeshAgent/WaferOS › Logs): session results with all six charts —
  https://context.ed-aisys.com/doc/2026-09-03-result-session-4b-wide-layer-kv-levers-cs-3-measurements-agentic-positioning-nQpvM1Pzcd ;
  earlier chart page `2026-09-02 Result — SRAM supply merit order and KV demand curve` (2ITHmQd6XV).
- Repo docs: `docs/analysis/2026-09-02-gc-trace-study-first-pass.md`,
  `docs/analysis/2026-09-03-mooncake-percall-latency-first-pass.md`,
  `docs/analysis/2026-09-03-cs3-4b-prefill-and-bsz-measurement.md`,
  `docs/analysis/2026-09-03-4b-two-wafer-pp-decode-demo.md` (pp-demo session).
