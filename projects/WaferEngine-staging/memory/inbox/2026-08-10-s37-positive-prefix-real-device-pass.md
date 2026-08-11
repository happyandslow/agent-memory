# S3.7 positive-prefix reuse passed the real CS-3 gate — 2026-08-10

**Project:** WaferEngine-staging
**Author:** codex
**Status:** drained
**Drained to:** `memory/topics/m1-s37-prefix-reuse-device-gates.md` (2026-08-11)

## What happened / finding

- Situation: M1/S3.7 needed proof that the production runtime-input → RoundPlanner → device execution → sampled-token commit → ledger-verifier path works on a real WSE-3, rather than only in host tests or simfab.
- The tracked two-round case ran through `launch_device.py` on CS-3 with `P_BLOCK_SIZE=8`, `bsz=2`, `slot_count=2`, and 16 device steps per round. Round 0 was `start=0, F=16, REBUILD`; its successful sampled-token commit installed the resident ledgers. Round 1 used different sequence IDs and matched the first 8 prompt tokens, producing `start=8, F=9, PREFIX-REUSE` without host KV reload.
- The real-device verifier reported slot 0/1 owners `2000/2001`, 24 resident tokens each, and ledger reconstruction `OK` for both. `device_verdict.json` was written, the launcher exited `rc=0`, compile took 7.4 s, and device execution took 5.3 s.
- Device TSC for this deliberately tiny 16×16, 7-layer functional case reported 59,959.4 cycles / 54.5086 us per timed step after two warmup steps. This is gate evidence, not a representative model performance result.
- The implemented S3.1–S3.7 host surface is now one complete chain: fail-closed static/runtime input validation; exact-ID and direct token-prefix facts; exact-pinned, one-to-one bottleneck assignment; empty-first / oldest-evictable LRU replacement; common-start take-over/truncate; full-prompt miss force-decode; suffix-only positive-hit force-decode with `plen=0`; and success-only atomic owner, actual ledger, and LRU commit. `RoundPlan` is the final immutable execution/commit intent; launch does not replan.
- Supported before S4: equal-length batches containing exact hits, block-aligned content hits, all misses, mixed exact+miss full rebuild, empty-slot allocation, LRU victim replacement, and consecutive cross-sequence reuse. Unsupported until later milestones: unequal per-lane length/start/F and EOS (S4), capacity curve (S5), and the full mixed e2e matrix (S6).

## Implications / next actions

- [x] Treat S3.7 lower-half usage wiring as device-validated; retain the tracked config, runtime sidecar, and gate runner for regression.
- [ ] Before closing S3, fold the separate `KVStore` object into the on-host `RoundPlanner` controller, group validation at the input/planning/commit boundaries without changing behavior, and rerun the full host plus real-device inert gates.
- [ ] After that cleanup, decompose S4 ragged execution; continue applying the explicit real-device gate policy to every implementation step.

## Pointers

- `/home/lexu/WaferEngine-staging/models/qwen3_1p7b-decode/model_config/test_device_s37_prefix_reuse.json`
- `/home/lexu/WaferEngine-staging/models/qwen3_1p7b-decode/round_inputs/s37_prefix_reuse.json`
- `/home/lexu/WaferEngine-staging/models/qwen3_1p7b-decode/scripts/s37_device_gate.py`
- Related policy capture: `memory/inbox/2026-08-10-m1-every-step-requires-device-gate.md`
- Current source-of-truth tracking: `/home/lexu/WaferEngine-staging/milestones/M1-intra-pe-reuse.md`
