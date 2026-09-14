# KV farm: late merge on every PE + small-scope streaming merges replace the farm-wide max; next step is farm-vs-no-farm on the current 4-row layout — 2026-09-13

**Project:** wse3-performance-model
**Author:** claude (session 4b-layout-kv-stream)
**Status:** captured

## Situation

You are attaching a compute-at-storage KV pool ("farm") to the Qwen3-4B
decode ATTN block and must decide how the farm's softmax partials rejoin the
block's softmax without adding wide synchronisation, and you are about to
compare F1 (farm keeps the block's sharding) with F2 (whole head per farm
PE). You also need to know what Le decided about geometry and what the
first measurement is.

## Findings

- **No farm-wide max is needed.** The online-softmax merge
  `merge((m1,l1,O1),(m2,l2,O2)) = (max, Σ e^(mi−m)·li, Σ e^(mi−m)·Oi)` is
  associative and commutative, so every farm PE exps with its *own* local
  max and the triples combine in any tree. The earlier draft's "farm-wide
  max reduce → broadcast → exp → sum reduce" (a copy of the block's two-pass
  structure) was one unnecessary round trip. Refined flow per layer: local
  triple → streaming chain-merge in groups of 16 along the row → 15 group
  roots → 32 rows of the same head along one column, from both ends toward the
  class's middle row 128+h → head triple. Widest new sync = 32; every hop is a 2-party streaming handshake (header `(m,l)`
  first, `O` scale-added on arrival). Design rule from Le: minimise
  wide-range synchronisation; decompose into small scopes and combine.
- **Late merge, not root fold.** After the block's two existing Y reduces
  every block PE already holds `m_b = local_max_gqa_group_f32`,
  `num_b = output_f32`, `den_b = output_sum_f32` (`decode.csl` :1452–1457,
  :1489–1526; den packed at :1524). Replace the normalise at :1530–1534 with
  `out = (a_b·num_b + a_f·O_f)/(a_b·den_b + a_f·l_f)`, `a_x = e^(m_x − max)`.
  The farm then has the block's whole attention span to deliver (loose
  coupling); block-side change = that line on every PE + one 24-f32
  broadcast per column; no kernel loop or collective changes. Root-fold
  before the max reduce remains the fallback (root-only change, tight
  coupling). Three reduces, two roots (block: local row 136 =
  `(group_num/2)·pe_num_per_group + root_1st_phase`, `launch.py:407-408,461`;
  farm: one PE per head), one transport.
- **F1 vs F2 (analytical):** Q-in per block→farm row link is 2,048 vs 256
  wavelets — an 8× = n_kv structural ratio (F2's farm row shares one `Q_h`,
  F1's PEs each need a different slice); hand-off 5,120 vs 4,160 (1.2×);
  farm-internal chains ≈ equal once F2's row chain is 2-phase; capacity
  1.6× for F2 only because F1 cannot use a 241-column band. Single-request
  re-arrangement (block→farm when the recent window fills) costs the same
  bytes in both (36,864 B per position on the one writing row ≈ 1.2 % of a
  token) and can hide in the ATTN block's idle phase. Byte capacity per PE is
  the same; the choice is links and width. Tied to side-by-side geometry:
  a column-aligned (stacked) farm would flip it to F1.
- **Block-side ring is small.** `process_kv` today silently drops at
  capacity (`decode.csl:1260`). A ring needs only `iter_num mod
  kv_len_per_pe` plus "send the slot out before overwriting"; **no scoring
  window rotation** — softmax is permutation-invariant and K is stored
  post-RoPE. Common to F1/F2.
- **Parked (Le):** the "true ring" (storage-only pool, block rotates
  segments in) — ≈ 4·C cycles/layer, 4–17× at 100K for 1.33× capacity;
  revisit only after the compute-at-storage variant is measured
  (`docs/design/2026-09-08-kv-harvest-mechanism.md` §8.7).
- **Hand-off (Le, 2026-09-13):** eight entry rows (block rows 128+h, one per
  head) + a per-column flood from the keeper, replacing a root-row keeper;
  colours alias K-pipe ids; implement this version exactly as the figures,
  measure, then reason about better variants.
- **Decision (Le, 2026-09-13):** do **not** overlap this with Layout C.
  Implement the farm on the current 4-row × 256² layout exactly as drawn
  (S4 frames), and measure against the shipped no-farm image: per-token time
  vs context length, to get the penalty curve as context grows.

## Implications / next actions

- [ ] V1 compile-only of the S4 layout with a routing-only farm stub; V2
  single-PE compile of the farm scorer (the ≈ 10 KB code estimate is
  load-bearing).
- [ ] Comparison protocol: baseline = shipped image (30,464 ceiling), farm =
  same request with prefix in the farm; sweep context {8K, 16K, 30K, 46K,
  60K, 76K}; metric = HT-tail per-token TSC; simfab first, device on Le's go.
- [ ] Knobs to A/B without touching block loops: group size (16/32/60),
  chain vs tree, one entry row per head (256 keeper taps, ≤128-row flood) vs
  32 entry rows per head (every block PE taps 520, 8-row flood), early vs
  late merge. First version = the figures as drawn (Le: implement exactly,
  measure, then reason about better variants).

## Pointers

- `docs/design/2026-09-02-kv-farm-s4-layout.md` §5.4–5.7, §6 (+ `.zh.md`)
- `docs/diagrams/2026-09-02-kv-farm-step-t0..t8.png`,
  `2026-09-02-kv-farm-steps-sheet.png`, `2026-09-02-kv-farm-reduce-roots.png`,
  `2026-09-02-kv-farm-timeline.png`; generator
  `docs/diagrams/gen_2026-09-02-kv-farm-figures.py`
- related inbox: `2026-09-07-score-at-the-storage-pe-not-stream-kv.md`,
  `2026-09-07-4b-floorplan-degrees-of-freedom-ht-head-tail.md`
