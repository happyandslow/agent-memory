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

## Pipelining hypothesis

Option 3 (tail skips logits/sample on forced steps) may make forced decode faster per token than normal decode because it removes the ht_tail→ht_head token-feedback bubble and lets the layer pipeline fill. This is **unverified** and should be measured with TSC before being quoted. It is a structural pipeline-overlap claim, not an lm_head-saving claim.

## Verification

Use the S6a value-based full-distribution / teacher-forced oracle method, but dump logits at `tail_step == F-1`, the first free-token logits that depend on all forced KV.

See also: [[s6a-decode-kv-retain]], [[kv-cache-policy-tradeoffs]].
