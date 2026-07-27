# When the numpy oracle stops being an independent reference: it can share the buggy formula, and it can share the RNG draw order

Date: 2026-07-27 · Repo: `WaferEngine-staging` · `models/qwen3_1p7b-decode` (M1-S1 review + M1-S2 planning)

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are about to gate a KV-reuse change on `numpy_oracle_*` — either as the red half of a
negative control ("run the red config on the old code, it must FAIL") or as the correctness gate
for a widened cache. The oracle agrees with the device, so you conclude the change is sound, or
that the seam is exercised.

Neither conclusion follows if the oracle is not independent of what you are testing. Two
distinct couplings were found in this codebase, and both are silent.

## Coupling 1 — the oracle contains a second copy of the formula under test

The per-slot high-water problem (see [[per-slot-kv-length-stays-on-host]] for the failure trace)
is a **single scalar** `kv_store.last_idx` standing in for a per-slot table. But that same
computation exists **three times**: `kv_store.last_idx`, `launch.py:2936` `_hw`, and
`oracle_fp16.py:633` `high_water`.

So the obvious negative control — run the red config on the old code and expect FAIL — gives
**device wrong, oracle wrong in exactly the same way, comparison agrees, PASS.** The oracle
reproduces the bug it was supposed to catch.

A control that actually discriminates has to break the shared copy: **new (per-slot) oracle vs
old device must FAIL**, plus **old-device round-2 logits ≠ new-device round-2 logits**.

Two further traps on the same control:

- **The bug is invisible unless rounds have unequal lengths.** Fresh rounds take
  `start_idx = pl_per_pe` and never read `last_idx`; only retain rounds do. With every round
  decoding the same length the scalar *coincidentally equals* the correct per-slot value and the
  old code passes honestly. `DECODE_LENS = [8, 16, 8]` forces the split (`pl_per_pe=1`,
  `dl_per_pe=1`): after round 1 slots [2,3] are at 3 while slots [0,1] are still at 2, so round 2
  resumes at 3, reads a column that was never written (zeros), and writes the new token one
  position late.
- On current HEAD the red config trips S1's `retain + remap` assertion first, so that guard has
  to be temporarily disabled for the control to reach the code being tested.

## Coupling 2 — the oracle shares the host's random draw order

`launch.py:1857` carries an in-repo comment saying it outright: *"RNG order MUST match oracle."*
Mock weights and mock K/V are drawn from `RandomState(2025 + global_l)` in a fixed sequence
(… WQ, WK, WV, q_norm, k_norm → **XK ×bsz, XV ×bsz** → UP/GATE at `:1883`, DOWN at `:1888`), and
`oracle_fp16.py:92-93` draws in the *same* order with the *same* seeds.

This is why the natural-looking edit — widening `for _ in range(bsz)` at `launch.py:1861/1867` to
`range(slot_count)` so the baked cache matches the new device width — **must not be made**. It
draws `2*(S−M)` extra values, shifting every subsequent weight. Device and oracle then run on
different FFN weights, and the symptom is *small numeric drift everywhere* — the hardest kind to
attribute — plus a failing byte-identity gate against the S6a baseline that looks like the seam's
fault.

Correct shape: keep the **draw count at `bsz`**, then zero-pad to `slot_count` and place by
`active_slot[b]`. The RNG stream is untouched; only the baked symbol layout changes. (A second,
independent reason the naive widening fails: the streaming payload is **M tiles** —
`_repack_kv_band` does `seg.reshape(bsz, kc, sq)` and the device expects
`tile_len = bsz*kv_cols*plen` — so an S-wide staging array changes the wire length and desyncs.)
Since no config currently takes the bake path, an assertion `kv_stream_ingress or slot_count == bsz`
is the cheap correct move rather than making bake multi-slot work.

## Related: the device-side checks also assume a static active set

`_kv_seed_check` and the KV-ISOLATION check both key off `last_active_slots_rnd`. Once the active
set varies per round that is wrong twice over: KV-SEED should pair with the last round that
**actually ingressed** (not the last round), and the idle set should be *slots never active in any
round*, not *slots not active in the last round* — otherwise a slot holding real KV from an earlier
round is reported as an isolation failure. An empty idle set must skip explicitly, not pass
vacuously. This is the same shape as the `plen == 0` vacuous PASS already recorded in
[[negative-control-configs-silently-degrade-to-pass]]; a red config with `SLOT_COUNT=5` leaves one
slot genuinely untouched so isolation has real signal.

## Confidence / attribution

All three-copy locations, the RNG ordering, and the check's use of `last_active_slots_rnd` were
**read off the code in-session** (and the RNG coupling is asserted by an existing in-repo comment).
The M1-S2 red-config design (`DECODE_LENS=[8,16,8]`, new-oracle-vs-old-device) was **proposed and
not yet run** `[unverified]`; S2 had not started when the session ended. Nothing here was
contradicted by Le.

**Promotion candidate (procedural).** Stated without naming this project: *before treating a
reference implementation as evidence, check what it shares with the thing under test — a duplicated
formula makes agreement meaningless, and a shared pseudo-random draw order makes any change in draw
count silently invalidate every downstream comparison.* This sits with the sibling lesson "prove a
red test can fail" from the same milestone.

## Pointers

- `kv_store.py`, `launch.py:1857/1861/1867/2936`, `host/oracle_fp16.py:92-93/633`.
- `milestones/M1-intra-pe-reuse.md` § S2, `milestones/kv-reuse-tradeoff-register.md` D4.
- Related: [[per-slot-kv-length-stays-on-host]] (the `last_idx` failure trace this control targets),
  [[negative-control-configs-silently-degrade-to-pass]],
  [[new-storage-axis-only-destinations-take-it]] (records the `slot_count == bsz` bake guard — this
  note is the reason behind it).
