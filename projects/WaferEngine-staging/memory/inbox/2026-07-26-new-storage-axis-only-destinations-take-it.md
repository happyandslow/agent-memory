# Adding a per-request storage axis: only **destination** addresses take it, and two addressing forms will drift — three of four bugs were the same mistake

Date: 2026-07-26 · Repo: `WaferEngine-staging` · `models/qwen3_1p7b-decode` (M1-S1 implementation + verification)

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are widening a per-PE buffer with a new per-request axis (here: the KV cache gains a
`slot_count` dimension so several requests can be resident at once). You work down the list
of sites that index "by request" and update each one. It compiles. It runs. The numbers are
wrong, or subtly wrong, or wrong only in one layer — and **nothing errors, nothing traps, no
out-of-bounds fires**, because the old index and the new index are both `i16` in the same
small range. The compiler cannot tell them apart, and neither can a quick read of the diff.

Four such bugs were caught by review in one M1-S1 session. **Three were literally the same
mistake.**

## Rule 1 — destination = slot, source = lane

Every site that touches KV has *two* addresses: where the data comes from (a compute or
payload buffer, sized by the **batch lane** count) and where it goes (the cache, now sized by
**slot**). Only the second one takes the new axis. The three repeats:

| site | what got slot-indexed by mistake | what actually happens |
|---|---|---|
| `process_kv` K source | `QKV_tile[bsz*attn_per_pe + slot*kv_cols]` | `QKV_tile` is packed `[Q \| K \| V]` **by lane**. With `slot >= bsz` the read runs off the K region **into the V region** — V values get written into the K cache. In range, no trap. |
| `process_kv` V source | `QKV_tile[bsz*(attn_per_pe+kv_cols) + slot*kv_cols]` | same shape of error |
| `kv_ingress_layer_phase` source | `kv_ingress_buf[slot*…]` | that buffer holds **this round's payload = M lane tiles**, not S slots; slot-indexing reads another lane's tile or past the live region |

The rule is one line and belongs in a comment at each site, because the types will not say
it: **the new axis applies to storage and write addresses only — sources keep the old axis.**

## Rule 2 — one addressing form, or the copies drift (this is what the "seam" is for)

The layout was implemented behind a seam, exactly so a future change (paging) touches one
place:

```
k_cache_offset(layer, slot, pos) = (layer * slot_count + slot) * kv_cols * kv_len_per_pe + pos
v_cache_offset(layer, slot, pos) = (layer * slot_count + slot) * kv_len_per_pe * kv_cols + pos * kv_cols
```

For one revision the hot sites used the seam while the KV-ingress copy kept an inlined
formula — and the inlined copy was left at the **old** layer stride `l * bsz` after the cache
had already been resized to `slot_count`, so every layer overlapped the next. **The bug the
seam exists to prevent appeared because the seam was only half-adopted.** Two equivalent
copies are not a style problem; they are a scheduled defect.

Sub-rule that decides the seam's *shape*: make `layer` a **parameter**, not a read of a
"current layer" global. The ingress path runs before `set_layer()` and has its own layer
loop, so a seam that reads the global is unusable there — which is precisely what forced the
second, drifting copy to exist. Cost accepted: `set_layer()` loses its "repoint every pointer
to layer l" symmetry for KV alone (worth a comment, since it reads as an oversight).

Fourth bug, same family: `set_layer()`'s KV pointer repointing was commented out while the
use sites still read those pointers — so they kept their declaration-time value and **every
layer addressed layer 0**. Half-migrations are the recurring shape here, not typos.

## What this session verified (closes out three earlier `[unverified]` captures)

The seam landed and both gates passed, so several things previously marked speculative are
now measured:

- **Inert gate:** `slot_count = bsz`, identity map, vs a `git worktree` of the pre-change
  HEAD, same config → **bit-identical over 48 `[LOGITDUMP]` records / 192 fp32 logits**, plus
  identical verdict fields. Method: extract every simprint fp32 record from both `sim.log`s
  and compare **element-exact** — not "within tolerance".
- **Slot-shift invariance:** `SLOT_COUNT=4, ACTIVE_SLOTS=[3,0]` → bit-identical to the inert
  run, `KV-SEED PASS slots=[3,0]` (device read-back matched the host payload byte-exactly at
  the *mapped* slots), and a new `KV-ISOLATION PASS` (the unmapped slots are still exactly
  zero after four rounds). This confirms [[negative-control-configs-silently-degrade-to-pass]]'s
  prescription that the red map must be non-contiguous **and** out of order.
- **The vacuous `KV-SEED` check is confirmed empirically, not just by reading:** on the same
  config the pre-change baseline prints `prefill_len_per_pe=0` and the fixed version prints
  `prefill_len_per_pe=1`. The fixes proposed there (`last_ingress_plen`, skip-instead-of-PASS,
  idle-slot-zero check) are now implemented and exercised.
- **[[per-slot-kv-length-stays-on-host]] holds in practice:** the device kept per-layer scalar
  counters, `kv_store.py` was left untouched, and both gates still passed.
- Still `[unverified]`: the `min(L_match)` batch rule from
  [[mixed-hit-miss-batch-needs-no-ragged]] — no code, no run; it is S3's job.

## Guards that were added instead of doc lines

The constraints reasoned out during review were written as assertions, not prose: i16
overflow of the addressing seam; the meta-block fabric extent; `ACTIVE_SLOTS`
length/range/**duplicate** (a duplicate = two lanes on one slot = silent contamination);
**retain-round + remapped active set rejected** (it would resume an empty slot); bake path
requires `slot_count == bsz`. The unknown-config-key assertion from
[[negative-control-configs-silently-degrade-to-pass]] was **not** added — still open.

## Confidence / attribution

All four bugs were found by review and fixed before any run; the two gates were **run and
measured** in sim this session (2×2/7-layer, ≤16×16 PE). The rules above are generalised from
those four instances, all in one kernel — the *pattern* is verified, its breadth is not.

**Promotion candidate (procedural, would recur).** Stated without naming this project:
*"when you add a dimension to a buffer, only destination addresses take it; and if two
copies of the addressing math exist, they will drift — the second copy is where the bug will
be."* The same session already produced a sibling procedural lesson (prove a red test can
fail); both are about changes that are silent by construction.

## Pointers

- [[negative-control-configs-silently-degrade-to-pass]] — the red-config/vacuous-check half
  of the same review; its proposed fixes are now implemented and exercised.
- [[per-slot-kv-length-stays-on-host]] — why counters did *not* take the new axis.
- [[mixed-hit-miss-batch-needs-no-ragged]] — the same-position invariant behind that.
- [[s6a-decode-kv-retain]] — the retain path this seam sits on; its lesson "a new per-request
  dimension lands on sites that hardcoded the old default" is the ancestor of Rule 1.
- `milestones/M1-intra-pe-reuse.md` Verification log (in-repo, authoritative for state).
