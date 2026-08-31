# A per-group reduction whose sum is short by exactly its first element — 2026-08-31

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation this applies to

A CSL reduction over a ragged, per-lane-packed arena returns sums that are
*close* to right. Most cells pass tolerance; a handful fail with a near-constant
absolute deficit. The companion max checkpoint is bit-exact, the input arena is
pinned bitwise correct, the capacity tails are zero, nothing is NaN/Inf — so
every "fixture is wrong / readback layout is wrong / oracle is wrong" hypothesis
is already eliminated. This is what a DSR that was reused across a group loop
looks like from the outside.

## What happened / finding

- M1b-S0 stage-3 (`softmax-scalar`) ran clean on device — RC 0, 64/64 PE
  completion markers — but the differential compare failed on exactly one
  checkpoint: `local_sum`, 32/256 cells, `max_abs = 0.9999873638153076`. First
  failure `[0,0,0,0]`: expected `1.3678793907165527`, observed
  `0.3678920269012451`. Per-row failure counts `[16,0,0,0,8,8,0,0]`.
  `local_max`, `score_f32`, `score_bf16` and the capacity tail all PASSED.

- Reconstructed signature: the 32 failures are 4 `(row, lane)` slots × all 8
  X-columns, **always group g=0, never g=1** — `(y=0,b=0,L=2)`,
  `(y=0,b=1,L=3)`, `(y=4,b=1,L=2)`, `(y=5,b=1,L=2)`. At every one, the observed
  sum equals the device's own exp memory summed over cells `[1..L-1]`: **the
  first live cell of each per-(b,g) group was dropped.** The ~1.0 deficit is
  the dropped `exp(max) = 1` cell.

- The defect was present in *every* `L≥2` g=0 slot; it only exceeded tolerance
  in the four where the first cell happened to be large. Wherever the first cell
  was ~1e-14 the residue displayed as 0 and the cell passed. `L=1` lanes and all
  g=1 groups are exact by construction. **A tolerance gate nearly missed a
  first-element-dropping bug because the dropped element is usually tiny.**

- Cause is the hot-path optimization that loaded a `save_address` source DSR
  once per positive request and reduced through it for all G groups —
  `save_address` advances the DSR but not the DSD template, so the group loop
  did not restart at each group's first cell. The repair (staged, not yet
  device-gated at capture time) replaces it with a per-(b,g)
  `save_address=false` scalar reduce + store + explicit `current_len` advance +
  `G*(C-current_len)` tail, mirroring the qwen3_4b safe idiom, applied
  symmetrically to both the max and the sum walks.

- **The review blind spot is the durable part.** This same optimization had
  already passed: (a) an independent read-only CSL review that explicitly
  verified "save_address advances the DSR but not the DSD template" and
  returned *no correctness findings*; (b) a full host unit suite; (c) stages 0
  and 6 of the device harness (rope stages, which do no collective reduction).
  Only a stage that actually executes the production reduction body against an
  independent NumPy oracle caught it. Source-level reasoning about DSR reuse is
  not a substitute for a differential gate on the stage that uses it.

## Implications / next actions

- [ ] When a reduction checkpoint fails and its companion max/min checkpoint
  passes bit-exact, suspect a *walk-position* bug, not an arithmetic one — max
  hides an off-by-one start whenever the extremum is not the skipped element.
- [ ] For any tolerance-gated reduction over ragged groups, add an exact
  relation the tolerance cannot mask (e.g. the g=0 first-cell contribution),
  or the first-element class of defect is invisible on realistic magnitudes.
- [ ] Re-run fresh stage-3 gates before unblocking stage-4 (`score_v`).

## Pointers

- `WaferEngine-staging/models/qwen3_1p7b-decode/src/decode.csl` — `softmax_score`
  max/sum loops (staged blob `99b7c589…` pre-repair)
- `WaferEngine-staging/models/qwen3_1p7b-decode/tests/s0_reference.py`,
  `run_s0_verification.py`
- `WaferEngine-staging/.s0-artifacts/m1b-s0-part1-20260831-ae-fix9`
- Related: [[an-oracle-cannot-check-an-input-it-re-derives]],
  [[a-regression-gate-that-cannot-pass-by-construction]],
  [[csl-module-dsd-length-carryover]]
