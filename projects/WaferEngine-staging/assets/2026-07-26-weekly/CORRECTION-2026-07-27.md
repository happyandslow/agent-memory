# ⚠️ CORRECTION — this deck's force-decode conclusion is FALSIFIED (2026-07-27)

**Do not reuse `fig_fsweep.png` / `fig_mechanism.png` or the force-decode slides from this
deck without reading this first.** The deck was built 2026-07-26; the claim was overturned
the next day by a real-hardware measurement.

## What the deck says (wrong)

- *"A straight line rules that out. Pipelining would flatten once the pipeline is full; a
  constant saving per forced step means work is simply not being done."*
- *"A forced step costs about 28% of a plain step here, roughly 806 cycles against 2,856."*
- Open question posed: *"Measuring real-scale pipelining needs a compute-heavy configuration.
  Is it worth the wafer time?"*

## What is actually true

**The gain IS layer pipelining.** Two independent errors in the deck's reasoning:

1. **The discriminator was invalid.** A *filled* pipeline is also linear in F — each forced
   step costs `max_stage` instead of the full serial chain, so cycles are linear with slope
   `(C_serial − max_stage)`. Both hypotheses predict a straight line. "A straight line rules
   that out" is simply not a valid inference; no knee was ever going to appear.
2. **The magnitudes never fit skip-compute.** The toy tail is ~5% of a step, yet the measured
   saving was ~71% of a step.

**Evidence (2026-07-27):**

- *Pipeline-depth ablation* (sim, `n_layers=8` fixed, block count varied): forced/free =
  **48.6% / 24.9% / 12.9%** at 2/4/8 blocks vs pipelining's `max_lpb/n_layers` =
  **50% / 25% / 12.5%**. Skip-compute predicts a flat, geometry-independent ~95%.
- *Full-scale device* (real WSE-3, 524,288 PEs, dim 2048, 28 layers / 8 blocks, vocab
  151,936, prefill 256→3840): forced/free **flat at 11.7 → 12.0%** — a **~8.5× cheaper
  forced token** — while the free step grows 479.2 → 560.0 µs/token. Skip-compute requires
  that ratio to climb toward 100% as context grows.

**The 28% figure is a toy-geometry artifact** (`max_lpb/n_layers = 2/7`). At real scale it is
**~12%**. The gain scales with **pipeline depth relative to layer count** — an architectural
lever — **not** with vocab / lm_head size as the deck implies.

## Answering the deck's own open question

*"Is it worth the wafer time?"* — **Yes, and it was cheap:** 8 full-scale runs took **29
minutes** total (compile ~43–54 s, decode ~19 s each). The deck's premise that the cluster was
unavailable ("cluster-gated") was also stale.

## Caveat carried forward

The device runs are **timing-only** — the numpy oracle and the `KV-SEED` / `LOCAL-TOPK` gates
are sim-only, so device-scale numerics at large F are **unverified**. Force-decode correctness
is sim-verified at F=4 (max_abs 9.8e-5) on the identical kernel.

## Where the corrected record lives

- ContextBase → MeshAgent → Logs: *"2026-07-27 Result — Force-decode gain is layer PIPELINING,
  not skip-compute (real WSE-3)"*
- `memory/topics/s6b-force-decode.md` (Performance attribution section, rewritten)
- Repo durable docs: `GOALS.md` §7 (now `[answered]`), `PROGRESS.md` (Failed approaches +
  Checkpoint metrics + session log), `milestones/M0-reuse-foundation.md` (2026-07-27
  verification-log section)

**If this deck is ever re-presented, the force-decode slides must be rebuilt** (via the
`wafer-slides` skill) with the corrected mechanism and the real-scale numbers.
