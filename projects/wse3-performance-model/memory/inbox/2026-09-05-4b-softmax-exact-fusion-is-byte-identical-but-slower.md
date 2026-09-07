**Status:** drained   <!-- drained 2026-09-07 by daily maintain pass -->

# Fusing the 4B softmax passes (sum, cast) into the exp pass is byte-identical but 8–14 % slower; the real lever is DSD overhead and the exp kernel — 2026-09-05

**Project:** wse3-performance-model
**Author:** claude (session 4b-wide-layer; work by subagent 4b-block-tsc)
**Status:** captured

## Situation

You want to speed up the softmax phase of the Qwen3-4B decode attention
(the largest phase, 69 % of the context slope — see
`2026-09-05-4b-phase-profile-softmax-dominates-stage-cut.md`) and are
tempted to fuse its passes.

## Finding (measured on CS-3, 10 device jobs, all byte-identical)

The phase is five passes over the score vector: max reduce, subtract/scale
prologue, SIMD-4 exp, sum reduce, bf16 cast. Only the exp pass scales with
context (1,736 → 6,469 cyc/layer, 2K → 23K); the max reduce (~1,030) and
the prologue (~960) are flat, and **the prologue is per-slot overhead, not
arithmetic** (37 % of the phase at 2K bsz 8).

Folding the sum and the cast into the exp pass (variants a1/a2/c) stays
**byte-identical** at every config — including 23K where a slot spans two
tiles — **but is slower: softmax +7.6 to +13.7 %, ATTN layer +3 to +9 %,
step +2.5 to +6 %.** The removed passes were single bulk DSD ops over a
long contiguous vector (a whole cast = 170 cycles for 368 elements);
folding them costs one DSD set-up per tile plus per-element work in the
scalar prologue/tail. Removing three `@set_dsd_length` per tile and
inlining the slot function recovers about half of that loss.

**Lever:** fewer and longer DSD operations (per-slot overhead), the
≈ 2,000 cyc/layer of fixed collectives, and a cheaper exp kernel — not
pass fusion. The online/flash variant (running max, no separate max pass)
was not built; it needs a restructure of score → softmax → P·V, not a
fold.

## Pointers

- `analyses/2026-09-05-4b-softmax-fusion/` (anatomy.md, softmax-fusion-a.patch,
  results/timing_table.txt, gates.txt); report Round 49.
