# A batch mixing prefix-hit and prefix-miss lanes does NOT need ragged support — and the scalar that really pins lanes together is RoPE, not `iter_num`

Date: 2026-07-26 · Repo: `WaferEngine-staging` · Branch base: `lexu/staging/kv-feature` (M1-S1 review)

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained

## The situation this applies to

You are designing the M1-S3 hit/miss experiments (some resident requests hit a cached
prefix, others start cold) and trying to decide what a single batch is allowed to contain.
The plausible-sounding conclusion — the one written down on 2026-07-25 in
[[decode-lanes-must-be-equal-length]] — is: *a hit lane starts at `L_match` occupancy and a
miss lane starts at 0, therefore mixed batches are ragged, therefore S3 must use `bsz=1` or
force every lane down the same hit/miss path.*

**That conclusion is over-constrained and should not be used to shape S3's configs.** Le
pushed back on it in this session and the pushback is correct.

## Why it was wrong: "cash in the hit" is not the only way to honour a hit

The earlier reasoning silently assumed **take-over semantics** — that a hit means jumping
`iter_num` straight to `L_match` and starting free decoding immediately. That is one option
(and it is exactly what S6a already does: `round_reset` `decode.csl:308` seeds
`iter_num_bank[l]` from `retained_len_per_pe_rt`, and `rope_init_from_delta_p` `:698-704`
rotates RoPE into position in one shot). Under take-over, a hit lane sits at 16 while a miss
lane climbs 0→16, so yes, lengths diverge.

But a hit lane can also simply **ride along**: `iter_num` advances one per step as usual and
the hit lane just does no useful work. Lengths never diverge. Attention reads `[0, iter_num)`
for whatever `iter_num` happens to be, so nothing in the attention path needs changing —
the choice is purely about how the round is scheduled.

## The rule that makes mixed batches legal with today's all-scalar metadata

> **Round start = `min(L_match)` over the active lanes; `F = prompt_len − start`.**

Every lane walks from the same start to the same end, so all the round-wide scalars stay
valid. `L_match` may then differ freely per lane.

The part that makes this safe rather than merely convenient: a hit lane's re-computation
over `[start, L_match)` is **bit-identical to what is already in its slot** — same tokens,
same weights, same RoPE angle (angles are keyed to global position), and the prefix
attention it reads is the correct resident data. So the redundant work produces the same
K/V it overwrites. **No mask, no guard, no special case — correctness falls out.**

Worked example: A′ matches 16, B′ matches 0 → start 0, F 16, batch saves nothing but is
correct. A′ matches 16, B′ matches 8 → start 8, F 8, the batch saves 8 steps and A′ wastes 8.
So **batch benefit = min over lanes**, which is the head-end mirror of the tail-end rule
already in the kernel (a finished lane keeps advancing and emits pad, `ht_tail.csl:360-362`
`done_flag`) — **batch cost = worst lane**.

**Retract:** the claim that the triple *(prompt length, `L_match`, remaining force-decode
suffix)* must match across lanes. Only the first of the three is a real constraint.

## The constraint that does survive: equal total prompt length — and RoPE is the hard half

Two round-wide scalars pin all active lanes to the same sequence position:

1. `iter_num` — a scalar (`decode.csl:167`), doubling as DSD length and as the packed
   score-buffer inter-lane stride. This is the one [[decode-lanes-must-be-equal-length]]
   documents.
2. **RoPE rotation state** — `cos_cur_f32` / `sin_cur_f32` are `[_attn_per_pe/2]`
   (`decode.csl:537-541`), with **no `bsz` axis at all**, and `rope_step_advance()` runs once
   globally per step (`:1496`, inside `decode_struct`, outside the layer loop).

RoPE is the **harder** of the two: even if you gave every lane its own `iter_num`, there is
still exactly one set of angles on the PE. A lane at position 12 and a lane at position 8
cannot both be served. Anyone costing out ragged batching (O1) from the `iter_num` analysis
alone will under-estimate it — per-lane RoPE state is a separate, larger change.

## Confidence / attribution

The RoPE finding and all line cites were read off `decode.csl` in-session. The correction to
the mixed-hit/miss conclusion is **Le's**, and Claude conceded it explicitly — authoritative.
The `min(L_match)` scheme is a **design proposal that follows from the verified mechanism**;
it has not been implemented or run, so treat the specific formula as proposed, not validated
`[unverified]`.

Promotion candidate (partial): the project facts belong here, but the reusable half —
*"before declaring a case impossible, check whether the impossibility came from an
implementation choice you assumed rather than from the hardware"* — is procedural. Here the
smuggled assumption was take-over-vs-ride-along.

## Pointers

- [[decode-lanes-must-be-equal-length]] — the 2026-07-25 note this **corrects**; its
  `iter_num` mechanism stands, its S3 config guidance does not.
- [[slot-reuses-bsz-batch-is-not-a-storage-axis]] — slot(S) vs batch(M) split.
- [[kv-cache-policy-tradeoffs]] — O1 (continuous batching), now with a bigger price tag.
- [[s6a-decode-kv-retain]] — `round_reset` / `rope_init_from_delta_p`, the existing
  take-over path.
