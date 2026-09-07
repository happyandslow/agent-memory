# Qwen3-4B decode floorplan: the gap between the role blocks is free, HT head is redundant, HT tail's PE count is fixed but its shape is not — 2026-09-07

**Project:** wse3-performance-model
**Author:** claude (session 4b-layout-kv-stream)
**Status:** captured

## Situation

You are trying to find room on the wafer for something new (KV storage, a
scoring farm, an extra stage) in the 4B decode placement, and the generator
audit reads as "geometry is locked": two role columns, one shared square
`P_BLOCK_SIZE`, fixed derived origins, no vertical/diagonal generator. The
128-column HT band on the west and the 113 unplaced columns on the east look
like the only free space, and they are not symmetric across the four rows.
Source-verified this session against the frozen worktree
`/home/lexu/worktrees/1.7b-pipeline-af@93a6d0e/models/qwen3_4b-decode`.

## Finding

- **What the serpentine actually constrains is that the two block columns keep
  the same fabric x in every row — not how far apart they are.** The
  row-crossing transport is a strip relay from FFN(r)'s *outer* strip straight
  down into ATTN(r+1) directly below (`launch.py:127-151, 998-1004,
  1084-1123`). Insert an arbitrary band *between* the two block columns and
  that relay, the A/B row multicasts, both role images and every shard
  parameter are untouched; only `PLACE_X`, the block-column-1 offset and the
  derived strip / `kv_inj` positions move. **The inter-block gap is the one
  large, per-row-identical piece of free area you can create.**
  (Keep the gap width odd: the ATTN east-edge ingress colour parity assertion
  `launch.py:1009-1020` needs both ATTN east edges at the same parity.)
- **HT head (128 × 256 = 32,768 PEs) is redundant work, not required
  hardware.** Qwen3-4B has `tie_word_embeddings`, and `launch.py:1953-1995`
  draws `lm_head_tile` from the *same* `(vocab, dim)` matrix as `W_E` — so HT
  tail already holds every embedding row. The head's only job is the
  vocab-on-Y / hidden-on-X diagonal transpose that hands ATTN r0 a Y-sharded X
  (`ht_head.csl:126-275`); the tail can gather the sampled token's row from its
  own tile (a 20-element strided read per PE, `lm_head_tile` is
  dim-outer/vocab-inner) and a one-column relay/transposer can do the same
  reshape. Cost is latency only (≈ +3K cycles/token ≈ 0.4 % of 785,769
  measured; analytical).
- **Its width cannot be changed instead:** `HT_WIDTH_head × 2 × dim_per_pe ==
  dim` (`launch.py:563`) pins it to `P/2 = 128`, and the diagonal pairing pins
  the height to `P`.
- **HT tail's per-PE bytes are set by its PE count, not its shape** —
  `lm_head_tile = V_per_pe_x × dim_per_pe × 2 B = vocab × dim / N_PE`, so
  32,768 PEs → 23.8 KB whatever the aspect ratio. The trap is the *other*
  buffer: `partials_buf = bsz × V_per_pe_x × 4 B`. Making the tail narrower
  (64 × 512) doubles it to 9.5 KB → 49.7 KB > 48 KB, **link failure**, unless
  the lm_head GEMV is chunked over vocab. Rotating the other way (256 × 128)
  keeps the tile, *halves* the partials to 2.4 KB and frees ≈ 2.4 KB —
  and 128 rows fits the 146-row unplaced south region. Checks that must hold:
  `vocab_pad % HT_WIDTH == 0` (152,064 % 256 ✓), `dim / height` integral
  (2560/128 = 20 ✓), `group_num | height` (16 | 128 ✓).
- Combined, those two free the whole 128-column west band, which is what makes
  a per-row-identical band possible at all: with the head gone and the tail
  moved south, every row gets the *same* free columns rather than rows 1/3
  facing 113 east columns, row 2 a 128-column west gap and row 0 the HT head.

## Implications / next actions

- [ ] All of the above is source-read + arithmetic, **not compiled**. The
  cheapest settling experiment is a compile-only `launch.py` variant with a
  routing-only stub in the gap plus the rotated tail; it also confirms the real
  usable fabric width (the 762 figure is inherited from the 2026-06-28 study).
- [ ] The head fold and tail rotation are verifiable **on their own**, before
  any new region has compute in it: the computation is unchanged, so the
  existing numpy oracle / top-k / re-arm bit-identity gates apply directly in
  simfab. Negative control: mis-pair the Z fold column's rows by one.

## Pointers

- `docs/design/2026-09-02-kv-farm-s4-layout.md` §2.1, §2.3, §4.2–4.4 (+ `.zh.md`);
  figures `docs/diagrams/2026-09-02-kv-farm-{s3-outer-edge,s4-wide-band}.png`
- `ht_head.csl:126-275`, `ht_tail.csl:1-11,99-113`, `launch.py:554-570,782-811,1781-1830,1953-1995`
- related inbox: `2026-09-01-qwen3-4b-placement-generator-boundary.md` (the
  generator boundary this refines — that capture is about what the generator
  cannot place; this is about what it can, without touching the serpentine)
- **staleness / status:** the S4 layout these facts were derived for is a
  *proposal under Le's review*, never accepted, never built; and it predates
  the thin-block / L = 4 device results (2026-09-04..06 captures) that changed
  the preferred stage geometry. The three structural facts above are properties
  of the source and survive that change; the S4 capacity numbers do not.
