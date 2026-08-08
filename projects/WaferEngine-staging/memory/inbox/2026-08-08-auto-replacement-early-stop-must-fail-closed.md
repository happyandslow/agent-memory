# Automatic replacement early-stop must fail closed — 2026-08-08

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

- When an automatic KV-slot round stops before its planned decode budget, `apply_round_start` and `extend` have already advanced the host slot length to the planned `RoundPlan.end`, but the device produced fewer resident KV positions.
- Merely skipping `commit_round` protects owner/LRU metadata but leaves the length snapshot inconsistent; a later automatic round could plan from that false high-water.
- Until M1-S4 defines ragged/EOS length and commit semantics, automatic mode now drains the trailing TSC and then fails closed before owner/LRU commit or the next round. The legacy manual no-retain early-stop behavior remains unchanged.
- A host calling-flow test discriminates this boundary, and the full decode host suite passed with 248 tests.

## Implications / next actions

- [ ] In M1-S4, replace the temporary fail-closed rule with explicit per-lane actual-length and EOS commit semantics.

## Pointers

- `models/qwen3_1p7b-decode/launch.py` (`_execute_runtime_rounds` S3.5 success boundary)
- `models/qwen3_1p7b-decode/tests/test_launch_s35_calling_flow.py`
- `milestones/M1-intra-pe-reuse.md` (S3.5 and deferred S4 ragged execution)
