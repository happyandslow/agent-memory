---
summary: Automatic KV-slot replacement must fail closed when a round early-stops before the planned decode budget; host slot length may already be advanced past device-resident KV until M1-S4 defines actual-length/EOS commit semantics.
tags: [waferengine-staging, m1, s3, s4, kv-retain, early-stop, eos]
---

# Automatic replacement early-stop fails closed — 2026-08-08

Created by the 2026-08-10 maintain pass from `memory/inbox/2026-08-08-auto-replacement-early-stop-must-fail-closed.md`.

## Finding

When an automatic KV-slot round stops before its planned decode budget, `apply_round_start` and `extend` have already advanced the host slot length to the planned `RoundPlan.end`, while the device produced fewer resident KV positions.

Skipping `commit_round` protects owner/LRU metadata but is not enough: the length snapshot can still be a false high-water mark, and a later automatic round could plan from that inconsistent state.

## Current rule

Until M1-S4 defines ragged/EOS length and commit semantics, automatic mode must drain the trailing TSC and then **fail closed** before owner/LRU commit or the next round. Legacy manual no-retain early-stop behavior remains unchanged.

A host calling-flow test covers this boundary, and the full decode host suite passed with 248 tests in the source session.

## Follow-up

M1-S4 should replace this temporary fail-closed rule with explicit per-lane actual-length and EOS commit semantics.

## Pointers

- `models/qwen3_1p7b-decode/launch.py` (`_execute_runtime_rounds`, S3.5 success boundary)
- `models/qwen3_1p7b-decode/tests/test_launch_s35_calling_flow.py`
- `milestones/M1-intra-pe-reuse.md` (S3.5 and deferred S4 ragged execution)
