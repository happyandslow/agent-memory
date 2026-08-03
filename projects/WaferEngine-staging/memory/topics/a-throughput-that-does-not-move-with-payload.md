---
summary: A GB/s that does not move when you change the payload — 2026-07-30
tags: [WaferEngine-staging, drained-inbox, 2026-07-30]
---

# A GB/s that does not move when you change the payload — 2026-07-30

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-07-30

Source: `memory/inbox/2026-07-30-a-throughput-that-does-not-move-with-payload.md`

# A GB/s that does not move when you change the payload — 2026-07-30

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You have a measured GB/s for some link — you divided a real payload by a real
timer — and you are now using it to price "this lane has to move N bytes."
The arithmetic looks unimpeachable: both numbers were measured.

It can still be structurally wrong, and the tell is cheap to get: **change the
payload by a known amount and see whether the time moves.** Twice today, on two
different links, it did not.

## Instance 1 — the H2D KV ingress (M2-S2 Step 0b, real WSE-3, pdSeparate)

Widening the KV metadata tile from 2 to 4 u32 slots is a pure payload change,
everything else fixed:

| | width 2 | width 4 | Δ |
|---|---|---|---|
| per-band payload (derived from code) | 8,912,896 B | 9,437,184 B | **+5.882%** (exactly 2/34 = 1/17) |
| per-band ingress span (device TSC) | 46,145.392 µs | 46,149.306 µs | **+0.0085%** |

524,288 extra bytes cost **3.914 µs** ⇒ **marginal rate 134 GB/s**. The H2D
physical ceiling is 11.43 GB/s, so the margin is **12× impossible**, and 655×
the average rate (0.2045 GB/s per band).

The bytes really crossed: the `metablk` DSD extent is a compile-time 1023 u32
per row, so short-feeding starves the receiver and hangs. The run completed and
`trace_sha256` was bit-identical.

⇒ **`0.7726 GB/s` is not a rate.** It is `payload ÷ a span that is almost
entirely fixed cost`. Pricing the reload lane as `bytes ÷ 0.7726 GB/s` — which
is what [[m2-s1-measurement-lenses]] does, including the `L = 8192 → 1390 ms`
figure — overestimates structurally as the payload grows.

Shape of the fixed cost, from the same run: each of 256 rows costs 180,271 ns
and carries 36,864 B, made of 1 metablk op + 1 KV op + 1 switch advance (this
workload has `n_segs_rt = D_kv × plen = 1`, i.e. one KV segment per row). The KV
op runs at ~22 ns/wavelet; the marginal metadata wavelet at ~0.03 ns. **Same PE,
same fabric, 700× apart** — which is the real open question, and it is *not*
answered here.

## Instance 2 — the on-chip prefill→decode move (M3 design session, same day)

`1.803 GB/s` has been quoted as the on-chip transfer rate. Decomposed:
16 MiB / 9.304 ms / 262,144 PEs, with the per-hop payload read out of the code
as `kv_tile_size = kv_dim_per_pe × reduce_len` = **16 bytes**, over 512 rows ×
4 phases = **2,048 serial store-and-forward steps**.

⇒ **4.54 µs per step to move 16 bytes. The wire is idle 99.91% of the time.**

So it is a per-step-overhead number, not a bandwidth number. Coalescing a whole
PE's KV into one step (3 KB at L = 8192) is **196×** on that term alone. The
three plausible movement models give **1.04 ms / 6.9 ms / 2308 ms** at L = 8192
— a **2200× span that brackets every competing option**, so T1 cannot be ranked
until that span narrows. That, not building a park band, is the first M3
experiment.

## The method (promotion candidate — procedural, not project-specific)

This is a test, not a fact about these two links:

1. Never accept `payload ÷ time` as a rate on its own.
2. Perturb the payload by a known amount with everything else fixed; take
   **Δbytes / Δtime**.
3. Compare the marginal rate to the **physical ceiling**. Above the ceiling ⇒
   the measured time is fixed cost and the "rate" must not be extrapolated.
4. Confirm the bytes actually crossed (here: a comptime DSD extent that would
   hang on a short feed), so "no time change" cannot be read as "no transfer".

It composes with, but is distinct from, [[a-quoted-number-is-not-a-measured-number]]
— there the divisor came from prose; here both numbers were measured honestly
and the *ratio* still does not mean what it looks like.

## Implications / next actions

- [ ] Reprice every "reload from host" figure at the margin, not at the average;
      the `L = 8192 → 1390 ms` anchor is a structural overestimate of unknown size.
- [ ] Explain the 700× per-op asymmetry. Needs an experiment that varies **KV**
      bytes rather than metadata bytes: a `plen_per_pe > 1` prompt, or the
      existing `KV_DSD_SEG_MAX` knob which forces segmentation at constant
      payload. Belongs to M2-S3 / M4, captured here rather than chased.
- [ ] The repo has **no on-chip PE→PE bandwidth benchmark**. `kv_switch_gather`
      terminates in host streams both directions — it is a host↔device LVDS
      benchmark, and its on-chip part is only the funnel feeding the LVDS port.

## Pointers

- Corrects a live number in [[m2-s1-measurement-lenses]] (H2D 0.7726 GB/s) and
  the T1 pricing assumption in [[kv-cache-policy-tradeoffs]].
- Session docs: `milestones/M2-tiering-cost-model.md`,
  `milestones/M3-idle-pe-tier.md` §3.
- Related: [[prefill-decode-transfer-bandwidth]], [[h2d-host-device-bandwidth]].
