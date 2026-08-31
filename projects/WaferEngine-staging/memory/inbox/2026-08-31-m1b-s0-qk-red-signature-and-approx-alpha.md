# M1b-S0 low-amplitude QK red controls need arithmetic-specific observability — 2026-08-31

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

- When a deliberately broken QK kernel is compared under the production
  numerical tolerance, an active fault can still report zero mismatches. In
  the M1b-S0 ragged fixture, removing the post-reduction alpha changed live
  scores by at most `0.0015934333205223083`, below locked
  `atol=0.006, rtol=0.005`.
- The missing-alpha simulator control became independently observable without
  tightening tolerance: for frozen `head_dim=16`, the faulty whole-arena
  output was bit-exact `4E`. A model preregistered from `expected.npz` before
  opening observed output caught exactly 416 live differences and verified
  all 16,992 capacity-tail cells remained zero. Fresh FIX59 then passed this
  gate with 64/64 PE completion and all provenance predicates.
- Do not mechanically reuse `E/4` for a double-alpha control. The device CSL
  `approx_math.rsqrt_f32(16)` evaluates to f32 bits `0x3e7fffff`
  (`0.24999998509883881`), not exact f32 `0.25`; naive `E/4` differs bitwise
  from the calibrated simulator model at all 416 nonzero cells. The current
  fixture's double-alpha semantic error is also only `0.00039835836`, so the
  generic locked comparison would again report zero mismatches.

## Implications / next actions

- [ ] For each low-amplitude red control, preregister a fault signature only
  when its device arithmetic and rounding are independently derivable; build
  the model before observed output is opened and keep the ordinary locked
  comparison honest.
- [ ] Give double-alpha a separately reviewed, finite power-of-two-amplified
  Q/K fixture and positive twin, and pin the simulator alpha bits/model before
  executing a new mutant root.
- [ ] Keep simulator exact-signature evidence scoped to functional control
  verification; it does not establish real-CS-3 bitwise behavior or
  performance.

## Pointers

- `WaferEngine-staging/docs/analysis/2026-08-30-m1b-s0-part1-execution-log.md`
- `WaferEngine-staging/models/qwen3_1p7b-decode/tests/run_s0_verification.py`
- `WaferEngine-staging/.s0-artifacts/m1b-s0-part1-20260831-ae-fix59-red-qk-missing-alpha-signature`
