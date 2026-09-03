# G(C) v2, inter-call idle gaps, and the keep-vs-park question — 2026-09-03

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

You are reading the KV demand curve for Qwen3-4B on WSE-3 and need to know
(a) why the first-pass "shared pool" line collapsed below 256K and what the
corrected pool models say, (b) how long a request's KV sits idle between
agent calls — i.e. whether keeping it resident is a real trade-off or a
foregone conclusion — and (c) which per-token unit prices exist as
measurements. Charts (generated views; keep old and new side by side):

- old: `assets/2026-09-02-gc-demand-curve.png` — orange = uncapped
  contexts, whole session must fit or every call is a miss.
- new: `assets/2026-09-03-gc-demand-curve-v2.png` — orange = best-effort
  prefix residency (LRU trims tails, missing prefix is recomputed), green =
  harness caps context at C + whole-session LRU, black dashed = the old
  rule for reference.
- `assets/2026-09-03-gap-sharing.png` — idle-gap CDFs and provider
  re-creation share by gap.

Scripts: `wse3-performance-model/analyses/2026-09-02-gc-trace-study/{extract_claude_code_traces.py,replay_gc.py,gap_stats.py,plot_gc.py}`;
numbers in `results/gap_stats.json`, `results/gc_curve_*.csv`. Trace: 1,048
local Claude Code contexts, 102,517 API calls, Claude tokens, 1M-context
models, one user.

## What happened / finding

- **The old orange line was an artifact of the "must fit whole" rule, not
  of concurrency.** Median context per call is 284K, so below ~256K every
  session was declared infeasible. With the same harness cap the blue line
  uses, the pool gets 79–83 % prefix hits and lands within 15–20 % of the
  single-request curve; best-effort partial residency lands even closer
  (avoided prefill per call: 24K @32K, 46K @64K, 83K @131K, 100K @167K,
  138K @262K vs blue 21K/49K/94K/114K/155K). The residual gap is the real
  eviction effect. Le's instruction: do not mark a whole scenario as miss
  because context > capacity; partial residency with recompute of the
  missing prefix is the correct model (this is also physically right: an
  evicted prefix [0,k) can be recomputed by itself; the kept suffix K/V
  stay valid).
- **Idle gaps (measured):** inside a user turn (call follows a tool
  result, n = 97,639) p50 3.3 s, p90 22 s, p99 126 s; only 0.33 % exceed
  5 min. At the start of a user turn (after a human message, n = 3,830)
  p50 4.1 min, p90 50 min; 45 % exceed 5 min. Provider-observed prefix
  reuse: 96.4 % inside turns, 83.3 % at turn starts.
- **What the provider actually does (live-policy datapoint):** share of
  context re-prefilled by Anthropic's cache, by gap: 3.7 % (<1 min), 3.7 %
  (1–5 min), 8.8 % (5–15 min), 7.7 % (15–60 min), **95.9 % (>1 h)**.
  Creation tokens split 796 M on the 1-hour TTL vs 324 M on the 5-minute
  TTL. So the operator keeps this workload's prefix for ~1 h and pays a
  full re-prefill beyond it.
- **Concurrency depends entirely on the window definition** (Le objected
  to "3 active"): at each call, contexts with activity in the last 30 min:
  all p50 3 / p90 10 (77 % of calls see ≥ 2); main sessions p50 2 / p90 3.
  In a 60-s window: all p50 1 / p90 4 (45 % ≥ 2, driven by subagent
  fan-out); **main sessions p50 1, only 16 % of calls have a second main
  session active**. "Active" = had an API call inside the window, evaluated
  at every call (call-weighted, not time-sampled).
- **Unit prices that DO exist (correcting my 2026-09-02 claim that none
  were measured):** Qwen3-1.7B real-scale prefill on CS-3, 8,192 tokens
  cold: 1,001 ms = 8,180 tok/s; 16,384: 3,145 ms = 5,210 tok/s
  (super-linear; another 8K run 1,280 ms); host→device KV ingress affine
  `t = 0.18 ms + bytes / 0.797 GB/s` per band × 4 bands = 3.19 GB/s
  aggregate (another fit 3.56 GB/s), 8K KV reload measured 338 ms; D2H
  ~0.63 GB/s aggregate marginal; H2D physical ceiling 11.43 GB/s; Qwen3-4B
  decode on CS-3 1,081.7 tok/s at bsz 1 (785,769 cyc/token). Sources:
  `projects/WaferEngine-staging/memory/topics/s6a-prefill-warm-start.md`,
  `m2-s3-experiment-tracker.md`, ContextBase log K0mf3Dd2WF. No 4B prefill
  throughput yet; no on-chip far-pool reload time yet (M3 fitted models).

## Keep-vs-park: what the evidence settles and what it does not (TODO)

Trade-off variables: idle gap g; KV size S = 147 KB × context (bf16);
reload time t_r = S / BW_tier (+ fixed); recompute time t_c(context)
(super-linear); contention = probability the freed capacity would serve
another request during g. Park only pays when g > t_r AND the capacity is
contended; otherwise keeping is free in latency and idle capacity has no
taker.

- Inside a turn the answer is settled by the numbers: g p50 3.3 s while
  host reload of a 100K-token 4B context (14.7 GB at ~3.2–3.6 GB/s) is
  ~4–5 s and recompute is longer still — parking to host between calls
  cannot pay for itself. Keep.
- At turn boundaries (g p50 4 min, 45 % > 5 min) host parking is
  latency-neutral, and the provider's own behaviour (1-h keep) shows the
  operator still chose to keep. Whether to park is then purely a
  contention question.
- **Not settled — TODO:** the contention side. This dataset is one user
  (16 % simultaneity of main sessions), so it cannot price the opportunity
  cost of idle KV; a multi-tenant trace (Mooncake tool/agent trace with
  prefix hashes) is required. Also unpriced: on-chip far-pool park/reload
  over fabric (M3 fitted model, 4B geometry), 4B prefill throughput, and
  the decode-side cost of longer resident context. Until then the design
  default is: keep KV resident across intra-turn gaps unconditionally;
  park (fabric first, host second) only at turn boundaries under measured
  contention.

## Trade-off chart and framing corrections (Le, 2026-09-03)

`assets/2026-09-03-keep-vs-reload.png` (script `plot_keep_vs_reload.py`):
left = time to bring KV back (= break-even idle gap g*) vs context length
for reload at 3.2 GB/s (measured, 4 bands) and 12.5 GB/s (all channels,
expected — Le: the 3.2 figure is unfilled channels), recompute at the 1.7B
measured prefill rates, and egress at 0.63 GB/s if no host mirror exists;
horizontal bands = measured gap percentiles. Right = the same at the median
intra-turn gap in decode tokens forgone (@ 1,082 tok/s). Readings:
- decode tok/s cancels in keep-vs-reload — it sets the stakes, not the
  crossover; the crossover is g vs S/BW (reload) or n/prefill_rate
  (recompute).
- with a host mirror and 12.5 GB/s, reload of any context ≤ 256K is under
  the 3.3 s median gap (32K: 0.39 s; 100K: 1.2 s) — evicting is
  latency-cheap at every context; without a host mirror the 0.63 GB/s
  egress makes eviction the most expensive option.
- recompute crosses the median gap already at ~25K tokens (8.2K tok/s) —
  recompute is never the right recovery above that; reload is.
- Le's framing: the right comparison is against GPU(+host DRAM), where a
  4B model's KV sits in HBM (80 GB − 8 GB weights ≈ 490K tokens bf16, 4×
  the wafer's ~120K) — GPU has capacity near compute and slow decode;
  agentic workloads need little decode. Cerebras' decode edge only holds
  while KV is resident, and the chip is far more expensive, so idle lane
  time during tool calls is the critical cost; the account closes only with
  very fast tool calls, very efficient KV recreation (host mirror at full
  channel bandwidth), or workload co-design (small contexts, subagent
  decomposition). The provider's 1-hour retention is most likely DRAM
  tiering, not HBM residency.

## Pointers

- `wse3-performance-model/docs/analysis/2026-09-02-gc-trace-study-first-pass.md` §7 (revision)
- ContextBase log: https://context.ed-aisys.com/doc/2026-09-02-result-sram-supply-merit-order-and-kv-demand-curve-qwen3-4b-on-wse-3-2ITHmQd6XV (revision section appended 2026-09-03)
- related: `2026-09-02-sram-supply-and-kv-demand-charts.md`, `2026-09-02-score-buffer-wall-and-single-request-remote-kv.md`
