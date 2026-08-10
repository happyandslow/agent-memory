---
summary: Decode host-seeded KV and decode-appended KV use the same strided token placement; a single scalar resume is exact only at P-aligned boundaries, with arbitrary truncate/branch needing per-PE plan payloads.
tags: [waferengine-staging, m1, decode, kv-layout, resume, d9]
---

# Decode KV strided placement and resume granularity — 2026-08-07

Created by the 2026-08-10 maintain pass from `memory/inbox/2026-08-07-kv-seed-and-decode-share-strided-placement.md`.

## Finding

A read-only source audit refuted the intuition that host-seeded KV is contiguous-per-PE while decode-appended KV is round-robin. Both use the same strided map:

- `shard_3d` blocks the sequence axis into contiguous storage columns per PE row, but the global-token identity is `abs_pos = col_in_pe * P_BLOCK_SIZE + owning_px`.
- Inverting that map: sequence token `t` lives on row `t % P`, local column `t // P`.
- Ingress writes each PE's received tile into local columns `0..plen-1`; those local columns represent strided global positions.
- K and V use the same placement, so attention stays numerically correct without reconstructing global token order: each PE scores its local `[0, iter_num)`, and softmax is all-reduced along the column.

## Consequence

For the current code, do **not** build a seed→decode relayout or per-PE start bridge. A single P-aligned scalar (`common_start` / `retained_len`) is faithful because host seed and decode append share the same physical map.

The real limitation is granularity: a single scalar can exactly represent a resume boundary only when it is a multiple of `P_BLOCK_SIZE`. At a non-multiple, row valid lengths differ by at most one. The code forbids that case via the D9 constraints (`prefill_len % P_BLOCK_SIZE == 0`, `retained_len % P_BLOCK_SIZE == 0`, decode length divisible by `P`).

## Next implication

Per-PE plan payloads — per-PE start, next-write, or extent — become necessary only if a future feature relaxes D9 and allows arbitrary non-P-multiple truncate-then-branch. That is where the same logical index can land in different physical cells per branch.

## Pointers

- Source audit pointers from capture: `host/oracle_fp16.py:559,676`; `layout.py:329,783,1723`; `decode.csl:1615-1662`.
- Related: `memory/topics/kv-cache-policy-tradeoffs.md` (per-slot KV length stays on host), `memory/topics/m1-s1-multi-slot-kv-seam.md`.
