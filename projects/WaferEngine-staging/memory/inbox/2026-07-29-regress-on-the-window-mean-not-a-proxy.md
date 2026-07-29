# A per-run average plotted against the wrong x-axis — 2026-07-29

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured   <!-- captured | drained -->
**Promotion:** procedural, cross-project — see § Implications. Candidate for a
measurement-methodology skill, not a WaferEngine topic.

## The situation this applies to

You have one aggregate number per run — average latency per token, average
throughput, average cost per item — and you want to know what it depends on. You
plot it against the obvious per-run quantity (how many tokens it generated, how
many items it processed, how long it ran) and get a beautiful straight line,
R² ≈ 0.998. The fit looks unimpeachable. It is off by a factor of two, and the
plot will not tell you.

The tell is somewhere else entirely: **the slope disagrees by ~2× with an
independent measurement of the same quantity**, and that disagreement gets
written down as "agrees in direction and order of magnitude."

## What happened / finding

Measuring decode cost on WSE-3: `device_steady_us_per_tok` is one number per
request, an **average over the request's timed window**. Regressed it against
generated-token count → `628.75 µs + 13.22 ns × x`, R² = 0.998, monotonic across
all 8 requests. Wrote it into three documents labelled as "per context token".

Wrong. The independent variable — KV context — **grows during the window** it is
averaged over, from `prompt + warmup` to `prompt + generated`. If the
instantaneous cost is `a + b·c`, the reported average is `a + b · mean_ctx`
where `mean_ctx = prompt + (warmup + generated)/2` — roughly **half** the
generated count. So the slope came out 2× low while the fit quality stayed
perfect, because halving the x-axis is a linear rescale and R² is invariant
under it.

Correct fit: `627.83 µs + 26.45 ns × context`, R² = 0.998 (unchanged).

Two consequences worth separating, because they are easy to conflate and differ
by 15%:
- cost of **one** item when the accumulated state is already N → `a + b·N`
- **average** cost per item of a run that processes N → `a + b·N/2`

**The error announced itself and the signal was ignored.** An independent sweep
on different hardware config had implied ≈22.5 ns/token for the same physical
quantity. 13.22 vs 22.5 is a factor of ~2 — exactly the error's magnitude — and
it was recorded as acceptable agreement. The corrected 26.45 agrees to within
15%, and *that* convergence is what makes the finding credible at all.

It was **plotting** the data that exposed it, not the table: drawing the axis
forced the question "what is x, actually?"

## Implications / next actions

- [ ] Two rules, both procedural and neither specific to this project:
      **(1)** when the measurement is an average over a window and the
      independent variable moves *during* that window, regress on the window's
      **mean**, never on an endpoint or a per-run proxy;
      **(2)** a factor-of-2 gap against an independent measurement of the same
      quantity is a **defect report**, not a rounding difference — investigate
      before writing "same order of magnitude".
- [ ] Corollary worth stating: **R² does not validate the choice of x.** A
      linear rescale of the x-axis leaves R² untouched, so a near-perfect fit is
      evidence of linearity and says nothing about whether you fitted the right
      variable.
- [ ] Third time this month a number reached a durable doc before its
      provenance was checked (see the two pointers below). The common shape is
      the same each time: a plausible number, no independent cross-check, and a
      discrepancy explained away rather than chased. Propose promoting the
      cross-check habit to a skill rather than logging a fourth instance.

## Pointers

- Corrected in `milestones/M2-tiering-cost-model.md` (§ Per-request breakdown,
  with a correction blockquote), `PROGRESS.md` (Checkpoint metrics + a Failed
  approaches entry), and `memory/topics/m2-s0-baseline-and-timer-provenance.md`.
- Sibling failure modes, same root shape:
  `inbox/2026-07-28-a-quoted-number-is-not-a-measured-number.md` (divisor came
  from prose, never a timer) and
  `inbox/2026-07-28-check-the-branch-tip-before-baselining.md`.
- Data: `we-m2bench/evidence/run{1,5}/timing.json`, 8 requests,
  `decode_device.tsc.per_round[]`.
