# Reporting KV-farm and micro-pipeline progress against the 09-13 meeting — 2026-09-20

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## What happened / finding

When preparing the next weekly update, distinguish device timing/capacity from real-value serving, and single-block latency/throughput from full-depth performance. The 09-13 slides are the historical baseline; their Layout C closure is superseded by this week's communication rewrites.

- Le cancelled the Monday 2026-09-21 meeting while on leave and requested an asynchronous ContextBase update covering 2026-09-13 through 2026-09-20.
- Farm reporting boundary: 28,672 → 51,200 capacity for +3.6% device cycles/token compares each configuration at its own capacity. Farm K/V remain zero-filled; nonzero ingress/device correctness are not complete. It does not establish arbitrary farm-size scaling or equal-context speedup.
- Micro-pipeline reporting boundary: the large 3.7–3.9× single-layer regression is largely recovered, but 28,368 vs the later 26,529-cycle original baseline is still about +6.9% serialized latency. The N=4 two-layer feedback result (41,684 cycles/output, 1.63× versus serial) is a staging experiment; production retains the N=2 fix. Full-depth inter-block communication remains open.
- Reporting uses raw device cycles, avoiding inconsistent source clock conversions. Cohort throughput uses output span, not median inter-arrival time.

## Implications / next actions

- Next intended update focuses on the end-to-end communication loop, starting with a two-block handoff measurement; no completion date or full-model speedup is claimed.
- Existing detailed results were linked rather than duplicated into new topic notes. No new hardware experiments or Git mutations were performed for this reporting task.

## Pointers

- Published weekly report: https://context.ed-aisys.com/doc/2026-09-20-weekly-update-kv-farm-and-micro-pipeline-wojpR3nfUR (MeshAgent/WaferOS → Logs; linked from Project Overview and Logs).
- Farm evidence: https://context.ed-aisys.com/doc/kv-farm-s1-session-update-2026-09-17-streamed-max-bf16-trial-correctness-capacity-Csdm3TvlvC
- The 09-17 tall timing/design page now links to the updated status and lives under Logs: https://context.ed-aisys.com/doc/2026-09-17-tall-pipeline-per-stage-timing-feedback-double-buffer-design-D4321nBxuT
- Existing detailed state: `2026-09-20-3stage-micropipeline-state.md` in this inbox (pre-existing; preserved unchanged).
- Reviewed Claude histories: `4b-layout-kv-stream` / `266a2d43-bfe3-41bd-8e88-7a8b180158bf`; `4b-mini-ppl-debug` / `824688b0-1bbe-4637-99c5-03ed21f26380`, related continuation `2fb84936-496b-499c-8f48-9028f5a2ac44`. This task read their existing records; it did not send new turns to those sessions.
