# Per-request latency and KV-pool value on a real serving trace (Mooncake) — 2026-09-03

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

You want to position CS-3 against a GPU for agentic/tool inference and
need a timed, multi-tenant, real workload rather than one user's Claude
Code sessions; or you want to know whether on-chip KV residency matters on
a serving trace at all. Mooncake's public FAST'25 traces
(`kvcache-ai/Mooncake` → `FAST25-release/traces/`, one hour of Kimi
production traffic, ms timestamps, input/output lengths, 512-token prefix
block hashes) download directly on gala2; copies + sha256 in
`wse3-performance-model/analyses/2026-09-03-mooncake-trace-study/`.
Figure: `assets/2026-09-03-mooncake-percall-latency.png`. Doc:
`docs/analysis/2026-09-03-mooncake-percall-latency-first-pass.md`.

## What happened / finding

- **Trace shape (measured on the trace):** conversation 3.4 req/s, input
  p50 6.9K / p90 27K, output p50 350, 33 % of requests continue a session,
  inter-turn gap p50 126 s. Toolagent 6.7 req/s, input p50 6.3K / p90 17K,
  **output p50 30**, **70 % continue a session, gap p50 3.0 s** — the same
  3-second intra-turn gap as Claude Code (3.3 s), so it is a property of
  tool loops, not of one user. ~94 M unique tokens per hour in each trace.
  Session reconstruction gotcha: an earlier request's last block is partial
  (input not a multiple of 512), so match on its block list minus the last
  block; matching on the full list finds almost no continuations.
- **KV pool size is invisible on a serving trace.** Block-LRU token hit
  rate is flat from 32K to 1M tokens (conversation 4.0 → 5.6 %, toolagent
  27.5 → 35.9 %) and only approaches the infinite-cache value (37 % / 57 %)
  at 16–64 M tokens. A 120K on-chip pool and a 490K HBM pool give identical
  hit rates; what the small pools capture is the next call of the same
  agent loop seconds later. The "one session resident on chip" framing does
  not describe a multi-tenant chip; the relevant tier is DRAM/SSD and the
  lever is reload bandwidth.
- **Per-request latency model (4B constants; single stream, no queueing;
  CS-3 decode 954 tok/s and prefill 9,304 tok/s — both measured, expressed
  at the calibrated 750 MHz clock; reload 12.5 GB/s expected; GPU decode
  150 tok/s, prefill 40K tok/s, PCIe 25 GB/s all ASSUMED):** toolagent mean
  0.61 s (CS-3 + host mirror; p50 0.14) vs 0.80 (no mirror) vs 1.32 s (GPU;
  p50 0.22); conversation 1.22 / 1.60 / 2.50 s. **CS-3 is prefill-bound**
  (0.40–0.81 s of the mean) and the GPU is decode-bound (1.2–2.3 s). The
  host mirror cuts CS-3 prefill by a third for ~0.02 s of reload — cheap,
  keep it. (Earlier passes: 0.64/0.86 with the 1.7B prefill proxy;
  0.54/0.71 with measured prefill at the launcher's 0.85 GHz.)
- **Cost side:** single-stream lane-seconds over the 3,537 s trace: CS-3
  14.4–14.6K (= 4.1 wafers), of which prefill 65 %, decode 31 %, reload
  4 %; GPU 30–31K single-stream but a GPU batches tens of streams, so ~1
  card. Decode can be multiplied by pipelining requests across the four
  block rows (measured floor ≈ 4,500 tok/s per wafer) or by in-kernel
  batching (measured asymptote ≈ 2,100 tok/s, after two experiment-only
  kernel edits — see `2026-09-03-4b-batch-scaling-pipeline-and-750mhz-clock.md`);
  with a 4-stage pipeline the trace needs ≈ 2.6 prefill wafers + 0.5 decode
  wafer. **Prefill throughput per wafer, not decode batching, sets the CS-3
  device count on this workload.**
- Le's framing (2026-09-03): compare against GPU + host DRAM, not a lone
  wafer; GPU keeps far more KV near compute and agentic workloads need
  little decode; CS-3's price makes idle lane time during tool calls the
  critical cost; the account closes only with fast tool calls, efficient
  KV recreation, or workload co-design. Implications are to be argued from
  these per-dataset charts, not in general.

## Revision 2026-09-04 — measured H200 rates flip the single-wafer 4B comparison

GPU rates replaced by the MeshRT paper's H200 + SGLang measurements
(Qwen3.5-9B, bs 1: prefill 72,757 tok/s, decode 355 tok/s; used as 4B
proxy). Result: the single-wafer 4B deployment no longer beats the GPU on
mean per-request latency (toolagent 0.61 vs 0.57 s; conversation 1.22 vs
1.09 s) — prefill-heavy requests reward the GPU's 8× faster prefill more
than CS-3's 2.7× faster decode. A same-size comparison (MeshRT Qwen3.5-9B
kernels on two wafers, 750 MHz, hops excluded: decode 1,475, prefill
21,442 tok/s) leads the GPU again (toolagent mean 0.32 s, p50 0.07; conv
0.63 s). Lesson: the CS-3 side is decided by prefill throughput per wafer
at least as much as by decode speed; quote which kernel generation and
how many wafers whenever comparing. Doc §7; figure
`assets/2026-09-03-mooncake-percall-latency.png` (4 configs).

## Implications / next actions

- [ ] Replace GPU assumptions with measured single-stream vLLM/SGLang
  numbers for a 4B dense model.
- [ ] Measure 4B prefill throughput and bsz > 1 decode on CS-3.
- [ ] Queueing replay at the trace arrival rates → devices needed at an SLO.
- [ ] Same replay on SWE-smith / Nebius coding-agent trajectories (check
  timestamps exist).

## Pointers

- `wse3-performance-model/analyses/2026-09-03-mooncake-trace-study/{trace_stats.py,percall_latency.py,results/}`
- related: `2026-09-03-gc-curve-v2-idle-gaps-and-keep-vs-park.md`, `2026-09-02-sram-supply-and-kv-demand-charts.md`
