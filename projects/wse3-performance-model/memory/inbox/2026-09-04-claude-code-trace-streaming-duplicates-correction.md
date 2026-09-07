**Status:** drained   <!-- drained 2026-09-07 by daily maintain pass -->

# Claude Code transcripts log one API call as several assistant records — de-duplicate by message id before counting — 2026-09-04

**Project:** wse3-performance-model
**Author:** claude (session 4b-wide-layer; found by subagent decoder-lever-value)
**Status:** captured

## Situation

You are counting API calls, decode tokens, prefill tokens, gaps or
calls-per-turn from `~/.claude/projects/**/*.jsonl` (Claude Code
transcripts), or reading any number derived from
`analyses/2026-09-02-gc-trace-study/results/` before 2026-09-04 evening.

## Gotcha

A streamed response is written as **several `assistant` records, one per
content block (thinking / text / tool_use), each carrying the same
`message.id` and the same `usage`** (identical `output_tokens`). Counting
records counts one call 2–3 times: in one sample 60,887 usage rows for
25,364 message ids; over the whole trace 58,581 of ~105K rows were repeats.
`decode_breakdown.py` additionally attributed a call's output tokens to
each block separately, which inflated the hidden-reasoning share.

**Fix:** keep the first record per `message.id` (usage is identical across
repeats); merge a call's blocks before attributing its tokens. Done in
`extract_claude_code_traces.py` / `decode_breakdown.py`; pre-correction
results kept in `results/pre-dedup-2026-09-04/`.

## Corrected headline numbers (Claude Code, 1,057 contexts, 46,650 calls, 4,032 turns)

| quantity | before | after |
| --- | --: | --: |
| API calls | 102,517 | 46,650 |
| intra-turn gap p50 / p90 | 3.3 / 22 s | 10.9 / 50 s |
| calls per user turn | ~19 | ~12 |
| prefix re-sent intra-turn | 96.4 % | 98.3 % |
| per-turn decode tokens p50 / p90 | 14.4K / 66.7K | 5.8K / 23.5K |
| per-turn new prefill p50 | 24.7K | 10.9K |
| hidden-reasoning share of decoded tokens | 89 % | 75 % |
| median turn CS-3 4B (8K rate / capped 29K curve) vs H200 9B rates | 17.7 / 26.0 vs 40.8 s | 7.3 / 10.5 vs 16.6 s |

Unchanged: per-session max context, G(C) curves, keep-vs-park logic,
decode/prefill ratio ≈ 0.6, CS-3 ≈ 1.6× faster per turn, turns decode-bound
in time on both engines, every CS-3 measurement.

## Pointers

- Report Round 28: `docs/reports/2026-09-04-4b-wide-layer-session-report.md`
- Captures amended with a CORRECTION section:
  `2026-09-04-agentic-decode-is-mostly-hidden-reasoning.md`,
  `2026-09-03-gc-curve-v2-idle-gaps-and-keep-vs-park.md`,
  `2026-09-04-4b-decode-cost-vs-context-and-device-ceiling.md`
