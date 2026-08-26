---
summary: M1-S3 is complete at kv-feature@f5252b3 after controller-ownership cleanup, 414 host tests, and a real CS-3 closure gate; S4-S6 remain separate.
tags: [WaferEngine-staging, M1, S3, S3.7, prefix-reuse, closure, device-gate, cs3, qwen3, performance, capacity, drained-inbox, 2026-08-25]
---

# M1/S3.7 prefix reuse device gates and full-model benchmarks — 2026-08-10/11

This topic was created by the 2026-08-11 maintain pass from the dated M1/S3.7 inbox captures. In-repo milestone state still lives in `/home/lexu/WaferEngine-staging/milestones/M1-intra-pe-reuse.md`; this note preserves the durable memory-layer facts and operational constraints.

## S3 closure — 2026-08-25

M1-S3 is complete on `lexu/staging/kv-feature@f5252b3`. PR #4 supplied the feature body and PR #5
merged the remaining closure artifacts. `RoundPlanner` now privately owns `KVStore`; launch uses the
controller's planning, start-action, success-commit, and immutable-snapshot seams instead of
coordinating a peer store. The post-cleanup host suite passed **414 tests**.

The real CS-3 closure gate reproduced the tracked two-round miss→positive-prefix flow:
`start/F = 0/16 → 8/9`; both final 24-token ledgers reconstructed `OK`; the launcher exited `rc=0`;
and no job remained. Ragged execution, capacity, and the mixed end-to-end matrix remain M1-S4, S5,
and S6. They are follow-on milestones, not S3 blockers.

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

Raw device cycles are the durable measurement. For the 2026-08-11 collaborator deck, throughput is converted with **0.85 GHz**, as requested for this decode benchmark. This is a local reporting convention, not a resolution of the project's open 0.85-vs-1.1-GHz TSC-clock question.

Reuse-length sweep, three appliance repetitions per point; every lane generates `G=255` tokens:

- miss: `P/R/F/G=1025/0/1025/255`;
- partial: fixed `P=1025,G=255`, with `(R,F)=(256,769),(512,513),(768,257)`;
- exact: `F=1,G=255,P=R+1`, with `R/P=256/257,512/513,768/769,1024/1025`.

The partial and exact series share resident-prefix length `R` on the x-axis, but not prompt length `P`. Partial reuse keeps the prompt fixed and shrinks the force-decoded suffix; exact reuse retains only the required one-token seed.

| Batch | Baseline miss | Partial reuse R=256/512/768 | Exact R=256/512/768/1024 |
|---:|---:|---|---|
| bsz=1 | 245.285M cycles | 210.731 / 176.171 / 155.839M cycles (1.164× / 1.392× / 1.574×) | 134.928 / 136.479 / 138.011 / 139.652M cycles (1.818× / 1.797× / 1.777× / 1.756×) |
| bsz=2 | 290.696M cycles | 255.852 / 221.281 / 189.308M cycles (1.136× / 1.314× / 1.536×) | 166.345 / 167.239 / 168.100 / 169.139M cycles (1.748× / 1.738× / 1.729× / 1.719×) |

Generated-output throughput at 0.85 GHz:

| Batch | Miss | Partial R=256/512/768 | Exact R=256/512/768/1024 |
|---:|---:|---|---|
| bsz=1 | 883.7 tok/s | 1028.6 / 1230.3 / 1390.9 tok/s | 1606.4 / 1588.2 / 1570.5 / 1552.1 tok/s |
| bsz=2 | 1491.2 tok/s | 1694.3 / 1959.0 / 2289.9 tok/s | 2606.0 / 2592.1 / 2578.8 / 2563.0 tok/s |

Most relative sample SDs were below 0.1%; maximum was 0.443%. Use these CS-3 device-TSC comparisons as the current S3.7 performance baseline; do not replace them with simulator timing or host wall-clock time.

## Temporal locality and slot capacity

Synthetic temporal-locality sweeps used ten rounds, `bsz=1`, `P=512=256 shared-prefix + 256 unique-suffix`, `G=0`, fresh sequence IDs, and multiple prefix groups. A content-prefix hit has `R=256,F=256`; a miss has `R=0,F=512`. Since `G=0`, the honest throughput metric is **logical prompt tokens/s**, `10×512×0.85e9 / cumulative_cycles`, not generated tokens/s.

Locality is controlled solely by the round-robin group sequence: W2=`A,B,A,B,…` gives reuse distance 1; W3=`A,B,C,A,…` gives 2; W5=`A,B,C,D,E,A,…` gives 4; no-reuse uses a fresh group each round. For this LRU trace, a group hits iff `reuse distance < SLOT_COUNT`.

- With `SLOT_COUNT=2`, W2 produced 8H/2M/0 victims, forced=3072, **23,087.2 prompt tok/s**; W3/W5/no-reuse produced 0H/10M/8 victims, forced=5120, and **12,260.8 / 12,261.0 / 12,275.7 prompt tok/s**.
- With `SLOT_COUNT=4`, W2 produced 8H/2M/0 victims, forced=3072, **23,038.5 prompt tok/s**; W3 produced 7H/3M/0 victims, forced=3328, **20,753.8 prompt tok/s**; W5/no-reuse produced 0H/10M/6 victims, forced=5120, and **12,251.6 / 12,258.9 prompt tok/s**.

Slots help when capacity crosses the locality working-set threshold, not merely because the configured count is larger.

## Recompute/reload interpretation and M3 discussion

The collaborator slide originally compared recompute with a theoretical host-reload ceiling that omitted the measured fixed floor, which made recompute appear slower over the entire plotted range. The corrected full-CS-3 E10 resume-only slice uses:

| Reused history H | 512 | 1024 | 2048 | 4096 | 8192 |
|---:|---:|---:|---:|---:|---:|
| Recompute | 37.9 ms | 76.9 ms | 158.3 ms | 333.5 ms | 735.1 ms |
| Host reload | 46.236 ms | 56.141 ms | 85.684 ms | 169.891 ms | 338.266 ms |

These measured lines cross near **700 tokens for this E10 slice**. This is not a universal eviction boundary: E10 prices resume-only delta reload; a full-target reload shifts with retained suffix and target length, and a real eviction decision adds D2H cost plus future-resume probability. Existing full-context estimates therefore remain separately scoped (about 932 tokens at suffix 256, 2756 at suffix 1024, and no crossing through history 4096 at suffix 4096).

M3's controller-facing contract should be placement-agnostic over static/precompiled storage profiles. Each profile must expose capacity and measured park/reload cost. A horizontal storage row attached to the lower edge of each PE block is the first candidate, not a committed topology. Nominal analytical capacity is about 10.5 MiB for a 1×256 row at 42 KiB/PE (about 672 tokens/block, about 13 rows for an 8K request). E1 must measure payload × distance × active rows × direction × transit mode before any eviction threshold is defensible; the existing 4.54 µs/step movement band is derived/unmeasured for M3.

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
