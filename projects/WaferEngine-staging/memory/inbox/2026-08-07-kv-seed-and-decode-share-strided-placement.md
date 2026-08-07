# Host-seeded and decode-appended KV share ONE strided placement — no per-PE contiguous seed, so one P-aligned scalar resume is exact (only) at P-multiples

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are designing the resume / RoundPlan / meta contract for `qwen3_1p7b-decode`
and reach for this intuition: *KV is sharded by token position, decode appends
tokens round-robin across PE rows, but the initial host KV ingress must place
adjacent prompt tokens contiguously within each PE — so seed KV and
decode-produced KV live under two different maps, a single scalar resume
position cannot represent the physical valid prefix on every PE, and I will need
per-PE starts / a relayout to bridge the asymmetry.*

That is the exact hypothesis a read-only source audit set out to validate. Most
of it is **wrong on the central factual premise**, and the part that is right is
already an enforced constraint, not an accident. Getting this wrong sends you
building a relayout or per-PE asymmetry handling that the code does not need.

## What the audit found (read-only, line-cited)

- **There is no prefill/decode placement asymmetry.** Host seed and decode
  append use the **same** strided map. `shard_3d` (`layout.py:1723`) blocks the
  seq axis into contiguous *storage columns* per PE row, but the
  global-token → (row, local-index) identity is **strided, not contiguous**:
  `abs_pos = col_in_pe * P_BLOCK_SIZE + owning_px`
  (`host/oracle_fp16.py:559`, `:676`). Inverting: sequence position `t` →
  **row `t % P`, local col `t // P`**. A PE's adjacent local columns are
  `P_BLOCK_SIZE` apart in sequence position — round-robin, same as decode
  append. Ingress writes each PE's received tile into local cols `0..plen-1`
  contiguously (`decode.csl:1615-1662`); the *positions* those cols carry are
  strided.
- **K and V use the same placement**, so attention stays numerically correct:
  each PE scores only its own local `[0, iter_num)`, softmax is all-reduced
  along the column, and there is no positional axis in the read path — logical
  token order is **partitioned, never reconstructed**. Physical placement is a
  set, not a sequence.
- **The genuinely valid concern:** a single P-aligned scalar (`common_start` /
  `retained_len`, resume granularity `= P_BLOCK_SIZE`) can only represent a
  resume boundary that is a **multiple of P**. At a non-multiple, per-PE
  physical valid lengths differ **by at most 1** (rows `< input_len % P` hold
  one extra position). The code **forbids** that case rather than handling it:
  `prefill_len % P_BLOCK_SIZE == 0` (`layout.py:329`),
  `retained_len % P_BLOCK_SIZE == 0` (`layout.py:783`), decode-length
  divisibility / `n_steps ≡ 0 (mod P)`. This is the documented **D9**
  constraint, enforced by host asserts — not an accidental limitation.

## Implications / next actions

- [ ] Do **not** build a seed→decode relayout or per-PE start bridge for the
      current code — one P-aligned scalar is faithful because both halves share
      the strided map.
- [ ] Per-PE plan payload (per-PE start / next-write / extent) becomes necessary
      **only** if a future feature allows an **arbitrary (non-P-multiple)
      truncate-then-branch** — i.e. relaxing D9. That is where a "same logical
      index lands in a different physical cell per branch" hazard lives; today
      D9's `% P == 0` gate keeps it out of reach.

## Confidence / attribution

Read-only source audit, facts read off `decode.csl` / `layout.py` /
`host/oracle_fp16.py` in-session with the line cites above. No user
confirmation; the conclusions are source-grounded determinations, not
suggestions. Supersedes the earlier same-day framing (audit `45aae5fb`) that
read the host seed as contiguous-per-PE and decode as round-robin — two
different maps; that premise is the one this audit refutes.

## Pointers

- [[decode-lanes-must-be-equal-length]] — the `iter_num`-is-length-and-stride
  mechanism and the single-high-water-scalar revisit failure this sits beside.
- [[kv-cache-policy-tradeoffs]] — 2026-07-29 update: per-slot KV length stays on
  the host; the "active set changes across rounds AND a slot is revisited"
  trigger for a per-slot table.
- [[m1-kv-memory-layout-contiguous-vs-paging]] — K/V transpose + slot-base
  symmetry; this note adds the token→(row,col) strided identity it omits.
- Source: `host/oracle_fp16.py:559,676`; `layout.py:329,783,1723`;
  `decode.csl:1615-1662`.
