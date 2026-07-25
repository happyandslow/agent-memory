# Per-PE KV memory layout for multi-request coexistence (M1): contiguous slots beat paging, but keep an addressing seam

Date: 2026-07-25 · Repo: `WaferEngine-staging`

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are adding **multi-request KV coexistence** to the standalone decode kernel
(`models/qwen3_1p7b-decode`, milestone M1 T0.5): several requests' KV caches must live
resident in each PE's SRAM at once, each addressed independently. The design fork is
**how each request's KV is laid out in the per-PE KV bank**, and whether to build
paging now or keep it merely *possible*:

- **A — contiguous fixed-size slots (no page table).** Each request → one contiguous
  region; attention reads it as the *existing* fixed-stride DSD, base-shifted.
- **B — non-contiguous paged (page table).** Small fixed pages + per-request page table;
  attention becomes a gather over scattered pages.

## Decision: ship A, do NOT build B; realise A on the existing `bsz` lane axis

**Contiguous fixed-size slots (A)** is the M1 choice. Realise the slot index on the
**existing `bsz` lane axis** (call it option (i)): a *slot* = one `bsz`-lane index
`s ∈ [0, SLOT_COUNT)`, `SLOT_COUNT` = old `bsz`. Under (i) the slot index is literally the
lane `b` in the existing base arithmetic `(l·bsz + b)·kv_cols·kv_len_per_pe`
(`decode.csl:564`, computed at `:605-606,1164,1177,1215,1337,1615`) — **no extra
`+s·SLOT_LEN` offset term** (that term is only for the alternative (ii): carving the seq
axis into sub-ranges). Slot definition (load-bearing, easy to get wrong): a slot spans
**all layers this PE hosts** for one request (one lane threaded through every layer),
NOT one layer; `iter_num_bank[l][s]` gains a slot dim but holds the same value for all `l`
at a given `s` (a request's length is layer-invariant).

## Why A wins — the code-grounded reason

The decisive fact: the KV bank *already* has a per-request-independent **storage** axis
(`bsz`, `decode.csl:565` "per-(b,l) cache state is independent"); what it lacks is
per-request **control** (`iter_num` is one scalar per layer, shared lockstep) — and
per-request length is a prerequisite for BOTH A and B, so it is not a differentiator.

Attention reads KV as **one long contiguous fixed-stride DSD** over `[0, iter_num)`:
QKᵀ `score_matvec_mult` (`decode.csl:1211-1225`, length `iter_num` at `:1216`, row base
advancing by `kv_len_per_pe` via `@increment_dsd_offset` at `:1224`); score·V
`output_matvec_mult` (`:1330-1346`). A contiguous slot is a sub-range of that same axis
⇒ **the DSD descriptor is byte-identical except for the base address** — no extra DSR
loads, no added per-step addressing. B replaces the single long SAXPY with a **loop of
`n_pages` short SAXPYs**, each with its own `@load_to_dsr` reload + a page-table lookup.

**Projected overhead of B [mechanism code-grounded; cycle figure unverified/ASSUMPTION]:**
the per-SAXPY fixed setup/dispatch cost is amortised over `iter_num` today vs over
`PAGE_LEN` under paging ⇒ overhead multiplier `≈ iter_num / PAGE_LEN = n_pages`
(e.g. **~16×** the per-slot dispatch overhead at `iter_num=256, PAGE_LEN=16`). FMA count
unchanged; only overhead grows. This is the single biggest perf risk found, and it lands
in the kernel's hottest loop.

## The seam: keep paging *possible* cheaply, isolate its real cost

A→B is two separable changes:
1. **Addressing** (logical pos → physical base) — open-coded at 5 sites (`set_layer:605-606`,
   `process_kv:1164/1177`, `score_matvec_mult:1215`, `output_matvec_mult:1337`,
   `kv_ingress_layer_phase:1615/1628`). **Cheaply seam-able:** route all of them through one
   accessor pair `kv_k_base(l,slot,pos)` / `kv_v_base(...)`. Near-free in A (returns a
   pointer; inner SAXPY unchanged).
2. **Loop structure** (single contiguous run → per-page loop) inside the 3 hot primitives —
   **cannot be pre-paid** without taxing the hot loop (even a trip-count-1 wrapper loop
   perturbs the `save_address` DSR idiom).

So a seam localises the *addressing* half; the *hot-loop restructure* is inherent to B and
is where the cost/risk lives. **Recommendation: A now, behind the addressing seam; isolate —
do not adopt — paging.** Given the project's `R*` stance (WSE decode ≈ prefill favours
force-decode-in-place over ship/reload), B's one real win — copy-free cross-request prefix
sharing — may never be on the critical path, so paying its hot-loop tax now is premature.

## Prefix reuse: take-over-in-place is free; cross-slot needs a copy

- **take-over-in-place** (new request keeps the *same* slot as the prefix it extends): free.
  Mechanics = `round_reset` retain on that slot: `iter_num_bank[l][s] = L_match`
  (block-granular truncate), keep bytes `[0,L_match)`, overwrite `[L_match:]` with the
  suffix; other slots untouched; then force-decode the divergent suffix (S6b) + free-decode.
  Zero data movement. Safe **only when the matched slot is evictable** (its prior request
  done) — take-over destroys that request's tail past `L_match`.
- **cross-slot reuse** (prefix in slot A, new request assigned slot B, e.g. to preserve A for
  fanout): on-chip SRAM→SRAM copy `len·kv_cols·2(K+V)·2B` per PE — not free. Copy-free
  cross-slot sharing is exactly what paging (B) would buy.

## Confidence

Layout/DSD facts read off `decode.csl` in-session (line cites above); the A-vs-B code-site
enumeration + perf projection are in the milestone doc
`milestones/M1-slot-memory-layout-tradeoff.md`. Cycle-level perf figures are projected from
the mechanism, **not measured** — labelled ASSUMPTION in the doc. Decision (A + seam + option
(i)) confirmed by Le in-session 2026-07-25.

## Pointers

- [[kv-cache-policy-tradeoffs]] — T0.5 in-bank multi-request reuse tier and its costs.
- [[prefill-kv-bank-slot-overwrite-semantics]] — the sibling "slot-indexed, in-place
  overwrite, no erase" fact on the prefill side; same in-place-reuse shape.
- [[s6a-decode-kv-retain]] — the single-region retain (`round_reset` gate) that multi-slot
  `round_reset` generalises.
- Milestone: `milestones/M1-intra-pe-reuse.md` (M1-S0 slot-addressing contract) +
  `milestones/M1-slot-memory-layout-tradeoff.md` (this investigation).
