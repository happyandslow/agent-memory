# Per-slot KV length stays on the host: the device keeps one scalar, and the trigger that finally forces a table is "active set changes AND you come back"

Date: 2026-07-26 · Repo: `WaferEngine-staging` · `models/qwen3_1p7b-decode` (M1-S1 review)

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are giving decode a slot dimension (M1-S1) and working down a change list. The obvious
next item reads *"`iter_num_bank` / `step_bank` are `[max_layers_per_block]` — give them a
slot axis, `[layer][slot]`, and fan the write-back out to every active slot."* It looks
mandatory: idle slots must "remember" how full they are, or their KV is useless when they
come back.

**Do not do it in S1.** Le questioned this item and the questioning is right; the earlier
change-list entry was wrong.

## Why the device does not need per-slot counters

Separate the two things a slot holds:

- **KV bytes** — safe with no help at all. Writes only ever target *active* slots, so an idle
  slot's cache region is simply never touched. Nothing can lose it.
- **Length** — the only per-slot state at risk. And under **D4 the control plane already
  lives on the host**: `kv_store` holds each slot's `valid_len`, and on reactivation the value
  comes back down through the meta tile's `retained_len` and overwrites the scalar in
  `round_reset`. This is not new machinery — it is precisely what S6a does today
  (`launch.py:2549` maintains the high-water mark → meta slot 2 → `decode.csl:308`).

Combined with the same-sequence-position invariant, one forward needs exactly **one** start
value. A per-slot bank would therefore be a **device-side copy of state the host already
owns** — a second source of truth and a drift source, for nothing.

**Three S1 items are cancelled by this:** the bank slot axis; the write-back fan-out at
`decode.csl:1501-1502` (stays a single scalar write); and the per-slot loop in `round_reset`.
The slot axis applies only to KV **bytes** and **write addresses** — the cache declarations,
the addressing seam, `process_kv`, ingress, and the two matmul base addresses. Counters are
not part of the slot dimension.

**Two in-repo contract lines must be corrected**, or the next person re-derives the wrong
answer straight from the doc: `M1-intra-pe-reuse.md § S0.2` says *"slot empty ⇔
`iter_num_bank[layer][slot] == 0`"* — occupancy is a **host** judgement now; and the grep
checklist's first row lists S1 as the fix owner for adding that dimension — it should read
"not needed, superseded".

## The trigger that does force a per-slot table (and it is not on the device)

The same reasoning exposes where the host's own state breaks. `kv_store` tracks a **single**
high-water scalar, `last_idx`, used by the `RETAINED_LENS = -1` sentinel. That is correct only
while the active set is constant across rounds. Concretely:

| round | active slots | event | `last_idx` |
|---|---|---|---|
| 0 | 0,1 | fresh, decode to 3 | 3 ✓ |
| 1 | 2,3 | fresh, decode to 6 | 6 — **clobbers the 3** |
| 2 | 0,1 | retain, `-1` sentinel, should resume at 3 | sends **6** ✗ |

Round 2 then appends from position 6 while positions 3–5 were never written, and attention
reads all of `[0,6)` as valid. **Silent wrong values, no crash.**

> **The table is required exactly when the active set changes across rounds *and* you later
> return to a previously-used slot.** Not before.

S1 satisfies neither (its map is static in both the inert and red configs), so **S1 does not
touch `kv_store.py`** — another change-list item that comes off. S2 is where the per-slot
`valid_len` table lands, and it retires the `-1` sentinel in favour of an explicit
`retained_len` computed on the host.

The knock-on is that **S2's shape flips**: the bulk of it becomes host work (a slot table plus
an explicit per-round `retained_len`), with the device barely changing — not the "device loops
over slots" design the milestone currently implies.

## When the device-side per-slot counter comes back

Only two ways: **ragged / continuous batching (O1)**, where active lanes genuinely differ in
length so one scalar cannot hold it — note that is per-**lane**, not per-**slot** — or moving
the control plane onto the PE so the host stops shadowing device state (O3 / M2).

Related cleanup noticed in passing: the `RETAIN_ROUNDS` config key is fully derivable from
`PREFILL_LENS[rnd] == 0`, which is already how the device decides; it is redundant and
drift-prone.

## Confidence / attribution

The retraction is **Le's correction, conceded by Claude** — authoritative. The mechanism
(D4 host control plane, `retained_len` → `round_reset`, idle-slot bytes untouched) is
code-verified against `decode.csl` / `launch.py` in-session. The `last_idx` failure trace is
**derived from the code, not observed** — it has not been run `[unverified]`, and the
doc/milestone edits it implies have not been made.

## Pointers

- [[slot-reuses-bsz-batch-is-not-a-storage-axis]] — slot(S) vs batch(M); this note says the
  split stops at bytes and addresses, not counters.
- [[mixed-hit-miss-batch-needs-no-ragged]] — the same-position invariant that makes one scalar
  sufficient, plus what O1 really costs.
- [[m1-kv-memory-layout-contiguous-vs-paging]] — the contiguous-slot layout and addressing seam.
- [[s6a-decode-kv-retain]] — the existing high-water → `retained_len` → `round_reset` path this
  reuses.
