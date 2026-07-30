# What a forced token costs on pdSeparate with real weights — 13.50% of a free one — 2026-07-30

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are pricing a "rebuild the prefix in place" lane against reload-from-host or
re-prefill, and you need the forced-token cost **for the pdSeparate line with
real weights** — not the standalone-decode number with mock weights that
[[s6b-force-decode]] carries.

Also relevant if you are asking whether the layer-pipelining explanation of the
force-decode saving survives a change of weights and kernel line. It does.

## The setting (the number is meaningless without it)

Qwen3-1.7B, **real HF weights** rev `70d244cc`, prefill/decode-separated
kernel time-sharing **one CS-3 / WSE-3**, 524,288 PEs, 2×4 blocks, 28 layers ⇒
`max_layers_per_block = 4`, batch 1, workload `mtbench8`, store
`serve_2x4_8k20k_s2`, **n = 1** (one clean run; 6 serve attempts, 3 lost to EPCC
ingress 502s).

## The measurement

| | cycles | µs |
|---|---|---|
| free token | 556,354 | 654.53 |
| saving per forced step | 481,257 | 566.19 |
| **forced token** | **75,097** | **88.35** |

⇒ **forced / free = 13.50%, i.e. 7.41× cheaper.**

**This is a measurement, not two anchors subtracted.** Both runs have identical
per-round `steady_tokens` (1728, 665, 461, …), so the timing window is the same
step range in both; and the per-round saving is constant at **22.06–22.20 M
cycles (0.61% spread)** across rounds spanning 461 to 3,364 steps. A constant
per-round saving is exactly what "46 forced steps inside the window" predicts,
and it rules out a context-length or round-length effect.

## Why it matters beyond the number: it confirms the mechanism across lines

| line | weights | geometry | forced/free |
|---|---|---|---|
| standalone decode | mock | 28L / 8 blocks | 11.7 → 12.0% |
| **pdSeparate** | **real** | 28L / 8 blocks | **13.50%** |
| pipelining prediction `max_lpb / n_layers` | — | 4/28 | **14.29%** (upper bound) |

Two independent measurements, different weights and different kernel line, land
~1.8 pp apart and **both under the bound**. The layer-pipelining account of the
saving (rather than skip-compute) holds up. Corollary that already mattered
once: the ratio is an **architectural lever** — the deeper the block split, the
cheaper a forced token — so it must be re-derived, never carried across, when
`max_lpb / n_layers` changes.

## One process fact worth keeping

The correctness checker **refused** rather than passed or failed on the first
run: its invariant `len(ids) == generated_tokens + 1` was written before
`generated_tokens` was redefined to exclude the F−1 forced positions, and every
request was off by exactly 63 = m−1. Had it been written as "compare whatever
overlaps", it would have compared a shifted window and reported a plausible
wrong number. **Refuse-on-unrecognised-shape is what turned a silent
mis-comparison into a five-minute fix.** Continuation then passed at
**10,067 tokens, 8/8 requests, zero mismatches**.

## Implications / next actions

- [ ] `n = 1`. Repeat before this number carries a decision on its own.
- [ ] The forced/free ratio and the free-token cost were taken in the same run;
      do not mix this 654.53 µs free token with the 655 µs from the S0 baseline
      without checking they are the same window.
- [ ] Steps 1 and 2 of the plan collapsed into one run — the skip gate and the
      forced-input path shipped in the same CSL change, so no binary ever
      existed with forced input and the tail still computed. It passed, so
      nothing was paid; but the bisect that staging was supposed to buy is gone.
      Disable the gate and re-run one `F > 1` case to recover it if a later
      failure needs localising.

## Pointers

- Extends [[s6b-force-decode]] (which carries the mock-weight standalone numbers
  and the `x = 0.823` pipelining fit) with the real-weight pdSeparate point.
- `milestones/M2-tiering-cost-model.md`; worktree `/home/lexu/we-m2bench`,
  branch `lexu/staging/m2-benchmark`.
- Related: [[m2-s0-baseline-and-timer-provenance]],
  [[standalone-vs-integrated-kernel-parity]].
