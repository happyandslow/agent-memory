# Prefill KV bank is slot-indexed, not append-only: fanout children overwrite the suffix for free, and there is no "erase" step

Date: 2026-07-23 (session content from the S6a-prefill review round) · Repo: `WaferEngine-staging`

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are designing a shared-prefix **fanout** case (one resident prefix, N children each
appending their own suffix), or any multi-request prefill reuse, and two questions come
up that the code does not answer on its face:

1. Does the previous request's non-shared KV have to be **erased** before a child reuses
   the prefix, or will the child read stale K/V?
2. After request A (chunks `1,2,3,4`) and then request B (chunks `1,2,5,6`), what is
   resident — `1,2,5,6` or `1,2,3,4,5,6`?

Getting (2) backwards leads to designing an M1 test around KV that accumulates across
requests, which this kernel does not do.

## The answer: the bank is indexed by chunk *position*, so writes are in-place

`K_cache_bank` / `V_cache_bank` are `[layer][chunk]` — a **fixed slot per sequence
position**, not an append-only log. `cache_kv` writes chunk `c` into slot
`[layer][current_chunk]`. So:

- **Resident after A then B = `1,2,5,6`.** B's suffix occupies *the same slot indices*
  (2, 3) as A's suffix, so `3→5` and `4→6` are overwritten in place. `1,2,3,4,5,6` is not
  representable: that would need six chunks live in six distinct slots plus a per-request
  index table.
- **The shared prefix (slots `0..k-1`) is simply never written** by a child that starts
  at `current_chunk = k` — that *is* the reuse.
- **No explicit erase is needed.** The child's own `cache_kv` write *is* the erase, and
  it is free (it was going to happen anyway).
- **Residue past the child's length is harmless.** Attention sweeps `attn_pair` over
  `0..current_chunk` only, so a child shorter than its parent never reads the parent's
  leftover tail slots.
- **No stale read at a slot the child is taking over**, because within a chunk `cache_kv`
  precedes `p_attn_score`: each chunk's K/V is written before it is attended, so the
  overwrite is just-in-time per chunk.

## Why this is the S6a / M1 boundary

This is the mechanical reason S6a carries a reuse **length** (`start_chunk`, prefix chunk
count) but **no reuse index**. "Request 3 reuses request 1's KV while skipping request 2,
with request 2's KV also resident" requires several requests' KV addressable at once =
per-request bank partition/keying = the **T0.5 / M1** tier, not S6a. Fanout does not need
it: the shared prefix is persistent, each child's suffix is transient, and only one
child's suffix is on-chip at a time.

The same shape holds on the decode side with one slab: reuse-all ≡ reuse-previous
(the previous request's resident KV already contains everything before it), and
"keep only the last request, evict earlier" is *not* expressible without compaction
(data movement), which S6a's seam rules forbid — also M1.

## Confidence

Mechanism is **read off `prefill.csl` in-session** (`cache_kv` at `[layer][current_chunk]`;
`p_attn_score` / `attn_pair` sweeping `0..current_chunk` with causal mask only on the
diagonal chunk; the `cache_kv`-before-attention flag ordering) — not from a dedicated
experiment. It is consistent with, and indirectly backed by, the S6a-prefill warm-start
run that verified byte-identical output with a reused resident prefix
([[s6a-prefill-warm-start]]).

## Pointers

- [[kv-cache-policy-tradeoffs]] — T0.5 in-bank multi-request reuse (the tier that would
  make reuse-by-index possible, and what it costs).
- [[s6a-prefill-warm-start]] — the warm-start mechanism and its three bring-up defects.
- Plan § Out-of-scope: `docs/superpowers/plans/2026-07-13-m0-s6a-pe-internal-kv-reuse.md`.
