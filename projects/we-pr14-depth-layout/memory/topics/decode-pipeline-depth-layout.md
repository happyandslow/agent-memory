---
summary: Qwen3-1.7B decode pipeline-depth vs SRAM/throughput tradeoff on PR14 — one-layer-per-stage rectangular blocks (64x256, 28 stages) fit but lose 22-25% decode throughput and 42% max context vs the 8-stage 256x256 baseline; 128x128 fails on HT embedding SRAM.
tags: [we-pr14-depth-layout, qwen3-1p7b, decode, pipeline-depth, layout, sram, ht, cs3]
---

# Decode pipeline-depth layout (Qwen3-1.7B, PR14)

## Summary

Experiment: raise standalone-decode pipeline depth from the baseline **8-stage 256x256**
blocks (multiple layers/stage) to **one-layer-per-stage** layouts, while holding the 8,192-token
KV capacity, on PR #14 head. The motivating payoff is decode-side pipelined prefill: more stages
means more in-flight tokens. The measured cost is a **throughput and max-context regression** on
the deeper layout, and a hard **HT-embedding SRAM wall** that blocks the squarest one-layer block.
Device TSC at 0.85 GHz is authoritative throughout; sim runs check completion/routing only.

Work repo: `/home/lexu/we-pr14-depth-layout` (branch `lexu/staging/decode-pipeline-depth`,
base `93a6d0e`; the 2026-08-06 CS-3 profile ran on upstream/main `b136ab64`, remote
`happyandslow/WaferEngine` fork). Primary report:
`docs/DECODE_PIPELINE_DEPTH_EXPERIMENT_2026-08-05.md`; raw:
`models/qwen3_1p7b-decode/bench/results/`.

## The layouts

| layout | block grid | stages | layers/stage | verdict |
| --- | --- | --- | --- | --- |
| baseline `256 x 256` | — | 8 | multi-layer | reference |
| `64 x 256` (rectangular) | `7 x 4` blocks | 28 | exactly 1 | **fits + compiles device-size** |
| `128 x 128` (native square) | — | 28 | 1 | **fails before decode SRAM** — HT embedding wall |
| `128 x 256`, 16-stage fallback | — | 16 | twelve 2-layer + four 1-layer | not yet built |

The `64 x 256` layout keeps hidden/sequence/HT sharding on Y=256 and shards
attention/FFN/KV-head work on X=64; all 28 blocks hold exactly one layer.

## SRAM (device-size compile)

- `64 x 256` tightest decode PE: **44,794 / 49,152 B used, 4,358 B free (8.9%)**.
- Vs a recompiled `256 x 256` baseline, free SRAM fell by **4,768 B**; **4,652 B** of that
  increase is system/scratch, not model weights.
- `128 x 128` fails first on **HT embedding**, not decode compute: the current HT-head mapping
  requests `1187 vocab rows x 2 x dim_per_pe=16 = 37,984 bf16 = 75,968 B per HT-head PE`, above
  the 49,152 B PE capacity. HT tail also reports data-memory exhaustion. ⇒ changing only the
  config cannot fit `128 x 128`; it needs a changed HT geometry and an explicit `256 <-> 128`
  hidden-vector redistribution.

## Max sequence length (device-authoritative)

- Baseline: **32,512** (32,768 is the signed-i8 KV-stride structural boundary).
- `64 x 256`: **18,688** (18,944 fails PE `.data.hi` + task-table memory).
- ⇒ candidate capacity is **57.48%** of baseline, a **42.52% reduction**.

## Decode throughput (device TSC, 0.85 GHz, bsz=1)

Shared decode-step pilot over D={64,128,256,512} selected **D=64**: every D within 1% of D=512
for both layouts, all CVs < 1%.

| context position | baseline `256 x 256` (tok/s) | `64 x 256` (tok/s) |
| ---: | ---: | ---: |
| 256 | 1850.5 | 1425.4 |
| 1024 | 1784.2 | 1380.7 |
| 4096 | 1702.1 | 1314.3 |
| 8192 | 1644.0 | 1259.4 |
| 16384 | 1538.7 | 1162.2 |

The deeper `64 x 256` layout is **22.6–24.5% slower**. Baseline-only tail: 1378.1 tok/s at
24,576 and 1317.7 at 32,000.

## Dedicated prefill (device TSC, 0.85 GHz) — position-dependent winner

- c512 wins at 256/1024: **4532.2 / 13761.8 tok/s**.
- production c768 wins at 4096/8192: **23583.6 / 24700.2 tok/s**.

Dedicated prefill is the achieved prefill comparison.

## The pipelined-prefill upper bound is NOT a measurement

Nominal-depth decode-side pipeline-prefill numbers are **upper bounds, not measurements**:
baseline roughly 13–15k tok/s, `64 x 256` roughly 35–40k over matched positions. At position 256
the nominal-depth arithmetic is `1850.5 x 8 = 14,804.0 tok/s` (baseline) and
`1425.4 x 28 = 39,911.2 tok/s` (`64 x 256`, 2.696x the baseline estimate). This multiplication
assumes every pipeline stage accepts independent prefill tokens at the measured steady-state
decode initiation interval, with no fill/drain, dependency, collective, input, or output
bottleneck. **It must not be reported as achieved throughput without an actual pipelined-prefill
run.**

## Correctness / provenance caveats

- A 28-stage rectangular **simfab** smoke test generated both requested steps and completed with
  `[run] SUCCESS` (compile 2.305 s, run 164.798 s). This checks completion/routing only — **not
  numerical accuracy or real-device throughput**.
- Local SDK 2.10 sim artifacts and CS-3 appliance/server 1.13.2 device artifacts are **not
  byte-identical**; source/config hashes match. **Device artifacts and device measurements are
  authoritative.**

## Reusable execution lessons (CS-3 / SdkLauncher)

- `SdkLauncher.run()` returns stdout but does **not** auto-retain worker files. Download
  `run_summary.json` and a compact compiled-artifact manifest with `download_artifact()` before
  leaving the launcher context; a new launcher cannot recover old ephemeral worker output.
- Decode summaries store `config` as the artifact directory, commonly prefixed with `out_`;
  layout inference must handle that controlled prefix.
- Dedicated-prefill verdicts use `tsc.per_round`; readers should also accept the older
  `per_round_tsc` form.
- CS-3 sync deletion can remove git-ignored remote results — copy every device-authoritative
  result locally before the next sync.

## Next actions

- [ ] Test the `64 x 256` layout for correctness and throughput on a real CS-3.
- [ ] Test the remembered `128 x 128` one-layer layout with a changed HT geometry and explicit
      `256 <-> 128` hidden-vector redistribution (config-only cannot fit).
- [ ] Investigate changing HT geometry/size to relieve embedding SRAM pressure.
- [ ] If one-layer layouts stay unsuitable, evaluate the `128 x 256`, 16-stage fallback
      (twelve 2-layer blocks + four 1-layer blocks).
- [ ] Validate the decode-derived pipeline-prefill upper bound with an actual multi-token
      pipelined-prefill implementation before reporting it as achieved.

## Provenance

Drained from two dated captures (2026-08-06 maintain pass):
- `projects/WaferEngine/memory/inbox/2026-08-06-qwen3-1p7b-decode-pipeline-depth-profile.md`
  (author codex — CS-3 profile, throughput/max-context/prefill numbers).
- `projects/WaferEngine-staging/memory/inbox/2026-08-05-decode-one-layer-rectangular-layout-sram.md`
  (author codex — layout/SRAM feasibility).

ContextBase log:
https://context.ed-aisys.com/doc/2026-08-06-result-qwen3-17b-decode-pipeline-depth-profile-tWZ5gVLrVO

## Related

- Assets: `assets/color-audit/` — qwen3_4b-decode color-audit SVGs (device 2x4 8k; sim 2x4 bsz2).
- Sibling SRAM work in `[[pe-sram-memory-breakdown]]` (WaferEngine) — the `.text`-dominated
  per-PE budget this depth study pushes against.
