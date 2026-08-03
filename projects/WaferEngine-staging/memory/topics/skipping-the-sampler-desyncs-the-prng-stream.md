---
summary: A correct force-decode still fails the continuation check — the skipped tail took a PRNG draw with it — 2026-07-30
tags: [WaferEngine-staging, drained-inbox, 2026-07-30]
---

# A correct force-decode still fails the continuation check — the skipped tail took a PRNG draw with it — 2026-07-30

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-07-30

Source: `memory/inbox/2026-07-30-skipping-the-sampler-desyncs-the-prng-stream.md`

# A correct force-decode still fails the continuation check — the skipped tail took a PRNG draw with it — 2026-07-30

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You have added force-decode (or any "skip the output head on steps whose token
is already known" optimisation) and you are validating it the obvious way: feed
in tokens a free run actually produced, and check that the continuation from
step `m-1` onward matches that free run token for token.

**It diverges from the very first real step, and your implementation is
correct.** You will then go and audit the KV cache, colour budget, rewind
arithmetic and RoPE — none of which are wrong. Device runs are ~14 minutes each.

## Why

Sampling on this path is **not greedy**: `temperature=0.6, top_p=0.95, TOP_K=20`.
`ht_tail.csl:1095` draws `random.random_f32(0.0, 1.0)` once per step from a
running PRNG stream that is re-seeded once per round
(`set_global_prng_seed(sample_seed)`).

Determinism therefore rests on *same seed **and same number of draws, in the
same order***. The skip branch bypasses `tail_sample_token` — so on a run with
`F` forced steps the stream advances **F−1 fewer times**. At the first real step
the free run is on its m-th random number and the forced run is on its 1st: same
candidate set, different draw, different token, and everything after it forks.

## The fix, and why it costs nothing

In the skip branch, still call `random.random_f32` on the sampling PE and throw
the value away.

`random.csl:54` is two `@random16()` LFSR reads plus a few bit ops — roughly
10–20 cycles, on **one PE out of 524,288**, off the critical path (forced steps
do not make `ht_head` wait for a token). Against a ~557,000-cycle step that is
**~0.003%**. Every real saving survives: the 151,936-wide `lm_head` matvec,
`tail_final_rmsnorm`, the Y-axis logits reduce, local + merge top-K, the
`xready` barrier and the north token emit are all still skipped.

Prefer calling `random_f32` and discarding over calling `@random16()` twice
directly — if the library ever changes how many bits it consumes per draw, the
discard stays aligned automatically.

## Two second-order facts found while checking this

**`done_flag` is set inside `tail_sample_token`,** so skipped steps never update
it. That is safe *only because* forced tokens come from a real free run and so
never contain EOS — which means the checker must assert that, rather than
assume it.

**EOS never appears in the trace at all** when `enable_early_stop` is on. In
10,571 sampled ids across 8 requests there were **0** hits on
`eos_token_ids = [151645, 151643]`, while all 8 requests report
`halted_eos: True`. Cause: `tail_sample_token` overwrites `pred_token_buf[0]`
with `STOP_TOK` on the same step it samples EOS, so the EOS id never goes on the
wire; every array ends in `-2`. **The in-source comment "The EOS was emitted on
its own step" is wrong with early stop enabled.**

## Implications / next actions

- [ ] Any future skip-the-tail optimisation on this kernel inherits the same
      trap. The general form: **a skipped stage that consumes stream state
      (PRNG, a counter, a queue slot) breaks reproducibility even when it
      produces nothing you need.** Ask what the skipped code *consumed*, not
      only what it produced.
- [ ] The zeros left in `decode_sampled_ids[0 : F-1]` by skipped steps are the
      only positive evidence the gate actually fired — the continuation check
      alone cannot distinguish "pipelining engaged" from "pipelining never
      started". Worth asserting on deliberately (`--expect-prefix skipped`).

## Pointers

- `src/decode/ht_tail.csl:1095` (the draw), `:1258` (per-round reset),
  `:1377-1392` (skip branch), `:1122-1131` (pad / `done_flag`).
- `models/qwen3_1p7b-e2e-pdSeparate`, worktree `/home/lexu/we-m2bench`,
  snapshot `a3a509c` + M2-S2 changes.
- Related: [[s6b-force-decode]], [[decode-lanes-must-be-equal-length]].
