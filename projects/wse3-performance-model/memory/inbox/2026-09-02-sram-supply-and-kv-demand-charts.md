# SRAM supply merit order and KV demand curve — the two exchange charts — 2026-09-02

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

You are deciding how far to push on-chip KV capacity for Qwen3-4B decode on
WSE-3 (code slimming, KV fp8, streaming K/V from non-local SRAM, parking in
idle PEs) and need, on one page, (1) how many tokens each lever buys and at
what kind of performance price, and (2) how much a real agentic workload
would actually use that capacity. These two charts are that page. Both are
generated views: regenerate from the scripts, never edit the PNGs.

## Chart 1 — supply side: `assets/2026-09-02-sram-supply-merit-order.png`

Source: `wse3-performance-model/analyses/2026-09-02-sram-perf-exchange/{levers.json,plot_exchange.py}`.

What it shows: a waterfall of resident-KV capacity (batch-summed tokens,
bsz 1) as levers are applied in merit order, canonical fp8 track:
shipped 8.2K → raise `MAX_SEQ_LEN` 23.0K (compile-swept) → `.text`
slimming 30.5K (compile-swept; CS-3 A/B at 8K byte-exact, TSC +0.007%) → KV fp8 51.2K → near-pool KV separation
(FFN free SRAM / in-block storage columns) 95K → far-pool park/stream
(227K unplaced PEs + HT head + strips) 167K, clipped by the **score-buffer
wall** (red dashed: ATTN-local 32 B per 256-token slot that cannot be
parked; ≈ 5.47 GB ATTN budget ÷ 32,768 B/token). The first two blocks are
device- or compile-verified (the route-table lever was A/B'd on CS-3 on
2026-09-02: outputs byte-exact, TSC/token +0.007%, appliance ATTN PE
39,328 → 34,080 B); everything from fp8 onward is analytical.

How to read it: **color = when the performance price is paid** — green P0
free/one-time (boot), blue P1 per turn (park/reload), orange P2 per decode
step (+P3 accuracy gate for fp8). **Hatching = capacity or price not yet
device-verified**; only the first two blocks are solid. Vertical reference
lines: Qwen3-4B native 32K, YaRN 131K, and two measured workload marks from
the trace study (harness base context p50 52K, session max context p50
177K). The point of the chart: reaching a median agentic session requires
crossing into the orange (per-step-priced) region, so pricing the P2 class
(streaming microbenchmark, dequant cycles) is the highest-leverage
measurement.

## Chart 2 — demand side: `assets/2026-09-02-gc-demand-curve.png`

Source: `wse3-performance-model/analyses/2026-09-02-gc-trace-study/{extract_claude_code_traces.py,replay_gc.py,plot_gc.py}`;
1,045 local Claude Code contexts (283 main + 762 subagent), 102K API
calls, 2026-06-10..09-02; counts only; **Claude tokens, 1M-context
frontier models, one power user** — first pass, not a population sample.

Left panel `G(C)` = prefill tokens avoided per API call when resident KV
capacity is C. Blue: single request with the harness budgeted to C
(`E[min(ctx,C)] − E[new]`) — the curve for kernel decisions. Orange: shared
pool with session-LRU (idle 30 min) — the curve for multi-session serving;
on this workload it is near zero below ~256K because one session fills the
pool. Dotted verticals are the supply-side lever marks; red dashed is the
167K wall.

Right panel `dG/dC = P(context > C)` = share of calls that would use one
more token of capacity, i.e. the marginal value of capacity: 0.93 @32K,
0.80 @64K, 0.59 @131K, **0.51 @167K**, 0.36 @262K, knee beyond 262K.

Headline readings (measured counts, robust to modeling; only the tokenizer
shifts them): 96 % of input tokens are re-sent prefix; ~19 API calls per
user turn; median 1.9K new + 441 decode tokens per call; **harness base
context p50 51.5K** (subagents 18.5K) — a native-32K Qwen3-4B cannot host
this harness as-is. Model-dependent reading (upper bound, likely shifts
left under a 32K–262K model's compaction pressure): demand does not cut
the supply curve before the wall, so the cut is set by price alone.

## Pointers

- `wse3-performance-model/docs/design/2026-09-02-sram-performance-exchange-methodology.md` (price classes P0–P3, normalization, fail-closed cards)
- `wse3-performance-model/docs/analysis/2026-09-02-gc-trace-study-first-pass.md` (§5 limitations: tokenizer, compaction feedback, single user)
- related inbox: `2026-09-02-score-buffer-wall-and-single-request-remote-kv.md`, `2026-09-02-qwen3-4b-per-role-sram-breakdown.md`
- ContextBase log (both charts embedded, MeshAgent/WaferOS › Logs): https://context.ed-aisys.com/doc/2026-09-02-result-sram-supply-merit-order-and-kv-demand-curve-qwen3-4b-on-wse-3-2ITHmQd6XV
