# Decode's per-forward lanes must be equal-length: `iter_num` is both a DSD length AND the packed score-buffer stride

Date: 2026-07-25 · Repo: `WaferEngine-staging` · Branch base: `lexu/staging/kv-feature` (M1-S1)

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are giving the standalone decode kernel (`models/qwen3_1p7b-decode`) a per-request
**slot** dimension (M1: multi-request KV coexistence, per-slot `retained_len`, hit/miss per
request). The natural next thought is "so now two coexisting requests can have different KV
lengths" — and within one round they can. The trap: **inside a single forward, all active
lanes must still have the same occupancy**, and nothing in the kernel will tell you when you
break it. The symptom is not a hang or a crash — it is **wrong values** out of attention,
because score-buffer lane base addresses are computed from the wrong stride.

Note the distinction that makes this easy to miss: slot **capacity** is fixed
(`kv_len_per_pe`) and equal by construction; the constrained quantity is **occupancy** —
how many KV positions a lane has actually filled. Attention only reads `[0, iter_num)`.

## Why: one scalar is doing two jobs

`iter_num` is a **scalar**, not `[bsz]` (`decode.csl:167 var iter_num: i16 = 0;`, reloaded per
layer from the bank in `set_layer` `:609`). Every active lane in this forward shares it, and it
is used as two different things at once:

- **a length** — K-matrix DSD extent in `score_matvec_mult` (`:1203/1216`), softmax pack
  lengths (`:1240/1256/1283`), the write column in `process_kv` (`:1164/1177`, `iter_num += 1`
  at `:1183`);
- **an inter-lane stride** — the score buffer is packed *by effective length*, not by
  capacity: `score_f32_dsd = packed [bsz*G*iter_num] view` (`:801`), and lane `m`'s block base
  is computed as `m * G * iter_num` (`:1231`); score·V walks score slots at the same stride
  (`:1344`).

So with lane A at 10 positions and lane B at 6, B's true block starts at `10*G` but the code
addresses it at `iter_num*G` — **misaligned reads, silently**. Worse, the batched softmax
operators (`@map(exp_map,…)` `:1283`, the casts `:1256/1306`, the alpha scale `:1240`) treat
`bsz*G*iter_num` as **one contiguous span**, which already presupposes every lane occupies the
same width. The buffers themselves are *allocated* by capacity (`:793/798`, tail zeroed) — it
is the *packing* that assumes uniformity, and that mismatch between allocation scale and
packing scale is exactly why unequal occupancy corrupts quietly rather than trapping.

## The real point: today the invariant is free — after M1 it is discipline-only

Right now equal length is **structurally impossible to violate**, so no one has had to think
about it:

- the KV meta tile carries **one** `plen` / `decode_len` / `retained_len` per round
  (`decode.csl:1580-1583`), so every lane gets the same values;
- host slices KV for all lanes with the same `plen` (`launch.py:2485-2487`);
- all lanes advance together (`iter_num += 1`, scalar);
- EOS only makes a finished lane emit pad (`ht_tail.csl:1123`) — it does **not** stop that
  lane's length from advancing.

M1 dismantles every one of those props: **S1** puts a per-lane slot vector in the meta tile,
**S2** makes `retained_len` per-slot, **S3** decides hit/miss per request. After that,
equal-length survives only as a convention the host must uphold — enforced by nobody, and
violated without a diagnostic. That transition ("an invariant that costs nothing today becomes
a maintenance obligation the moment you add the dimension that could break it") is the part
worth remembering, and it is the same family as the S6a lesson that a new per-request
dimension quietly lands on several places that hardcoded the old default.

## Practical consequence for M1-S3 config design

**A batch that mixes hit and miss lanes is a ragged batch**, because a hit lane starts at
`L_match` occupancy and a miss lane starts at 0 (or at whatever force-decode has produced).
So S3's hit/miss experiments must either use `bsz=1`, or make **all lanes take the same
hit/miss path**. Mixed-hit batches belong to continuous batching (open question O1), not M1.

## What supporting ragged batches would actually cost

If ragged is ever taken on: `iter_num` scalar → `[M]` array; `process_kv` per-lane write
column; score laid out by **capacity** stride (`kv_len_per_pe`) instead of packed by effective
length; softmax either split per lane or given `-inf` padding. The consequential part is not
the edit — it is that score/softmax compute goes from `O(effective length)` to
`O(capacity)`, so fixed-slot internal fragmentation starts **wasting compute, not just SRAM**.
That is a new argument against fixed slots that the SRAM-only framing in
[[m1-kv-memory-layout-contiguous-vs-paging]] does not capture.

One piece of good news found while checking: the kv-head **collective is already
capacity-length** (`decode.csl:1234`, `comm_pe.csl:931`) — which is why `:1192` zero-pads the
tail so the reduce adds zeros. So the communication side needs no change; only the local
packing does.

## Confidence / attribution

Line cites read off `decode.csl` in-session on the M1-S1 branch base. The mechanism (scalar
used as length + stride, packed-not-capacity score layout) is **code-verified**. The
*recommendation* — keep equal-length as an explicit M1 invariant, write it into
`milestones/M1-intra-pe-reuse.md` § S0.2 + the tradeoff register, route ragged to O1 — was
proposed at the end of the session and is **not yet confirmed by Le** `[unverified]`. The
ragged-support cost estimate is projected from the code structure, **not measured**.

Partial promotion candidate: the project-specific layout facts belong here, but the reusable
half — *"before adding a per-request dimension, find the invariants that the old uniformity was
silently paying for, and decide who enforces them afterwards"* — is procedural and would fit
alongside the existing S6a "new dimension hits hardcoded old defaults" lesson.

## Pointers

- [[m1-kv-memory-layout-contiguous-vs-paging]] — the contiguous-slot decision and the
  addressing seam this invariant sits underneath.
- [[slot-reuses-bsz-batch-is-not-a-storage-axis]] — slot(S) vs batch(M) split; this note is
  the constraint on the M side that survives the split.
- [[kv-cache-policy-tradeoffs]] — O1 (continuous batching) is where ragged batches live.
- [[s6a-decode-kv-retain]] — `round_reset` / retain, source of the single-`eff_len` shortcut.
