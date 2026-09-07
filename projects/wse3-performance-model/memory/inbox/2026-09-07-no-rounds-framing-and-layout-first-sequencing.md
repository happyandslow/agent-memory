# KV movement is designed for a continuous pipeline, not rounds; and layout is settled before the data path — 2026-09-07

**Project:** wse3-performance-model
**Author:** claude (session `4b-chunked-softmax`; decisions taken 2026-09-02, captured 09-07)
**Status:** captured

## Situation

You are designing how a request's K/V gets to (or is scored at) the PEs that
need it, and you are about to reason in terms of round boundaries — park at end
of round, reload at start of next — or you are wondering why the chunked-score
work and the layout work are two separate sessions with an ordering between
them.

## Finding — Le's framing decisions (authoritative)

- **No rounds.** The target execution model is a **continuous request pipeline
  between stages**; ideally new KV flows into the decoder whenever it can be
  scheduled. Round-based park/reload is therefore **not a design target for the
  kernel data path**. Movement is a steady-state path whose cost is fabric
  occupancy concurrent with compute, not a round-boundary burst.
  - This is a *different axis* from the keep-vs-park **policy** question
    (host / far-pool eviction, gap vs reload time), which remains open and is
    unaffected — see `2026-09-03-gc-curve-v2-idle-gaps-and-keep-vs-park.md`.
  - Consequence: the P1 (per-turn) price class still exists for eviction
    policy, but it is not the frame for designing where KV lives on chip.
- **Layout before data path.** The movement/offload path is expensive to build,
  so the layout is decided first — a wrong layout wastes that work. This is why
  `4b-layout-kv-stream` was split off from the chunked-score session, and why
  the chunked-score work was narrowed to the part with no layout dependency
  (online-softmax scoring on the ATTN PE, which is PE-local).
- **Balance requirement for any layout**: equal fetch overhead in every stage —
  same topology, link count, shared traffic and capacity per row — because in a
  pipeline the binding quantity is the **max over rows**, never a wafer
  average. Compute overhead must stay "not outrageous" versus the shipped
  role-split placement.

## Minor source constraint worth not re-deriving

Splitting the existing ATTN block into alternating compute/storage **columns**
is forced to **1:1**: `launch.py:435` asserts `kv_cols % 2 == 0` and
`attn_per_pe == gqa_group_size * kv_cols`, and a KV-head band is 32 columns, so
with `c` computing columns `kv_cols = 128/c` must be an even integer. 16:16 is
the only legal ratio (8:24 needs 31 KB of weights per compute PE and does not
fit). This constrains *splitting the block*; it does not constrain a separate
scoring-storage region, whose advantage is precisely shape freedom.

## Superseded within the same day — read these instead

The session briefed above went further on 09-07; do not act on the earlier
framing:

- **The perimeter/bisection bound does not condemn off-block pools.** It blocks
  streaming K/V *into* the block; a pool that can *compute* sends only
  online-softmax partials (`m, l, O`), independent of positions stored. Do not
  mark far-pool cards `mechanism: none` on the bound alone —
  `2026-09-07-score-at-the-storage-pe-not-stream-kv.md`.
- **The per-row free-SRAM asymmetry is solvable, and the serpentine is looser
  than it looks**: what it constrains is that the two block columns keep the
  same fabric x in every row, not how far apart they are — so a per-row-
  identical band can be inserted *between* them; folding the redundant HT head
  and rotating HT tail south makes every row's free area identical —
  `2026-09-07-4b-floorplan-degrees-of-freedom-ht-head-tail.md`.
- **Chunked/online softmax is not X-collective-neutral**: it makes the 32-PE
  score band all-reduce per-chunk (`decode.csl:1348`). Already measured and
  stronger: *chunking the scan helps only to k = 2, its fixed collectives bind
  after that* — `2026-09-05-4b-phase-profile-softmax-dominates-stage-cut.md`.

## Pointers

- `docs/design/2026-09-02-kv-storage-layout-stage-balance.md` (the brief this
  session wrote and handed to `4b-layout-kv-stream`; its §3.1 bound is the
  version corrected above)
- `docs/design/2026-09-02-kv-farm-s4-layout.md` (the design that superseded it —
  proposal under Le's review, never accepted, never built)
- `docs/session-prompts/2026-09-02-single-request-remote-kv-and-chunked-score.md`
- Related: `2026-09-03-session-4b-wide-layer-conclusions.md` (open item
  "layout/stage-balance"), `2026-09-02-score-buffer-wall-and-single-request-remote-kv.md`
