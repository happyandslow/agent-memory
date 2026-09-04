# Agentic decode: short per call, ~89 % hidden reasoning, decode-bound per turn — 2026-09-04

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

You are reading "output_tokens" from Claude Code transcripts as decode
length, or arguing that agentic decode is short so decode speed does not
matter. Script and numbers:
`wse3-performance-model/analyses/2026-09-02-gc-trace-study/{decode_breakdown.py,results/decode_breakdown.json}`;
figure `assets/2026-09-04-decode-breakdown.png`.

## What happened / finding

- **Per call, decode is short in both trace families** (measured): Mooncake
  toolagent output p50 30 tokens (100 % ≤ 2K), conversation p50 350;
  Claude Code p50 443 per API call, p90 3.3K, p99 10K.
- **Per user turn it is not small** (Claude Code, ~19 calls per turn):
  decode p50 14.4K tokens, p90 67K; newly prefilled tokens per turn p50
  24.7K. Decode/prefill token ratio p50 0.63 (decode > prefill in 25 % of
  turns). **In time the turn is decode-bound on both engines**: at CS-3 4B
  rates 2.7 s prefill + 15.1 s decode per median turn (decode dominates in
  80 % of turns); at H200 9B rates 0.34 s + 40.5 s (98 %). CS-3's decode
  speed shows per turn (≈ 18 s vs ≈ 41 s), not per call — the counterpart
  of the Mooncake per-request result, where prefill dominated.
- **Claude Code transcripts do not store thinking text** (thinking blocks
  carry only a signature; 0.1 % of messages even have the block). The
  median assistant message has 0.57 visible characters per output token
  vs ~3.8 for normal text, so most decoded tokens are invisible. Estimate
  (visible tokens = characters / 3.8, remainder hidden): **hidden
  reasoning ≈ 89 %**, visible text 2.7 %, Edit/Write tool inputs 4.2 %,
  Bash inputs 2.5 %, other tools 1.7 %; per call hidden p50 356 / p90
  3,021, visible text p50 26 tokens, Edit/Write p50 325. The visible answer
  is Mooncake-sized; the reasoning is what makes the per-turn decode budget
  14K. Hidden share is ±10 points (the chars/token constant is assumed).
- Consequence for sizing: a reasoning-light agent (or a small model without
  extended thinking) has an order-of-magnitude smaller decode budget per
  turn; a reasoning-heavy one is where fast decode pays.

## Pointers

- Report: `docs/reports/2026-09-04-4b-wide-layer-session-report.md` Round 14
- Related: `2026-09-03-gc-curve-v2-idle-gaps-and-keep-vs-park.md`,
  `2026-09-03-mooncake-percall-latency-serving-trace.md`
