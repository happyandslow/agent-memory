# Inside a Qwen3-4B decode layer, softmax is the largest phase and drives both the context and batch slopes; the finest control-flow cut is 5 stages per layer — 2026-09-05

**Project:** wse3-performance-model
**Author:** claude (session 4b-wide-layer; profile by subagent 4b-block-tsc)
**Status:** captured

## Situation

You are cutting the 4B decode layer into pipeline stages, sizing ATTN vs
FFN blocks, or deciding which attention phase to optimise for long
context or batch.

## Finding (measured, CS-3, row-0 TSC at phase boundaries, 256² blocks, 7 runs, all byte-identical)

Cycles per layer per step (bsz 1, 2K / 8K / 23K): ATTN 11,886 / 14,176 /
20,931; FFN 5,802 / 5,797 / 5,814 (flat in context). Within ATTN at 2K:
QKV 1,660, QK-norm+RoPE 1,793, score 906, **softmax 3,808**, P·V 1,942,
O-proj 1,570, residual 208. At 23K softmax is 9,984 of 20,931.

- **Softmax carries 69 % of the context slope** (0.303 of 0.439 cyc per
  context token per layer; score 20 %, P·V 11 %, others 0) and **49 % of
  the ATTN batch slope** (3,345 of 6,846 cyc per batch element per layer).
  The three KV-walking phases sum to 15.8 cyc/context-token/step over 36
  layers — reproduces the context sweep's 16.07 independently.
- **A1 | A2 (projections | attention core) is 1 : 2.4 at 2K, 1 : 4.5 at
  23K** — not an even split; it buys 1.41× at most.
- Finest cut on existing control-flow boundaries: **A1 | scan | O-proj+resid |
  FFN up/gate+SiLU | FFN down** = 5 stages per layer (180 over 36 layers);
  longest stage 6,656 (2K) / 8,894 (8K) / 15,659 (23K) cycles → 1.79× /
  1.59× / 1.34× over ATTN-whole granularity. Chunking the scan helps only
  to k = 2 (its fixed collectives bind after that).
- **Highest-payoff move is not a cut: a cheaper softmax** (flash-style
  fusion into the scan, no separate max pass) hits the largest phase, both
  slopes and the chunking obstacle at once.

## Gotchas

- 29K cannot be probed (ATTN PE 960 B free); long-context point is 23K.
- Numbers are 256² block times; they transfer to smaller blocks only under
  a flat-time assumption that is NOT safe (collectives shrink with width,
  per-PE vectors grow) — re-measure at the target block size.
- Phase (i) is the out-of-D-cache SiLU (~10 % high). Only row 0 stamped.
- Probe overhead +0.02–0.11 %; the bsz-experiment patch is numerics-neutral.

## Pointers

- `analyses/2026-09-05-4b-phase-tsc/` (README with the stage-cut table,
  `phase-tsc.patch`, `results/phase_tsc.json`, `phase_breakdown.png` →
  `assets/2026-09-05-4b-phase-breakdown.png`); report Round 45.
- Related: `2026-09-04-4b-block-times-vs-batch-and-thin-stage-sram-fit.md`,
  `2026-09-05-4b-ht-tail-colour-repaint-race-and-8-stage-forced-prefill.md`
