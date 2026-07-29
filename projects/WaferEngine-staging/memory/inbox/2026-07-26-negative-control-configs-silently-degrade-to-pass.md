# A "red" config that reports PASS: unknown JSON keys are silently dropped, and the KV-seed check has been comparing empty arrays since S6a

Date: 2026-07-26 · Repo: `WaferEngine-staging` · `models/qwen3_1p7b-decode` (M1-S1 review)

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained

## The situation this applies to

You add a negative-control ("red") sim config that is supposed to fail until the feature is
implemented — a slot map, a forced-decode schedule, anything driven by a new key in
`model_config/*.json`. You run it. **It prints PASS.** You conclude the seam works.

It did not. Three separate instances of this showed up in one M1-S1 review session, all with
the same shape: the test quietly degraded into the *positive* control and then truthfully
reported that the positive control passed.

## Failure mode 1 — `launch.py` silently ignores unknown config keys

`cfg.get(...)` with a default means a misspelled key is not an error; it is the default. The
config and the reader then disagree in silence:

| config file says | `launch.py` reads | effect |
|---|---|---|
| `FORCED_DECODE_LEN` (singular) in `test_sim_2x2block_kv_retain_chain.json` | `FORCED_DECODE_LENS` (`launch.py:2500`) | its `[1,4,4,4]` **never once took effect** — that config has always run the default `[1,1,1,1]`. Five sibling configs spell it plural and are fine. |
| `ACTIVE_SLOT` (singular) in the new non-contiguous red config | `ACTIVE_SLOTS` | the `[3,0]` map is dropped, the run falls back to the identity map, and the red config **becomes a second copy of the inert baseline** |

Also worth knowing: a broadcast/length rule has to be decided at the same time. A single
map `[3, 0]` sliced per round as `active_slots[rnd*bsz:(rnd+1)*bsz]` yields `[3,0]` for round
0 and **`[]`** for rounds 1–3 → the meta tile shrinks by two i16 → the KV band size assert
trips on round 1. That one at least fails loudly.

**Mitigation (proposed, not yet applied `[unverified]`):** assert on unknown keys, or at
minimum explicitly read every new key and validate it (length == `bsz`, each value <
`SLOT_COUNT`, **no duplicates** — a duplicate means two lanes share a slot, which is silent
cross-contamination).

## Failure mode 2 — the device-side check compares two empty arrays

`_kv_seed_check` (`launch.py:2627`) is the strongest evidence available for slot addressing:
it reads `XKCache_tile` / `XVCache_tile` back off the PEs and compares against the host KV.
It is called with `last_plen_per_pe` — the **last round's** prefill length. Every retain
config has `PREFILL_LENS = [8, 0, 0, 0]`, so the last round's plen is **0**, every slice
`[..., :plen]` is empty, `np.array_equal(empty, empty)` is True, `bad` stays 0, and it prints
**PASS having compared zero bytes**.

This has been vacuous since S6a introduced retain rounds (plen=0 meta-only heartbeats) — the
check's original premise, that every round ingresses KV, quietly stopped holding.

Fix shape: track the plen of the **last round that actually ingressed** and pass that; round
0's prefix is still a valid oracle because decode only appends at positions `>= plen`, so
`[0:plen)` is never rewritten. And make `plen == 0` print *skipped*, never PASS — otherwise
this exact failure grows back.

## The generalisable rule

**A negative control has to be shown to fail before its PASS means anything.** Two things
were doing the opposite here: an unknown key defaulting back to the baseline, and a
comparison whose empty-input case is indistinguishable from success. Both report the same
word as a real pass.

Corollary for the slot work specifically: an identity slot map (`active_slot[m] = m`) cannot
tell a correct seam from one that just uses `m` directly. The red config must be **both
non-contiguous and out of order** — `SLOT_COUNT=4, ACTIVE_SLOTS=[3,0]` kills "slots are
contiguous", "slots are ascending", and "`m` is the slot" in one shot — and its output must
be **byte-identical** to the inert run, since changing slots only changes addresses.

## Confidence / attribution

All three key/reader mismatches and the `plen=0` path were read off `launch.py` and the
config files in-session — **code-verified**. The proposed fixes (unknown-key assertion,
`last_ingress_plen`, skip-instead-of-PASS, an idle-slots-must-be-all-zero check that stays
meaningful even at plen=0) were suggested at the end of the session and are **not yet
implemented or confirmed by Le** `[unverified]`.

**Promotion candidate.** This is procedural, not a fact about M1: *"before trusting a red
test, prove it can fail — silent config defaults and empty-input comparisons both degrade a
negative control into a positive one."* It fits alongside the existing S6a lesson that a new
per-request dimension lands on places which hardcoded the old default.

## Pointers

- [[decode-lanes-must-be-equal-length]], [[slot-reuses-bsz-batch-is-not-a-storage-axis]] —
  the M1-S1 seam these configs are meant to exercise.
- [[s6a-decode-kv-retain]] — where plen=0 retain rounds came from, which is what hollowed out
  `_kv_seed_check`.
