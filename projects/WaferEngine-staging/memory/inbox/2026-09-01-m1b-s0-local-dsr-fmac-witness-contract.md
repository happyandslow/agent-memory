# M1b-S0 local DSR/FMAC witness must bind production shapes and cannot self-approve — 2026-09-01

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

M1b-S0 Part 1 reached a device-only arithmetic boundary after its accepted C2c
host gates.  Source inspection cannot determine the exact real-WSE result of
the scalar-destination `@fadds(ptr, scalar, src1_dsr)` reduction or every
mixed-BF16/f32 `@fmachs` DSR traversal.  A test-only one-PE probe is therefore a
prerequisite to full 28-layer arithmetic, not optional debug instrumentation.

Independent review rejected the first probe delivery before compile.  The
evidence validator could be unlocked entirely from local data: synthesize the
pre-registered expected observations, label the receipt
`origin=real-cs3-device`, and provide an `ACCEPT` JSON with a reviewer string
different from the operator.  `current_status()` then returned
`PRIMITIVE_WITNESS_ESTABLISHED`.  A provenance label and a second arbitrary
string are not independent evidence.

The corrected A0 boundary is fail-closed:

- the A0 harness has no accepting global-status branch and always leaves
  `BLOCKED_LOCAL_DSR_FMAC`; a later root-reviewed patch must pin the exact
  accepted real-device receipt;
- the canonical plan binds the host contract, runner, layout, PE program, and
  command proposal, while a receipt binds a resolved, all-regular-file artifact
  inventory with relative path, size, SHA-256, and MD5;
- plans and receipts are published exclusively and atomically; evidence is read
  once from regular non-symlink bytes and the same snapshot is parsed and
  hashed;
- device inputs and guards are read back bit-exactly before launch; a host hash
  echo is insufficient;
- every post-construction failure calls `SdkRuntime.stop()` in `finally`; outer
  timeout and actual appliance-job cancellation remain with the reviewed
  `cs3-runner`/`run_device` operation; and
- compile and real-device execution are separately reviewed gates.  Simulator
  output cannot certify arithmetic.

The live full-model geometry also matters.  For
`model_config/test_device_2x4block_s0_bsz2.json`, source-derived values are
`P_BLOCK_SIZE=256`, `dim_per_pe=8`, `kv_cols=4`, `gqa_group_size=2`, and
`kv_len_per_pe=32`.  The witness must distinguish the actual production call
forms:

- RMSNorm/QK-norm omit `@load_to_dsr` options and reduce extents 8 and 4;
- softmax uses explicit `.save_address=false` and must cover every live length
  1 through 32, including group replay and descriptor advance;
- the Q/K/V three-accumulator map uses reduction extent 8 and unequal
  output/weight extents 8/4/4; and
- every physical input/output arena needs independent leading/trailing guards
  plus an extent-plus-one poison region.  Capacity tails are semantic zero
  checks, not guards.

Testing only lengths up to eight cannot establish softmax lengths up to 32;
using one common three-accumulator extent cannot establish late binding of the
8/4/4 lengths; and a later case that clears an adjacent output can hide an
earlier out-of-bounds write unless every bank owns its own guards.

## Implications / next actions

- [ ] Claude Code corrects the test-only probe and its host evidence contract;
  root independently reviews the named positive/red gates before compile.
- [ ] Compile-smoke verifies syntax/layout/resources and RPC exports only; it
  does not witness arithmetic.
- [ ] A separately authorized minimal real-CS-3 run records two full-bank raw
  observations, exact input readback, guards, completion state, artifact/job
  provenance, and bitwise determinism.
- [ ] A0 must pass before the cap-Q1 physical oracle is promoted or any complete
  28-layer NumPy/CS-3 arithmetic is accepted.
- [ ] Equal-position performance A/B remains blocked until the complete
  correctness artifact is frozen.

## Pointers

- `WaferEngine-staging/docs/analysis/2026-08-30-m1b-s0-part1-execution-log.md`
- `WaferEngine-staging/models/qwen3_1p7b-decode-ragged-batch/tests/s0_local_arithmetic_probe.py`
- `WaferEngine-staging/models/qwen3_1p7b-decode-ragged-batch/tests/s0_local_arithmetic_probe/pe_program.csl`
- `WaferEngine-staging/models/qwen3_1p7b-decode-ragged-batch/src/decode.csl`
- Related: `2026-09-01-m1b-s0-c2c-host-gates-and-collective-source-binding.md`
- Related: `2026-08-31-softmax-save-address-dsr-drops-first-live-cell.md`
