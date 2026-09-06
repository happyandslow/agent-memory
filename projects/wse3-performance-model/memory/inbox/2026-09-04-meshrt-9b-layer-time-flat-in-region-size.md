# MeshRT 9B decode: per-layer step time is flat in region size; the stage floor is SRAM — 2026-09-04

**Project:** wse3-performance-model
**Author:** claude (subagent `meshrt-9b-region-profile`)
**Status:** captured

## Situation

You are sizing pipeline stages for forced-decode ("decoder as prefiller") or
pipelined decode throughput on WSE-3 and need to know whether a smaller
layer region makes each layer slower, and how small a stage can get.
Full README with provenance and all wsjob ids:
`wse3-performance-model/analyses/2026-09-04-meshrt-9b-region-profile/README.md`
(configs, logs, results, phase-probe patch alongside).

## What happened / finding (measured, CS-3 device TSC, MeshRT Qwen3.5-9B
`layer_block`, bsz 1, 4K context, commit 288fe8ae, 12 jobs)

- Weighted per-layer cycles vs the published 256² (Full 14,719 / GDN
  15,949): 128×256 **−0.3 %** (fastest), 256×128 +6.6 %, 128×512 +1.1 %,
  512×128 +20 %, 256×512 +5.3 %, 512×256 +17 %, 512×512 +22 %. Over an 8×
  span of PE count the per-layer time barely moves; **width is the
  expensive axis** (X shards the hidden tile and KV, so wider meshes
  lengthen the collective chains bsz-1 decode is latency-bound on), height
  is nearly free. 512² loses at bsz 1 even though it wins 37 % at bsz 16.
- **Stage-size floor = per-PE SRAM, not time.** Resident weights scale as
  1/(W×H): 128×128, 64×256 and 256×64 (16,384 PEs) fail to link (`.bss`
  overflow); 128×256 (32,768 PEs, 88 % of the bank) is the smallest stage
  that exists without kernel changes → ≤ ~22 concurrent stages per wafer.
- **Phase split** (TSC probe around `post_ffn` in `full_layer_tile` /
  `gdn_layer_tile`, +61 lines, build 0.25–0.85 % slower): mixer/attention
  69–77 % of a layer step, FFN 23–31 % despite ~2× the MACs; a
  ~1,450-cycle per-step floor at every region size.
- Reproduction gate: published numbers matched to 0.0001 %; both
  published bsz-1 A/Bs reproduce. Negative gate: illegal meshes (200×256,
  264×256, 256×48, 256×272, 256×16) rejected by the generator's
  divisibility checks (mirrored as `@comptime_assert` at
  `src/Layer/layer.csl:1277-1284`).
- Analytical consequence: 1-layer stages at 128×256 → ~15.6K cycles per
  stage → ≈ 48K tok/s forced-decode throughput per 9B instance at 750 MHz
  (hops excluded) — the order of an H200's measured 72.8K tok/s prefill.

## Gotchas

- MeshRT's `layer_block` run reports both layer types from one job (272
  Full steps then 272 GDN steps, TSC on the phase-2 collective root PE).
- Upstream JSON/paper convert at 1.1 GHz; use cycles, or 750 MHz.

## Pointers

- Report: `docs/reports/2026-09-04-4b-wide-layer-session-report.md` Round 12
- Related: `2026-09-03-4b-batch-scaling-pipeline-and-750mhz-clock.md`,
  `2026-09-03-session-4b-wide-layer-conclusions.md`
