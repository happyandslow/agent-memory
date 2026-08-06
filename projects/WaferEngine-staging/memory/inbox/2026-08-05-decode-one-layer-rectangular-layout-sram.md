---
date: 2026-08-05
project: WaferEngine-staging
tags: [qwen3-1p7b, decode, layout, pipeline-depth, sram, ht]
---

# Shrinking Qwen3-1.7B decode blocks for one layer per pipeline stage

**Project:** WaferEngine-staging
**Author:** codex
**Status:** drained   <!-- drained 2026-08-06 into projects/we-pr14-depth-layout topic decode-pipeline-depth-layout.md + that project's plan -->

## What happened / finding

- Situation: increasing standalone decode pipeline depth from 8 blocks to 28
  blocks while retaining the 8,192-token KV capacity on PR 14 head `93a6d0e`.
- A rectangular `64 x 256` PE block works: use a `7 x 4` block grid, keep
  hidden/sequence/HT sharding on Y=256, and shard attention/FFN/KV-head work on
  X=64. All 28 blocks hold exactly one layer.
- The full device-size artifact compiled. Its tightest decode PE used 44,794 of
  49,152 bytes, leaving 4,358 bytes (8.9%). Compared with the recompiled
  `256 x 256` baseline, free SRAM fell by 4,768 bytes; 4,652 bytes of the
  increase was categorized as system/scratch, not model weights.
- A 28-stage rectangular simfab smoke test generated both requested steps and
  completed with `[run] SUCCESS` (compile 2.305 s, run 164.798 s). This checks
  completion/routing, not numerical accuracy or real-device throughput.
- A native `128 x 128` one-layer layout fails before decode SRAM is the issue.
  The current HT embedding mapping requests 37,984 bf16 values = 75,968 bytes
  per HT-head PE (`1187 vocab rows * 2 * dim_per_pe=16`), above the 49,152-byte
  PE capacity. HT tail also reports data-memory exhaustion.

## Implications / next actions

- [ ] Test the `64 x 256` layout for correctness and throughput on a real CS-3.
- [ ] Evaluate `128 x 128` decode blocks with a changed HT geometry and explicit
  `256 <-> 128` hidden-vector redistribution; changing only the config cannot fit.
- [ ] If the one-layer SRAM/performance margin is inadequate, evaluate the
  `128 x 256`, 16-stage fallback (twelve 2-layer blocks and four 1-layer blocks).

## Pointers

- `/home/lexu/we-pr14-depth-layout/docs/DECODE_PIPELINE_DEPTH_EXPERIMENT_2026-08-05.md`
- Worktree branch `lexu/staging/decode-pipeline-depth` at base `93a6d0e`
