# Per-step KV offload: the perimeter bound only blocks streaming K/V IN, not scoring at the storage PE — 2026-09-07

**Project:** wse3-performance-model
**Author:** claude (session 4b-layout-kv-stream)
**Status:** captured

## Situation

You want a decode request's active context to exceed what the ATTN block's own
PEs can hold, so you look at the wafer's idle SRAM (FFN free bytes, unplaced
PEs, HT band) and immediately hit the published conclusion that any pool
outside the 256×256 ATTN block is "bandwidth-dead beyond a few thousand
tokens". The temptation is to stop there and treat off-block SRAM as unusable
for anything touched every step, or to grow the ATTN block instead.

## Finding

- **The bisection bound is a property of the direction of movement, not of the
  pool.** It says: every ATTN PE needs its own 16 B per 256-token slot per
  layer (`kv_cols = 4` dims × K and V × bf16), so the block wants ≈ 1 MB per
  slot per layer through a perimeter of 256 links × 4 B/cycle — ≈ 1,024
  cycles/slot/layer per edge against a ≈ 21.8K-cycle layer (measured, 785,769
  cycles / 36 layers, CS-3). That caps *streaming K/V into the block* at
  ≈ 5.4K tokens per edge (analytical, nominal 1 wavelet/cycle/link).
- **Reverse the direction and the bound disappears.** If the PE holding the K/V
  scores its own positions, per step per layer it needs only the query of its
  KV head in (4 GQA heads × 128 dims × bf16 = 1 KB) and sends only
  online-softmax partials out (`m[4], l[4], O[4][128]` f32 ≈ 2 KB) — **both
  independent of how many positions it stores**. Traffic per stored token goes
  to zero; K/V never crosses a link during decode.
- This is not a new algorithm: every ATTN PE already does exactly this for its
  own positions and merges via the block's Y max/sum all-reduces
  (`decode.csl:1436-1537`). The offload only enlarges the set of PEs taking
  part in the softmax. The merge is exact —
  `m = max(m_b, m_f)`, then `e^(m_b−m)·(l_b, O_b) + e^(m_f−m)·(l_f, O_f)` —
  and folds in at each block column's reduce root, so no other PE changes.
- **The real cost moves from bandwidth to `.text` replication**, which is the
  same objection that applies to simply enlarging the ATTN block. Per added PE
  (analytical): a 2× ATTN block buys ≈ 26 KB of K/V room per PE (17.3 KB of
  every added PE is a copy of the ATTN image, compiled); a scoring-storage PE
  buys ≈ 33 KB, because it needs neither projection weights nor the ingress /
  route-init / RoPE / QK-norm code, and joins none of the 256-participant
  collectives. Only +27 % — **the decisive advantages are shape freedom (any
  rectangle, not the square-`P` law) and leaving the block's collectives
  untouched**, not the byte count.
- Consequence for the exchange cards: a "far pool" is not automatically
  `mechanism: none` for per-step use. Ask first whether the pool can compute.

## Implications / next actions

- [ ] The ≈ 10 KB (8–12) scoring-PE code estimate is **analytical and
  load-bearing** — every capacity number depends on it. A single-PE `cslc`
  build of the scorer path settles it and is minutes of work.
- [ ] Largest unpriced term in the design is the hand-off into the block's
  reduce root: 8 heads × 520 f32 per layer on one row ≈ 4.2K cycles if
  serialised (analytical).
- **Promotion signal (procedural):** "when an on-chip pool looks bandwidth-dead
  for per-step access, check whether the computation can move to the data
  instead of the data to the computation" is a method, not a fact about this
  project. Proposed for a skill, not installed.

## Pointers

- `docs/design/2026-09-02-kv-farm-s4-layout.md` §3, §5.4–5.6 (+ `.zh.md`
  translation); figures `docs/diagrams/2026-09-02-kv-farm-{pe-budget,pe-math,split-axis}.png`
- bound as originally stated: `docs/design/2026-09-02-kv-storage-layout-stage-balance.md` §3.1
- related inbox: `2026-09-02-score-buffer-wall-and-single-request-remote-kv.md`
  (frames per-step offload as streaming K/V *to* the compute PE — this capture
  is the counterpoint), `2026-09-01-qwen3-4b-placement-generator-boundary.md`
- **staleness:** written against the 4-rows × 256² / 9-layers-per-row geometry.
  The thin-block and L = 4 results (2026-09-04..06 captures) changed the
  preferred geometry; the direction-of-movement argument is geometry-independent,
  the per-row capacity numbers are not.
