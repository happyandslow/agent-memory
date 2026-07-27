---
summary: S6b forced-token decode design: today’s decode already consumes one host-forced token per round; S6b generalizes that to F token-granular forced steps, with an inert F=1 baseline and a staged path to pipelined forced decode.
tags: [waferengine-staging, qwen3, decode, force-decode, s6b, kv-reuse, csl, wse-3]
---

# S6b force-decode design

Curated from `memory/inbox/2026-07-21-s6b-force-decode-design.md`. Source-of-truth implementation plan lives in the work repo at `docs/superpowers/plans/2026-07-21-m0-s6b-force-decode.md`.

## Core finding

Standalone `qwen3_1p7b-decode` already force-decodes exactly one token per round: step 0 consumes a host-seeded embedded X vector from `x_stream`; step ≥1 is autoregressive via `ht_tail` sampling and `tok_bcast` back to `ht_head`. S6b is therefore not a new mechanism from zero — it parameterizes the forced prefix length to `F`, with `F=1` as today’s byte-identical inert baseline.

`F` is a **token count**, not a block count. It indexes the global decode step loop, unlike `prefill_len` / `retained_len`, which are per-PE cache-column units. Making forced decode block-aligned would force 256-token granularity on device and be unusable for real turns.

## Design decisions

- Carry `F` in KV-ingress meta slot 3, currently a pad. Store the value directly, default `F=1`; do not store `F-1`.
- The two gates are deliberately off by one: `ht_head` reads forced host embeddings for `ht_step < F`; `ht_tail` skips logits/sample/emit for `tail_step < F-1` and samples at `F-1`, producing the first free token for step `F`.
- Widen the N-header to an explicit two-wavelet `[N, F]`, rather than packing F into a batch lane. Batch-lane packing collapses at `bsz=1`.
- Stage the work: S0 inert `F=1`; S1 correctness with host-fed F embeddings and unchanged tail/token drain; S2 pipelined by skipping tail work for `F-1` pure-forced steps and guarding the `ht_head` token drain at `ht_step >= F`.
- `demux` needs no semantic change; it is a per-cycle store-and-forward pump that re-arms. The host must push F X-vectors and the `x_stream` quota must scale with `F_max`.

## Performance attribution — REVERSED 2026-07-27 on real WSE-3

**The gain is LAYER PIPELINING, not skip-compute.** The 2026-07-23 sim conclusion was wrong for two independent reasons.

1. **The discriminator was invalid.** "Linear ⇒ fixed per-item skip-compute; saturating ⇒ pipelining" does not hold. Once the forced steps run open-loop the pipeline fills, and each forced step then costs `max_stage` instead of the whole serial chain — giving cycles **linear in F** with slope `(C_serial − max_stage)`. Both hypotheses predict a straight line, so linearity carried no information and no knee could ever appear.
2. **The magnitudes never fit.** The toy tail is ~5% of a toy step, yet the measured saving was ~71% of a step.

**Ablation (sim, `n_layers=8` FIXED, only block count varied)** — forced/free vs the pipelining prediction `max_layers_per_block / n_layers`:

| blocks | max_lpb | measured | pipelining | skip-compute |
|---|---|---|---|---|
| 2 | 4 | 48.6% | 50.0% | ~95% (flat) |
| 4 | 2 | 24.9% | 25.0% | ~95% (flat) |
| 8 | 1 | 12.9% | 12.5% | ~95% (flat) |

**Full-scale device (real WSE-3, 524,288 PEs, dim 2048, 28 layers / 8 blocks, vocab 151,936):** with prefill swept 256→3840, forced/free stays **flat at 11.7→12.0%** while the free step grows 479.2→560.0 µs/token — i.e. a **~8.5× cheaper forced token** (55.9→67.4 µs). Skip-compute requires that ratio to climb toward 100% as context grows, because its saving is the sequence-*independent* tail. The mild upward drift is pipelining's own prediction: the ratio approaches `max_lpb/n_layers = 4/28 = 14.3%` from below.

**Pipeline-depth ablation ON REAL HARDWARE (2026-07-27).** Same full-size config, only block count varied — skip-compute is geometry-independent, so this is a binary discriminator:

| geometry | PEs | max_lpb | free µs/tok | forced µs/tok | measured | pipelining | skip-compute |
|---|---|---|---|---|---|---|---|
| 2×2 (4 blocks) | 262,144 | 7 | 468.9 | 97.2 | **20.7%** | 25.0% | ~12% (flat) |
| 2×4 (8 blocks) | 524,288 | 4 | 479.2 | 55.9 | **11.7%** | 14.3% | ~12% (flat) |

Halving the blocks nearly doubled the forced-step cost (×1.74) while the free step barely moved (×0.98) — the free step is geometry-insensitive because it serializes through all 28 layers regardless. (`nb2`, 14 layers/PE, does not link: out of PE memory + task table.)

**Model fit + decomposition.** Both points fit `forced/free = (max_lpb/n_layers)·x` with ONE free parameter `x = T_blocks/(T_blocks+T_tail)`: **x = 0.823**, i.e. **`ht_tail` is 17.8% of a free decode step** (measured). Error 0.4% on both points. ⇒ **8.55× = 1.22× (skip-compute) × 7.0× (pipelining)**, where `7.0 = n_layers/max_lpb = 28/4`. **Skip-compute is real but minor; pipelining supplies 7× of the 8.5×.**

**What skip-compute actually is (source-verified).** The `ht_tail.csl:1347` gate `tail_step >= forced_decode_len - 1` skips: final RMSNorm, `lm_head` GEMV (`vocab×dim`, dominant), logits Y-reduce, local top-K, top-K X merge-reduce, sampling, the X/Y route repaints + xready barrier, and the north token emit. Deliberately OUTSIDE the gate: the Z drain and the south top-k emit (re-sends stale buffers so host receive count stays `n_steps`). `ht_head.csl:308` also skips the blocking token-color wait + `embed_gather_dispatch()`. **`decode.csl` never branches on `forced_decode_len`** — all 28 layers run identically on forced steps. Every skipped item scales with `vocab`/`dim`/`TOP_K` and has **no sequence-length term**, which is precisely why the context sweep discriminates.

**Consequences.** For M2's `R*`, a forced token costs **≈12% of a free decode token at real scale, not 28%** — the 28% was a toy-geometry artifact (`2/7`). The saving is an **architectural lever**: it scales with pipeline depth relative to layer count, so *more blocks ⇒ cheaper forced tokens*. The previously asserted "strengthens with vocab because lm_head grows" mechanism is **not** what drives it.

**Caveats.** Device runs are timing-only — the numpy oracle and the `KV-SEED`/`LOCAL-TOPK` gates are sim-only, so device-scale numerics at large F are unverified (correctness is sim-verified at F=4, max_abs 9.8e-5, identical kernel). All 256 steps were confirmed to execute, ruling out "fast because steps were skipped".

**Reusable lessons.** (a) Before reading a curve's *shape* as a mechanism signature, verify the rival hypothesis predicts a *different* shape — and cross-check the magnitude against a cost model. (b) Simfab cannot reach real geometry (~12–24 h per decoded token at 524k tiles); mechanism ablations are fine in sim, but performance attribution at scale must run on device. (c) `cyc/token` from `launch.py` divides by a stale `counted_tokens` when `DECODE_LENS < MAX_SEQ_LEN − PREFILL_LEN` — the S6b sim numbers are **5× too low**; set `DECODE_LENS = MAX_SEQ_LEN − PREFILL_LEN`.

## Verification

Use the S6a value-based full-distribution / teacher-forced oracle method, but dump logits at `tail_step == F-1`, the first free-token logits that depend on all forced KV.

See also: [[s6a-decode-kv-retain]], [[kv-cache-policy-tradeoffs]].

## Bring-up lessons (2026-07-23)

- Forced tokens are host-owned. Build one deterministic `forced_tokens[F][bsz]` sequence and feed the same token IDs to device embeddings and the numpy oracle. Do not read forced-step device samples back from the spill path; those outputs are discarded/dummy by design.
- Preserve fabric producer/consumer counts when introducing F. The safe Step-1 edit kept the `ht_step == 0` seed gate, drained the color-7 token every step, and added a separate `ht_step < F` overwrite. The unsafe if/else rewrite skipped drains for forced steps 1..F-1 and would hang or poison the next round.
- When changing the deterministic comparison point from step 0 to `F-1`, grep every verifier/diagnostic consumer for hardcoded step-0 reads. A stale Pass-1 top-k consumer compared device step 0 against oracle step F-1 until it was updated.
