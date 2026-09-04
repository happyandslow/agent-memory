# M1b-S0 Part 2+3 correctness complete — production ingress bit-exact on CS-3; perf sweep in flight — 2026-09-04

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are resuming M1b-S0 work and need to know how far validation got: the
last inbox state said Part 1 done, Part 2 not started. As of 2026-09-04 the
Part 2+3 build (Part 2 metadata CSL + Part 3 **production** `launch.py`
vector-metadata ingress, no adapter injection) has **all correctness gates
passed** on sim and real CS-3; only the final perf-sweep aggregate was
pending at session end.

## What happened / finding

- **Real CS-3, full Qwen3-1.7B bsz=2, production ingress path:**
  - equal-position == exact `origin/main`: **byte-exact (124/124)**;
  - ragged [256,512] vs 28-layer NumPy: **40/40 indices AND values
    bit-exact**, lane0 peer-isolation bit-exact;
  - swapped [512,256] vs NumPy: values 40/40 bit-exact; 4 index deviations
    (ranks 16–19) all at bf16 value 1.34375 — the **same tie plateau** as
    the 2026-09-01 equal-case lane1 deviation, admissible under the
    established policy. This per-lane match against a *swapped* reference is
    the control that settles lane↔metadata binding correctness;
  - rearm two rounds bit-exact (round0 == standalone ragged run); rowwrap
    Q=257: 257/257 steps, finite, rank-monotone.
- **Host/sim:** final full host suite **975/975**; Part 1 regression on the
  combined artifact 53/53 + 23/23 reds; integrated P1-I1..I5 + red all pass;
  Part 2/3 matrix 6 positives + mode0-parity **byte-exact** (overlay inert in
  mode 0) + 2 reds fail-closed (stall, per the 09-03 red-stall note);
  UPLOAD_IDENTITY_PASS (372 comparisons: production packer == record bytes).
- **Perf (Step 6, raw TSC, equal PREFILL 256 / 129 timed tokens):**
  validation pair main 665,015 vs Part 3 S0 680,458 cyc/token → **+2.32%**,
  consistent with Part 1's +2.36%. Full 12-rep alternating sweep launched;
  **final aggregate not yet recorded** at session end — check
  `docs/analysis/` results doc in the work repo for the closing number.

## Reusable mechanics

- **`SdkLauncher.download_artifact` retrieves worker-side files** (the
  `--retain-topk` trace tarball) to the control side with zero device-ABI
  changes — but it **returns None even on success**; verify the downloaded
  file exists instead of keying on the return value.
- Swapped-case NumPy reference without touching frozen modules: driver-level
  monkeypatch of `_resolve_scenario`, gated by an **in-place identity
  control** (patched resolver must reproduce the original case bit-exact
  first). Avoids extending the frozen record/streaming files and the pin
  cascade that would follow.
- `cs_python`'s container binds **only `$PWD`** (`/tmp` is not mounted):
  place drivers/scratch under the repo and run with cwd at the repo root, or
  subprocess launches fail confusingly.

## Implications / next actions

- [ ] Record the final perf-sweep aggregate when the 12-rep run completes;
      then M1b-S0 (Parts 1–3) can be reported closed for correctness+perf.

## Pointers

- Work repo: `models/qwen3_1p7b-decode-ragged-batch/`; results doc under
  `docs/analysis/` (Part 2+3 results, started 2026-09-03)
- Related: [[2026-09-02-m1b-s0-part1-ragged-validation-complete]],
  [[2026-09-03-frozen-pin-cascade-after-intentional-source-change]],
  [[2026-09-03-red-fault-sims-stall-and-timeout-cannot-kill-container]]
