# Micro KV farm: a "thin" storage row, and why 1-in-2 inside the block can never beat shipped capacity cheaply — 2026-10-02

**Project:** wse3-performance-model
**Author:** claude (session 4b-multicore-prefetch)
**Status:** captured

## Situation this applies to

You are looking at a KV-storage PE design on the shipped Qwen3-4B decode block
(or any row-sharded hidden-state block) and either (a) the storage PE's image
is far bigger than its K/V arrays, or (b) a "pair / 1-in-k" variant holds the
same bytes as the shipped rows and you cannot see why capacity did not grow,
or (c) you are deciding between halving the attention PEs and spending extra
PEs for storage.

## Finding 1 — an ATTN PE has two independent roles, one per block axis

- **Row y = hidden-dim role**: owns x[10y:10y+10] (dim_per_pe = 10, 256 rows
  × 10 = 2560): W_Q/W_K/W_V input-row slices and W_O output-row slices for
  those 10 dims (7,200 B over 9 layers), attn-norm table, QKV partial + Y
  all-reduce membership, O-proj partial + X all-reduce, residual, and the A/B
  interface with the FFN row of the SAME y (1:1 row match).
- **Column x = KV role**: 4 head dims of one kv head (kv_cols = 4, 32 columns
  × 4 = head_dim 128) and 16 Q dims; the K/V cache is
  [layer][4 head dims][positions], positions p ≡ y (mod 256) sit on row y.
- "The storage row has no hidden dim" means it drops the ROW role. The K/V
  cache's dimension axis is the HEAD dim (column role) and is untouched.
  Figure: `docs/diagrams/2026-10-02-micro-kv-farm-thin-storage-row.png`.

## Finding 2 — why PAIR_SHARED (1-in-2, zero local KV) tops out at ~17K < shipped 28K (measured, CS-3 compile-only fit)

- The storage row kept the whole row role (option N, chosen to avoid the
  routing rebuild): 29,760 B fixed before the first position (≈17 KB .text,
  7.2 KB weights, norms, RoPE, ingress buffer, X/QKV working set). Slope 145.5
  B per stored position (9 layers × 16 B).
- Per context slot it stores two residues' positions = 288 B = exactly what two
  shipped rows hold. No byte gain, plus the fixed cost → ceiling 133 positions
  ≈ 17K. The compute row's saving (27 KB code + 40 B/pos) is not on the bound.
- A thin storage row (KV role only: K/V cache + append + slab send + collective
  pass-through) is derived at a few KB fixed → ~300 positions ≈ 38K per pair.
  NOT compiled; the compile is the gate.

## Finding 3 — the latency penalty is "half the attention PEs", not "remote KV" (Le's framing, 2026-10-02, confirmed by the model)

- cycles/layer = 19,881 + 90.1 × L, L = positions scored per compute PE.
  Any 1-in-2 where the storage row does not score has L = 2C/256 regardless of
  WHERE the bytes live (local-first / remote-on-overflow changes nothing: the
  compute PE still scores both residues). Slope per context token is constant
  but 2× shipped (0.70 vs 0.35 cycles/layer/token); relative penalty
  (F+2cs)/(F+cs) grows 4 % (2K) → 34 % (28K) → 53 % (64K), limit 100 %.
  Per compute PE the scan duty cycle rises (33 % → 50 % at 28K); per block the
  attention utilisation falls (same work, longer layer).
- Same-context comparison at 28K (model, both extrapolated beyond measured
  L ≈ 63): shipped 29,972/layer (1,079K/token, 788 tok/s @0.85 GHz) vs thin
  pair 40,063/layer (1,442K, 589 tok/s), +34 %.
- The 90 cycles/position is not GEMV time (~32 MACs/position/PE): it is
  per-position P·V op launch, band all-reduce payload, exp. Halving c halves
  the penalty of every 1-in-k design and helps the shipped kernel equally
  (profile-gated P·V rewrite, separate demo).

## Conclusion — where storage PEs must come from

- Experiments pinned two facts: remote KV transport is free (0 vs shipped) and
  the role split is free (~100 cycles/layer). The whole penalty is the halved
  compute. A 512-row ATTN block (256 shipped compute rows + 256 interleaved
  thin storage rows) would, by the model, match shipped time within ~1 % with
  capacity set by the thin row (~79K derived; even today's thick row → 34K)
  and no hidden reshard (A/B row index y → 2y only).
- The cost is wafer area: shipped layout is 4 bands × [ATTN 256² | FFN 256²] =
  512 × 1024 on a 762 × 1172 fabric; 4 × 512 rows does not fit. Options are
  layout questions, not kernel questions: 2 bands × 18 layers (weights per PE
  double), spare area as storage bands (≈1/3 of the PEs, the band-farm
  geometry, streamed hops are 0/hop), or stay at 256² (= shipped).
- Decision (Le, 2026-10-02): first build the thin storage row inside the
  current pair tree (strip every buffer / weight / collective membership the
  storage row does not need), compile-gate its footprint, then take the layout
  question. [procedural: "spend PEs for storage, never halve the scorers" is a
  design rule worth a skill line if it recurs]

## Pointers

- Notes: `demo/micro-kv-farm/code/pair/IMPLEMENTATION-NOTES.md` §12–§13; model
  `analyses/2026-10-01-micro-kv-farm-sweep/`; earlier captures
  `2026-10-01-micro-kv-farm-positions-per-pe-model.md`,
  `2026-09-27-micro-kv-farm-1in2-rung1-and-dsd-cost-model.md`.
- ContextBase log: https://context.ed-aisys.com/doc/2026-09-27-log-micro-kv-farm-1-in-2-paired-attn-rows-rung-1-on-cs-3-dsd-cost-model-next-steps-I2chiMZyfg (§12).
