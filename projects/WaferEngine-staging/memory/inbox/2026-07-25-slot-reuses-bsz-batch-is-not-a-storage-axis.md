# Reusing decode's `bsz` axis for multi-request slots does NOT force re-adding a batch dimension later — batch is a scheduling subset, not a storage axis

Date: 2026-07-25 · Repo: `WaferEngine-staging`

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are adding multi-request KV coexistence to the decode kernel (`qwen3_1p7b-decode`,
M1 T0.5) and deciding how to get the "N resident requests" axis. The tempting objection:
"the kernel already has `bsz`, but if I *reuse* `bsz` as the slot axis I destroy its
batch meaning, and since we'll want batched serving again later I'll have to re-add a
batch dimension — so better open a NEW axis adjacent to `bsz` (`[layer][slot][bsz]`) now,
leaving the layout untouched at `SLOT_COUNT=1`." This sounds prudent and future-proof.

It is the wrong call, and the reason is worth remembering because it recurs whenever you
weigh "reuse a dimension vs add a parallel one" for KV storage.

## The answer: reuse `bsz` (make it the slot axis); do NOT add a parallel `[slot][bsz]` axis

Key realization: **`bsz` is already storage, and "batch" in modern LLM serving is not a
storage axis at all — it is a per-iteration active-subset over the resident requests.**

1. **What `bsz` is today** (`decode.csl:561-566`): `[layer][bsz][kv_cols][kv_len_per_pe]`
   = B *independent per-request KV slabs* ("per-(b,l) cache state is independent",
   `:565`), decoded in lockstep. So `bsz` is *already* B resident per-request containers +
   a lockstep constraint (all active, same length). It is storage, not a compute-only batch.
2. **What M1 does:** relax the lockstep constraint → per-slab independent length + active/idle.
   `bsz` lanes become slots. No storage added or removed.
3. **What batched / continuous serving needs later:** decode an *active subset* (M) of the S
   resident slots each step, membership dynamic. vLLM-style "batch size" = number of active
   requests *this iteration* = a **scheduling / mask** concept, NOT a storage axis. The KV
   cache is a pool of slots; the batch is whichever slots are active. There is no `S×B` storage.
4. **Therefore** reusing `bsz` is not a take-back: the same axis is both the resident-request
   storage and the pool the active batch is drawn from. Opening `[layer][slot][bsz]` would
   allocate `S×B` slabs = storing each request up to B times = wasted, because batch is not
   per-request replication.
5. **The one real case for a second width:** a fixed hardware/ALU batch width W always
   materialized (pad to W even if fewer active) — a compute-tiling/padding detail (mask the
   pad in the GEMV), NOT a KV storage axis.
6. **The actual work is identical either way and none of it is "re-adding `bsz`":** (a) per-slot
   `iter_num` (break lockstep); (b) compute only active slots — today the attention GEMVs loop
   `for b in bsz` (`decode.csl:1330`), so idle slots would waste per-token compute unless the
   loop iterates the active set; (c) dynamic membership + mid-flight injection (continuous
   batching, later). These are the slot mechanism itself.

## Why this generalizes

The trap is modeling *batch* as a storage dimension. In KV-cache serving, storage = slots
(one per resident request); batch = the active subset chosen each step. Conflating them makes
you over-allocate (`S×B`) or think you've "lost" batching by relaxing lockstep. Whenever you
face "reuse an existing per-request dimension vs add a parallel one," ask whether the second
concept is *storage* or *scheduling* — if scheduling (batch, active set), it is a subset/mask
over the existing storage axis, not a new axis.

## Confidence

Layout facts read off `decode.csl` in-session (`:561-566`, `:565`, `:1330`); the serving model
(batch = active subset over slots) is standard vLLM-style continuous batching. Decision (reuse
`bsz`, option i) confirmed with Le in-session 2026-07-25.

## Pointers

- Register: `milestones/kv-reuse-tradeoff-register.md` (decision D2 + Appendix A; mirrored to
  ContextBase → MeshAgent → Milestones).
- [[kv-cache-policy-tradeoffs]] — the T0.5 tier this slot mechanism realises.
- Related same-session capture: `2026-07-25-m1-kv-memory-layout-contiguous-vs-paging.md`
  (contiguous slots vs paging; the layout axis, orthogonal to this storage-vs-scheduling point).
- Continuous batching (concurrent active + mid-flight inject/evict) is a later milestone needing
  ingress/egress rework — register O1 + GOALS §7.

## Update (2026-07-25) — the precise split, and locked vocabulary

Refined with Le: "reuse `bsz` as slots" was imprecise (it implied the cache dim and the compute
dim stay merged, i.e. `S = M`). The correct split keeps them as **two different-sized axes linked
by an index** — this is the vLLM block/slot-table shape:

- **slot** (`S = SLOT_COUNT`) = **maximum request capacity**. Sizes the KV cache + `iter_num_bank`/
  `step_bank` → `[layer][slot][…]`, size ∝ **S** (NOT `S×M`).
- **batch** (`M`) = **active requests in one local forward**. Sizes compute/IO (`X`/`QKV`/`score`/
  `output`/sampling/`N`-header) + the `score_matmul` loop.
- **`S ≥ M`**, linked by **`active_slot[m] → s`**: batch lane `m` reads slot `active_slot[m]` via the
  addressing seam `kv_k_base(l, slot, pos)`.
- Least-churn naming: keep `bsz` for **batch (M)** (most of its uses are compute/IO); rename only the
  cache + counter sizing to **`SLOT_COUNT` (S)**; add `active_slot[]`.
- Inert seam unchanged: `SLOT_COUNT = bsz`, `M = bsz`, `active_slot[m] = m` → byte-identical.

So the "batch is not a storage axis" lesson stands and sharpens: the cache axis is **slot (S)**;
**batch (M)** is an *index into* it, not a nested `[slot][batch]` storage dimension (that would
over-allocate `S×M`). Full decision register: `milestones/kv-reuse-tradeoff-register.md` (D2 +
Appendix A) + the M1-S0 contract in `milestones/M1-intra-pe-reuse.md`.
