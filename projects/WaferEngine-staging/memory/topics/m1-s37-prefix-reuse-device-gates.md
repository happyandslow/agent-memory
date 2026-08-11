---
summary: M1/S3.7 now has a real CS-3 positive-prefix reuse gate and full-model TSC baselines; future steps require explicit device gates, and S5 must separate batch size from slot count.
tags: [WaferEngine-staging, M1, S3.7, prefix-reuse, device-gate, cs3, qwen3, performance, capacity, drained-inbox, 2026-08-11]
---

# M1/S3.7 prefix reuse device gates and full-model benchmarks — 2026-08-10/11

This topic was created by the 2026-08-11 maintain pass from the dated M1/S3.7 inbox captures. In-repo milestone state still lives in `/home/lexu/WaferEngine-staging/milestones/M1-intra-pe-reuse.md`; this note preserves the durable memory-layer facts and operational constraints.

## Device-gate policy

Beginning with S3.7, each M1 implementation step must have a real-device verdict before it is marked complete or handed off as passed. Host tests, mocks, compilation, and simulator results remain useful diagnostic layers, but they do not replace a CS-3 gate.

For each step, define before implementation:

- the minimal, step-specific device config;
- the expected evidence and pass/fail gate;
- bounded runtime and retry policy;
- the artifact/log/verdict files that will be preserved.

If device access or execution is unavailable, report the step as incomplete/blocked rather than substituting simulator evidence.

## S3.7 positive-prefix reuse gate

S3.7 proved the production runtime-input → `RoundPlanner` → device execution → sampled-token commit → ledger-verifier path on a real WSE-3.

Tracked gate shape:

- `launch_device.py` on CS-3;
- `P_BLOCK_SIZE=8`, `bsz=2`, `slot_count=2`;
- 16 device steps per round;
- round 0: `start=0, F=16, REBUILD`, successful sampled-token commit installs resident ledgers;
- round 1: different sequence IDs with the first 8 prompt tokens matching, producing `start=8, F=9, PREFIX-REUSE` without host KV reload.

Evidence:

- real-device verifier reports slot owners `2000/2001`, 24 resident tokens each, and ledger reconstruction `OK` for both;
- `device_verdict.json` written;
- launcher exits `rc=0`;
- compile 7.4 s, device execution 5.3 s;
- tiny functional case TSC: 59,959.4 cycles / 54.5086 µs per timed step after two warmup steps. This is gate evidence, not representative performance.

The S3.1–S3.7 host surface is now a complete chain: fail-closed static/runtime input validation; exact-ID and direct token-prefix facts; exact-pinned one-to-one bottleneck assignment; empty-first / oldest-evictable LRU replacement; common-start take-over/truncate; full-prompt miss force-decode; suffix-only positive-hit force-decode with `plen=0`; and success-only atomic owner, actual ledger, and LRU commit. `RoundPlan` is the immutable execution/commit intent; launch must not replan.

Supported before S4: equal-length batches with exact hits, block-aligned content hits, all misses, mixed exact+miss full rebuild, empty-slot allocation, LRU victim replacement, and consecutive cross-sequence reuse. Unsupported until later milestones: unequal per-lane length/start/F and EOS (S4), capacity curve (S5), and the full mixed e2e matrix (S6).

## Full-model S3.7 performance baselines

Full Qwen3-1.7B geometry for the CS-3 TSC measurements:

- `dim=2048`, 28 layers, 16/8 GQA;
- `Pw=512`, `Ph=1024`, `P_BLOCK_SIZE=256`;
- `MAX_SEQ_LEN=1792`.

Reuse-length sweep, three appliance repetitions per point:

| Batch | Baseline miss | Partial reuse R=256/512/768 | Exact R=256/512/768/1024 |
|---:|---:|---|---|
| bsz=1 | 245.285M cycles | 210.731 / 176.171 / 155.839M cycles (1.164× / 1.392× / 1.574×) | 134.928 / 136.479 / 138.011 / 139.652M cycles (1.818× / 1.797× / 1.777× / 1.756×) |
| bsz=2 | 290.696M cycles | 255.852 / 221.281 / 189.308M cycles (1.136× / 1.314× / 1.536×) | 166.345 / 167.239 / 168.100 / 169.139M cycles (1.748× / 1.738× / 1.729× / 1.719×) |

Most relative sample SDs were below 0.1%; maximum was 0.443%. Use these CS-3 device-TSC comparisons as the current S3.7 performance baseline; do not replace them with simulator timing or host wall-clock time.

## Temporal locality and slot capacity

Synthetic temporal-locality sweeps used fresh sequence IDs and multiple 256-token prefix groups:

- With `SLOT_COUNT=2`, W2 produced 8 hits / 2 misses and 188.503M cycles; W3/W5/no-reuse all thrashed around 355M cycles.
- With `SLOT_COUNT=4`, W3 retained seven prefixes and improved from the matching 355.008M no-reuse control to 209.696M cycles (1.693×); W5 still thrashed at 355.218M cycles.

Slots help when capacity crosses the locality working-set threshold, not merely because the configured count is larger.

## Batch-capacity boundary

The unchanged full-model kernel compiles/runs at coupled `bsz=SLOT_COUNT=1,2`, but `3` and `4` fail before execution from `ht_tail` shared PE data-SRAM exhaustion. M4's known lower bound is already about 39,648 B/PE (19,008 B fixed lm-head tile + 19,008 B fp32 partials + top-k/merge/state), before compiler/DSD overhead. Task-table and decode-dcache messages are cascade/secondary. These failures have no TSC or ledger and are capacity-boundary evidence, not performance rows.

Implication for S5: separate batch size from slot count and include `ht_tail` batch scratch in the SRAM model; reducing decode `MAX_SEQ_LEN` alone cannot fix the observed bsz≥3 compile wall.

## CS-3 retry classification for long sweeps

Long appliance sweeps saw eight strict pre-worker HTTP-502 attempts in experiment A (8/56 launches) and one in B. Each had zero worker/TSC/ledger evidence, was archived, cooled down for about 300 s, and retried unchanged; only complete retry evidence was counted. A server-side `SUCCEEDED` state alone is insufficient when the client fails to retrieve TSC.

Future long sweeps: classify only zero-worker/zero-TSC HTTP 502 as retryable, archive it, wait about 300 s, and retry the identical logical point without counting the failed attempt.

## Pointers

- Milestone: `/home/lexu/WaferEngine-staging/milestones/M1-intra-pe-reuse.md`
- Gate config: `/home/lexu/WaferEngine-staging/models/qwen3_1p7b-decode/model_config/test_device_s37_prefix_reuse.json`
- Round inputs: `/home/lexu/WaferEngine-staging/models/qwen3_1p7b-decode/round_inputs/s37_prefix_reuse.json`
- Gate runner: `/home/lexu/WaferEngine-staging/models/qwen3_1p7b-decode/scripts/s37_device_gate.py`
- Perf evidence: `/home/lexu/.claude/jobs/bfd14235/tmp/results.jsonl`, `/home/lexu/.claude/jobs/bfd14235/tmp/expA_M1_summary_at24.json`, `/home/lexu/.claude/jobs/bfd14235/tmp/expA_summary_M2_at48.json`, `/home/lexu/we-m1-s3-perf-b/models/qwen3_1p7b-decode/exp_b/results/summary.csv`, `/home/lexu/we-m1-s3-perf-b/models/qwen3_1p7b-decode/exp_b/results/report.md`.
- Source captures: `memory/inbox/2026-08-10-m1-every-step-requires-device-gate.md`, `memory/inbox/2026-08-10-s37-positive-prefix-real-device-pass.md`, `memory/inbox/2026-08-11-m1-s37-prefix-reuse-device-benchmarks.md`.
