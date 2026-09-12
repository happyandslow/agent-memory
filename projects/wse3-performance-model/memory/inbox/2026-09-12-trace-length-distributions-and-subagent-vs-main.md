# Request length distributions of the three traces, and how subagent calls differ from main-thread calls — 2026-09-12

**Project:** wse3-performance-model
**Author:** claude (session 4b-pp-demo)
**Status:** captured

## Situation

You are deciding whether on-chip KV capacity should serve one request's growth
or several requests' parked KV, and need the input/output length distribution of
each workload trace side by side — or you are quoting "median context 309K" for
the Claude Code trace and need to know which subset that number describes.
Figure: `assets/2026-09-12-trace-length-distributions.png` (script beside it);
numbers: `wse3-performance-model/analyses/2026-09-12-trace-length-distributions/results/lengths.json`.

## Finding (recomputed from the sibling studies' raw files; tokens)

| trace | n | input p10 / p50 / p90 / p99 / max | output p10 / p50 / p90 / p99 / max |
|---|--:|---|---|
| Claude Code · main thread | 26,144 | 95K / **302K** / 719K / 955K / 1.0M | 166 / 763 / 3.8K / 10.6K / 64K |
| Claude Code · subagents | 20,506 | 29K / **100K** / 326K / 726K / 991K | 2 / **4** / 170 / 1.5K / 22.8K |
| Claude Code · all calls | 46,650 | 47K / 197K / 616K / 930K / 1.0M | 2 / 243 / 2.5K / 8.7K / 64K |
| Mooncake · conversation | 12,031 | 964 / 6.9K / 27K / 85K / 126K | 24 / 350 / 597 / 1.1K / 2,000 (cap) |
| Mooncake · toolagent | 23,608 | 1.8K / 6.3K / 17K / 62K / 126K | 3 / 30 / 507 / 897 / 2,000 (cap) |
| Mooncake · synthetic | 3,993 | 30 / 11.6K / 39K / 66K / 191K | 4 / 69 / 389 / 768 / 893 |
| ServeGen · DeepSeek-R1 | — | – / 208 / 2.1K / 23K / 57K | – / 792 / 3.4K / 12.6K / 32.8K |
| ServeGen · Qwen-Max | — | – / 812 / 2.4K / 6.2K / 31K | – / 56 / 433 / 840 / 9.3K |
| ServeGen · Qwen-Plus | — | – / 216 / 1.7K / 4.7K / 372K | – / 39 / 213 / 1.1K / 16K |
| ServeGen · Qwen-Turbo | — | – / 680 / 813 / 2.3K / 229K | – / 11 / 73 / 467 / 10.9K |

- **"Median context 309K" is the main-thread number.** Subagent calls are 44 %
  of all calls; including them the per-call median is 197K. Earlier captures
  that quote 309K (decoder-lever-value, gc-curve) describe main-thread calls.
- **Subagent calls are a different shape, not a smaller copy:** input median
  3× smaller (100K vs 302K; first call of a subagent starts at 18.6K vs 51.5K
  for a main session), output median 4 tokens vs 763 — 58 % of subagent calls
  emit ≤ 5 tokens and 70 % ≤ 50 (a tool call with no visible reasoning; Haiku
  subagents p90 = 4). Output is 1.5 % of subagent token traffic vs 11.6 % on
  the main thread. Intra-turn gaps are shorter (p50 8.3 s vs 14.9 s) and
  sessions shorter (15 calls vs 21, p90 46 vs 267). So the decode budget of the
  trace lives on the main thread; subagents are prefill-dominated fan-out.
- **Three worlds, not one workload.** Claude Code = huge input (p50 100–300K),
  medium output; Mooncake = input a few K (p99 ≤ 85K), output a few hundred
  (capped 2,000); ServeGen R1 = input a few hundred (p99 23K), output ~800
  (p99 12.6K, reasoning share p50 76 %). Every non-agentic trace has p99
  input inside the 29,184 placed-region ceiling; only the agentic harness
  needs more than the whole wafer (29K + ≈74K unplaced ≈ 103K) for a
  single request. "On-chip KV for one request's growth vs many parked
  requests" therefore has no workload-independent answer: for Mooncake /
  ServeGen the wafer holds tens of sessions; for Claude Code it holds a
  fraction of one.

### Subagent vs main-thread calls, side by side (Claude Code, 46,650 calls)

| | main thread (26,144) | subagents (20,506) |
|---|--:|--:|
| input context p10 / p50 / p90 / p99 | 95K / **302K** / 719K / 955K | 29K / **100K** / 326K / 726K |
| first call of a session, context p50 | 51.5K | 18.6K |
| output p10 / p50 / p90 / p99 / max | 166 / **763** / 3.8K / 10.6K / 64K | 2 / **4** / 170 / 1.5K / 22.8K |
| share of calls with output ≤ 5 tokens (≤ 50) | 0.2 % (1.1 %) | **58 %** (70 %) |
| output share of the class's token traffic | 11.6 % | 1.5 % |
| intra-turn gap p50 | 14.9 s | 8.3 s |
| calls per session p50 / p90 | 21 / 267 | 15 / 46 |
| output p50 by model | Opus 4.8 837 · Opus 5 673 · Fable 5 501 · Fable 5.1 1,145 | Opus 4.8 3 · Opus 5 3 · Sonnet 5 3 · Haiku 4.5 1 (p90 4) · Fable 5 74 |

Reading: subagent input is 3× smaller but still 10^5-scale (does not fit 29K
either); subagent output is essentially one tool call with no visible
reasoning, so the trace's decode budget lives on the main thread and
subagents are prefill-dominated fan-out.

## Gotchas

- ServeGen's release gives per-model mean/p50/p90/p99/max only; no p10, no
  raw per-request rows, so it cannot go on a CDF with the other two.
- Delivery of a cross-session request to 4b-wide-layer expired unapproved;
  the numbers above were recomputed directly from its result files instead.
- ContextBase MCP `update_document` with `editMode: patch` returned success
  (revision bumped) but left the document unchanged when the findText was a
  bullet line; `append` worked. Verify with `fetch` after a patch.

## Pointers

- `analyses/2026-09-12-trace-length-distributions/` (README, script, results)
- ContextBase: https://context.ed-aisys.com/doc/2026-09-12-data-request-length-distributions-of-the-three-traces-YWufPZhWnG (MeshAgent/WaferOS › Logs)
- Related: `2026-09-04-decoder-only-lever-value-and-trace-representativeness.md`,
  `2026-09-04-agentic-decode-is-mostly-hidden-reasoning.md`,
  `2026-09-03-mooncake-percall-latency-serving-trace.md`
