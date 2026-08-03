---
summary: Your "prove it changed nothing" gate fails, and the code is fine — the tolerance was calibrated on the wrong comparison — 2026-07-30
tags: [WaferEngine-staging, drained-inbox, 2026-07-30]
---

# Your "prove it changed nothing" gate fails, and the code is fine — the tolerance was calibrated on the wrong comparison — 2026-07-30

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-07-30

Source: `memory/inbox/2026-07-30-a-regression-gate-that-cannot-pass-by-construction.md`

---
date: 2026-07-30
project: WaferEngine-staging
tags: [methodology, measurement, regression-gate, reproducibility, m2, procedural]
---

# Your "prove it changed nothing" gate fails, and the code is fine — the tolerance was calibrated on the wrong comparison — 2026-07-30

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You changed a kernel in a way that is supposed to be **inert** — a knob added
with its default set to today's behaviour — and you have a regression gate that
says *"no device-side timing field may move by more than X%"*, where X came from
running the baseline twice and observing its jitter.

The output is bit-identical. The gate fails anyway, on a handful of fields, by
a hair. You start hunting for the semantic change that is not there.

**There is no bug. The gate cannot pass, by construction, and it never could.**

## Why

The tolerance was measured **run-to-run on one binary**. You are applying it
**binary-to-binary**. Those are different quantities:

- *Run-to-run, same binary* is hardware + scheduling noise. Here it is tiny:
  one pair of runs of the same artifact agreed to **±1 cycle/token (−0.0001%)**.
- *Binary-to-binary* includes everything the compiler did differently —
  instruction scheduling, code layout, branch placement. Requiring that to be
  zero is requiring the compiler to emit identical code, which is not what
  "inert" means and not something you asked for.

Measured on the actual change (force-decode ported into `pdSeparate`, F defaulted
to 1 so nothing branches differently): a **systematic −0.044%/token**, all 8
rounds, band width 0.005%, −234 to −253 cycles/token. Note the sign — the ported
binary is *faster* despite adding two comparisons per step. That is the tell that
it is layout, not semantics.

For scale, two *same-binary* pairs on this project bracket the noise: −0.0001%
(±1 cycle/token) and **+0.0219%** (a systematic whole-run offset, all rounds same
sign). So whole-run offsets of ~0.02% exist too — a second reason a 0.05% gate is
not measuring what its name suggests.

## What to use instead

Split the claim in two, because "inert" is two different things:

1. **Semantics unchanged** — a whole-run content hash over the outputs
   (`trace_sha256` here), bit-exact. This is the real gate and it is not
   negotiable.
2. **No new hazard** — placement/routing unchanged: compare the artifact's
   `colors.json`, the port map, and the router-warning set against the baseline.
   Cheap, and it catches the class of change that silently re-routes buses.

Then keep a timing check, but set its threshold by **what would change a
conclusion** — order 1% for a cost model — and *report* the systematic shift
rather than gating on it.

## A second-order trap in the same area

The gate script's own device/host classifier was wrong the first time: it treated
any field under `.tsc.` as a device reading, but the per-round records interleave
host wall-clock there (`kv_handoff_s`, `recv_s`, `decode_wall_s` — the first of
those moves ±5% run to run). That script **failed the baseline's own two
bit-identical runs**.

⇒ **Before trusting an instrument, run it on a pair you already know agrees.**
Doing that reproduced the project's documented ±0.0268% jitter figure
independently, which is also how you know the classifier is right afterwards.

## Implications / next actions

- [ ] **Promotion candidate — this is procedural, not a fact about this project.**
      It is a method for a class of situations ("a tolerance quoted for one
      comparison is being reused for a different comparison"), it has already
      recurred here twice — the same project previously mis-set this gate at
      ±0.02%, a figure that was the *anchor* precision rather than the whole-file
      spread — and it can be stated without naming a file or a commit.
- [ ] When the maintain pass runs, consider folding the "test the instrument on a
      known-agreeing pair" half into the existing negative-control note rather
      than duplicating it.

## Pointers

- `milestones/M2-tiering-cost-model.md` § Verification log, 2026-07-30 S2 entry.
- `PROGRESS.md` Failed approaches, 2026-07-30 — the third of the three entries.
- Prior, related but distinct: [[2026-07-28-prove-same-source-before-comparing-timings]]
  (establish *same source* before comparing timings — this note is the next
  question: what tolerance is even meaningful once the sources differ).
- Prior mis-calibration of the same gate: `M2-timer-provenance.md` §9.2b.
