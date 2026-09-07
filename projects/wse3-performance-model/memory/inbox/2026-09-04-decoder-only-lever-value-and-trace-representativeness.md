**Status:** drained   <!-- drained 2026-09-07 by daily maintain pass -->

# Decoder-only lever value on traces, and what each trace can and cannot represent — 2026-09-04

**Project:** wse3-performance-model
**Author:** claude (session 4b-wide-layer; analysis by subagent decoder-lever-value)
**Status:** captured

## Situation

You are deciding whether on-chip KV work (capacity, keep-KV-across-calls)
or throughput machinery (pipelining/batching) is worth building for a
CS-3 used as a decoder, or you are about to cite the Claude Code or
Mooncake traces as "the agentic workload".

## Finding (measured on traces; economics modelled from measured CS-3 rates)

`docs/analysis/2026-09-05-decoder-only-lever-value.md`,
`analyses/2026-09-05-decoder-lever-value/`.

- Decode-heavy agentic calls' KV **is** reused: 99 % of Claude Code calls
  have a successor re-reading ≥ 95 % of it within 10–18 s; not keeping it
  costs a median 13.9 s reload at 3.2 GB/s = 61 % of the next call's latency.
- What is reused is the **input context**, not the decoded tokens (thinking
  is stripped; keeping decode-produced KV is worth ≤ 0.13 s per call).
- **Capacity binds**: median agentic context 309K; 29K fits 0.04 % of calls,
  167K covers 19 % of decode tokens. Mooncake-class traffic fits 29K (90 %)
  but only 37 % of its decode-heavy requests come back (p50 gap 159 s).
- Decode-stream concurrency p50 = 1 in both traces; a forced-prefill rate
  ≥ ~20K tok/s makes recompute beat reload at today's link.

## What the two traces represent (Le's concern, 09-04)

| | Claude Code trace (ours) | Mooncake FAST'25 |
| --- | --- | --- |
| who | one user (Le), 1,057 contexts, 46,650 calls after de-dup, 2026-08-04 → 09-02 | Kimi production, multi-tenant, 35,639 requests over ~41 days of sampled timestamps (0.003–0.007 req/s — a sample, not the full stream) |
| models | Opus 4.8 / Opus 5 / Fable 5 / Sonnet 5 with extended thinking, agentic coding harness | 2024 Kimi chat (pre-reasoning; k1.5 came 2025-01) |
| outputs | per turn p50 5.8K tokens, 75 % hidden reasoning | **no thinking**: output max 2,000 (hard cap; the ≥ 512 tail was synthesized once and shared by two traces), p99 0.9–1.1K, p50 30–350 |
| inputs | median context 309K | long: input p50 6–12K, p90 17–39K |
| represents | the newest usage *shape* (turn structure, thinking share, context growth, tool gaps) | the multi-tenant *input* side of a 2024 chat service (prefix sharing, arrivals) |
| cannot say | user diversity, arrival process, provider concurrency, cross-user prefix sharing | anything about reasoning-era decode |

Single-user duty cycle (decode engine time at 954 tok/s ÷ wall time): 1 %
per session (p90 7 %), 8 % within a turn. So filling S pipeline stages
with decode-heavy streams needs ≈ S / 0.08 ≈ 12·S users in-turn (≈ 50 for 4
stages, ≈ 700 for 54) — an operator-scale number, never a single box.
Provider-side effect absent from both traces: the harness's shared prefix
(≈ 51.5K tokens for Claude Code) is cacheable once for all users.

## Pointers

- Report Rounds 27–29 and §2b: `docs/reports/2026-09-04-4b-wide-layer-session-report.md`
- Correction of the trace counts: `2026-09-04-claude-code-trace-streaming-duplicates-correction.md`

## Bridge dataset (found 2026-09-04)

**ServeGen** (Alibaba Cloud Model Studio production, NSDI'26, arXiv
2505.09999; github.com/alibaba/ServeGen, Apache-2.0): four months, 12 models,
includes a **DeepSeek-R1 reasoning workload** (bimodal reasoning-length
distribution), per-model `chunk-i-dataset.json` (input/output length
distributions) + `chunk-i-trace.csv` (arrival rate/burstiness, per-client
CV), and `conversations_hashed.json` (block hashes, multi-turn structure).
Supplies the reasoning-era multi-tenant decode side Mooncake lacks and the
diversity/arrivals the Claude Code trace lacks; it is API/chat traffic, not
an agentic harness with tool gaps. Proposed next: rerun lever-evaluation
steps 1/4/5 on it.

## ServeGen analysed (2026-09-05, subagent servegen-trace-study)

`docs/analysis/2026-09-05-servegen-reasoning-workload-first-pass.md`,
`analyses/2026-09-05-servegen-trace-study/` (clone d70c8b2d). The release's
multi-turn conversation file (1,616 conversations, 5,720 turns, 24 h in
Feb 2025, per-turn input/output token counts + timestamps) recovers
per-turn reuse length, incremental prefill, decode length and gaps by
count arithmetic — no harness needed. Model-level datasets are fitted
distributions only; conversation hash lists are undocumented (counts used).

| axis | ServeGen R1 | Claude Code | Mooncake |
| --- | --- | --- | --- |
| output per request (incl. reasoning) | p50 792, p90 3,432, max 32,768; reason ratio bimodal 0.38/0.9 (mean 0.70) | per call p50 763; per turn 5.8K, 75 % hidden | p50 350, cap 2,000 |
| reuse length | p50 7,498 (UB), 82 % of input | ~302K context, 98 % re-sent | 37–57 % blocks |
| incremental prefill | p50 2,107 | small vs context | dominates |
| output re-enters next input | 83 % fully — reasoning kept | ~5 % — thinking stripped | 0 % |
| fits 29K / 167K | 78 % / 99 % of requests; 67 % / 98 % of output tokens | 0.04 % / 19 % of decode tokens | ~90 % / — |
| decode-stream concurrency | derived 26 mean / 68 peak @954 tok/s (released 16 req/s slice) | 1 | — |
| gaps | inter-turn p50 308 s | intra-turn 10.9 s | 3 s / 159 s |

Headline: multi-tenant reasoning traffic is decode-heavy (same per-call
output as Claude Code) but not deep-context (input p50 7.7K), and keeps
reasoning in context — so the 29K/51K capacity rungs and decoded-KV reuse
matter there, unlike on our own trace. Assumptions: verbatim-history upper
bound for reuse; unstated conversation model and selection; Little's-law
concurrency without queueing; per-model tokenizers.

## KV capacity across N wafers — proportional rule (2026-09-05)

capacity ≈ η × (N × 44 GB − weights) / KV bytes per token, η ≈ 0.13 for
today's kernels (two anchors: 4B one-wafer ceiling 29,184 → 0.12; MeshRT
GPT-OSS-20B 900K on 4 wafers → 0.135); 4B pool levers ≈ 0.39 / 0.68.
Per-wafer resident context stays ≈ 24–32K for dense-attention Qwen-class
models regardless of size; each wafer beyond the weight minimum adds ≈ 40K
(dense Qwen) / 155K (hybrid 9B) / 235K (GPT-OSS-20B); a weight-minimum
deployment (Qwen3-235B on 12 wafers) has ~3K per wafer. Table:
`analyses/2026-09-05-kv-capacity-scaling/table.md`; report Round 36.
