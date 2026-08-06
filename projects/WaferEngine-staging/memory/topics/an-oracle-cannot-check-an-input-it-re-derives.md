---
summary: A device-vs-oracle regression gate reports PASS on a provably-wrong run because both sides re-derived the same setup quantity from one shared buggy rule — an oracle is independent only in what it COMPUTES, never in what it is GIVEN; plus the vacuous-PASS sibling (a gate that compared nothing).
tags: [WaferEngine-staging, methodology, verification, oracle, regression-gate, procedural, drained-inbox, 2026-08-04]
---

# Your device-vs-oracle check says PASS and the run is provably wrong — the oracle re-derived the same input

This topic was created by the 2026-08-06 maintain pass from a dated inbox capture
(`memory/inbox/2026-08-04-an-oracle-cannot-check-an-input-it-re-derives.md`, author claude). Keep it
as the durable, topic-scoped home; the capture is marked drained. **Procedural / promotion
candidate** — a method for a class of verification situations, not a WaferEngine fact.

## The situation this applies to

You verify a kernel by comparing its output against a numpy "oracle" and gating on the difference.
Both sides need a **setup quantity** that is not itself the thing under test — a starting offset,
sequence position, length, or schedule. The host computes it and sends it to the device; the oracle
computes it **again**, with its own copy of the same rule, because that felt like an independent
check.

- **Symptom:** the gate reports PASS on a run you can show, on paper, is wrong.
- **Sibling symptom, same family:** the gate reports PASS having compared **nothing at all**.

## The cause

**An oracle is independent only in the quantity it COMPUTES, never in the quantity it is GIVEN.**
When the setup quantity is derived on both sides from one shared (buggy) rule, the two sides make
the *same* mistake and their outputs agree. The comparison then answers a narrower question than you
think — "given this setup, is the arithmetic right?" — and a faithful execution of a wrong
instruction passes that question.

**Measured instance (M1-S2, 2026-08-04):** the decode-start column was re-derived in **three**
places (host round loop, oracle, metrics pass), each keeping its own scalar high-water. With two
request slots interleaving, the correct resume for round 2 was column 16; the shared rule said 24.
The device resumed at 24 (reading a never-written zero column), the oracle replayed from 24, they
agreed to `max_abs = 3.27e-4` against a `0.05` threshold, and the run printed `SUMMARY: PASS`.

**The vacuous sibling:** a round with no comparable data hit a `continue` that never touched the
running `all_ok`, so a run where *every* round was skipped still printed PASS. In the same session
the **rank-based check labelled "diagnostic only" correctly reported FAIL** while the designated
primary gate said PASS.

## What to do instead

1. **Execute the setup rule once and RECORD it.** Consumers read the recording; delete the
   parameters they would need to re-derive it (here `prefill_lens`, `retained_lens` left the
   oracle's signature entirely). Fewer copies, no drift, no spurious FAILs when copies disagree
   while the device is fine.
2. **Do not claim this fixes detection.** Recording the input does not let the comparison audit it —
   the input is still given to both sides. Be explicit in the docstring: "the numerics are correct
   **given** this schedule."
3. **Verify the setup with a different instrument.** What actually caught the bug: (a) a **paper
   derivation** of the expected value from first principles; (b) an **A/B run** of old vs new code
   requiring the outputs to *differ* — and, crucially, the *other* rounds to be **identical**, which
   localises the divergence and rules out an unrelated cause; (c) **structural guards** that refuse
   impossible states (a store API that refuses to resume a slot never written, and refuses two
   active slots at different lengths).
4. **Make every gate distinguish PASS / FAIL / VACUOUS**, and print how many units were actually
   compared. Count units that can be *judged*, not units that have data — here the fresh rounds only
   establish the noise floor and are never judged, so counting them would have hidden "zero retain
   rounds compared".

## Why it is worth remembering

The failure is silent in the worst way: nothing crashes, nothing goes out of range, the gate is
green, and the number it prints looks like the noise floor. It cost a full verification cycle and
was only noticed because a negative control was run for an unrelated reason. Same root as the
earlier "vacuous KV-SEED PASS" (a check handed an empty slice printed PASS having compared zero
bytes) — two instances a milestone apart, in two different checkers, of one rule: **a checker must
refuse rather than pass, and "PASS" must never be printable by a path that compared nothing or that
compared two copies of the same mistake.**

## Related

- [[a-regression-gate-that-cannot-pass-by-construction]] — the mirror-image failure (a gate that
  *fails* while the code is fine, because its tolerance was calibrated on the wrong comparison).
- Work repo: `milestones/M1-intra-pe-reuse.md` § Verification log 2026-08-04 (full evidence);
  `PROGRESS.md` Failed approaches — two 2026-08-04 entries.
