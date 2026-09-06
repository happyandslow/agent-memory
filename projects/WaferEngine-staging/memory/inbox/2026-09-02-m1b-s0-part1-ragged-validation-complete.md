# M1b-S0 Part 1 ragged validation complete — bit-exact on real CS-3, +2.36% overhead — 2026-09-02

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## What happened / finding

M1b-S0 Part 1 (the per-lane ragged compute kernel in
`models/qwen3_1p7b-decode-ragged-batch/src/decode.csl`, 583 changed lines vs
the `qwen3_1p7b-decode` baseline) is **fully verified end-to-end**, and its
equal-position production overhead is measured. Full results log (work repo,
untracked): `docs/analysis/2026-09-01-m1b-s0-validation-results.md`.

Chain of evidence, all PASS:

- **A0 closed:** attempt-G receipt `987264bd...` validated on the CS-3 login
  node (the earlier `bwrap` failure was transport-only; running the public
  validator remotely against the existing receipt bypassed it, RC 0,
  `all_expected=true`). Accepted device semantics: `@fadds` scalar-DSR =
  serial_chain; softmax group replay = serial_replay_advance; `@fmachs` =
  one f32 rounding per accumulate step.
- **A1 closed:** new test-only physical oracle
  (`tests/s0_a1_physical_oracle.py`, root-pinned acceptance anchor
  `5151af32...`) reproduces all 40 witness cases bit-exactly; 16/16 gates;
  full host suite 904/904. Implemented as NEW files only — editing C2 or the
  streaming reference would have drifted the probe's frozen SOURCE_CLOSURE
  and made the A0 receipt unrevalidatable.
- **Simulator (2x2 blocks, P=8):** 53/53 per-function+chained scenarios,
  23/23 mutation/red faults caught (incl. the old double-alpha / omit-zero
  debt), zero vacuous comparisons.
- **Integrated sim:** P1-I1 30/30, P1-I2 24/24, P1-I3 row-wrap 14/14,
  P1-I4 rearm 10/10, P1-I5 7/7, rope-advance-per-layer red 4/4.
- **Real CS-3, full Qwen3-1.7B (cap-2048 config, bsz=2, TOP_K=20):**
  - equal S0 == exact `origin/main`: bit-identical (2026-08-31 A/B);
  - equal vs 28-layer NumPy: bf16 top-20 values bit-exact; index deviations
    only inside a bf16 tie plateau (f32 logits 1.3399..1.3444 all round to
    1.34375; k-cutoff membership within the plateau is arbitrary);
  - **ragged [256,512] vs NumPy: 40/40 top-k indices AND bf16 values
    bit-exact, both lanes — zero ambiguity**;
  - ragged lane0 == equal-run lane0 bit-exact (peer isolation at full scale);
  - rearm: rounds bit-exact within AND across wsjobs;
  - row-wrap Q=257: 257/257 steps, finite, rank-monotone.
- **Perf (raw TSC, equal request PREFILL 256, 129 timed tokens/run):**
  main median 665,007.8 cyc/token (n=12) vs S0 mode-0 680,711.6 (n=10) →
  **+2.361% (+15,704 cyc/token)**; run-to-run spread ~10 cycles on both
  sides, so the delta is mechanism cost, not noise. 10 launches excluded as
  EPCC 502 (known transient). Resource deltas not collected (SdkLauncher
  retains no compile artifacts).

## Reusable mechanics (promote to topics on maintain pass)

- `S0_TRACE_JSON` top-k index/value words are **rank-major interleaved (lane
  fastest)**; the trace adapter's npz `(bsz, top_k)` labels are misleading.
- Device-vs-NumPy bf16 noise floor is ZERO → the right comparison standard
  is bit-exact values + tie-plateau-only index tolerance, not an
  atol/rtol band.
- `s0_verify_mode` is a compile-time decode.csl param (mode 1: lane b at
  `(b+1)*P_BLOCK_SIZE`); production `launch.py` does not plumb it — add
  `rg.set_param_all("s0_verify_mode", cfg.get("S0_VERIFY_MODE", 0))` in a
  staging copy only.
- Full-scale NumPy reference: drive
  `_execute_public_streaming_mechanics(plan, obs, snapshot)` directly;
  ~100 min/case single-core; run equal/ragged as parallel `setsid nohup`
  processes (a harness-managed background task was killed once mid-run).
- Device runs on the 8/31 bundle pattern cost ~3 min wall each including
  compile, so device-side controls (isolation/rearm/row-wrap) are cheap.
- Process note (Le, 2026-09-01): verification ceremony right-sized — one
  approved plan, straight-through execution, plain logs + one results
  markdown; no per-step signatures/receipts for internal kernel features.

## Boundary / next

Part 2 (heterogeneous metadata ingress,
`docs/session-prompts/M1b-S0-P2-metadata-ingress.md`) not started; S0 stage
closure requires it. Then S1/D1 per-lane EOS. Work repo changes staged but
uncommitted (Le commits).
