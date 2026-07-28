# A number that has been quoted often enough starts to read as measured — check its denominator before building a decision rule on it

Date: 2026-07-28 · Repo: `WaferEngine-staging` · M2 kickoff (tiering cost model)

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

A figure has appeared in the durable docs long enough that every session repeats it, and a
decision rule now depends on it. Two independent instances surfaced in one session, both
load-bearing, both wrong, and both caught only by opening the source of the number rather than
the number itself.

## Instance 1 — the divisor came from prose, not a timer

`ROADMAP.md`, `GOALS.md §8`, `PROGRESS.md`, and `topics/kv-cache-policy-tradeoffs.md` all carried
**"host KV transport as-built ~15 MB/s"**, and the entire `R*` breakeven argument
(`R* = Δ·BW/B_tok`) used it as `BW`. Tracing it back:

- The value is `29.4 MB ÷ "~2 s"`. The numerator is real (derived from a wavelet count on a
  device run). **The denominator is a STATUS.md prose phrase — "a few seconds".** No timer.
- The topic file hedges it in its own text as *"measured-ish"*, and that hedge was silently
  dropped by every doc that cited it.
- It also describes the **wrong branch**: it is the staging single-stream colmux path, which
  additionally zero-extends each fp16 into a u32 on ingress and wastes half the wire.

The pr14 line has been 4-stream varlen for some time, and its `per_req_kv_egress_ms` **is** true
wire time (a blocking `task_wait` after four `nonblock` receives). That gives **~1.3–1.5 GB/s —
about 90× higher.** Consequences: `R*` moves from a degenerate ~0.036 ("always keep KV in place",
no boundary at all) to **≈3**, a real boundary with requests on both sides; and M4's completion
gate ("beat as-built ~15 MB/s") was **already cleared by ~90× before it was written**.

*Note the failure is asymmetric in danger: a degenerate `R*` doesn't look broken. It looks like a
strong conclusion.*

## Instance 2 — the span was wider than the quantity being computed

Same session, from `pr14`'s recorded `timing.json`: dividing `decode_phase_wall_s = 293.694` by
10,571 generated tokens gives 27.8 ms/token, ~58× the known device rate — apparently "decode is
98% host overhead", which would have invalidated the entire on-wafer optimization thesis.

Wrong. `decode_phase_wall_s` **brackets `compile_s` (94.5 s), `load_s` (105.3 s) and eight KV
handoffs**. The same file already carries the correct steady-state figures: device **655 µs/token**,
host-observed **740 µs/token**, `host_device_ratio = 1.129`. Host adds ~12%.

Caught by reading the rest of the JSON before writing the alarm into a durable doc. One file read.

## What to do instead

- Before using an inherited number as a model input, **open the artifact that produced it** and
  state what its denominator spans. If you cannot, label it derived, not measured.
- Carry the original author's hedge forward. "measured-ish" is information; dropping it during a
  citation is how a guess becomes a constant.
- Record, per parameter, whether it is a **physical floor** or an **as-built artifact** — otherwise
  a cost model just re-derives "the current implementation has bugs" for every option.
- For any wall-clock, name the start and end line. `*_phase_wall_s`-style names almost always
  include setup.

## Confidence / attribution

Both corrections read directly off `pr14-real`/`pr14-head` `request_config/mtbench8/timing.json`
and the agent-memory topic text in-session. The replacement ~1.3–1.5 GB/s is itself **derived** —
it assumes the egress payload is one 256-token chunk (29–34 MB); computing the payload from
`launch_prefill.py`'s `per_region_n` is an explicit M2-S0 task `[unverified]`.

**Promotion candidate (procedural).** Stated without naming this project: *a number repeated across
enough documents acquires the appearance of measurement; before it becomes a decision threshold,
recover its denominator and the span that denominator covers — and preserve any hedge the original
author attached to it.*

## Pointers

- `PROGRESS.md` Failed approaches (both entries, 2026-07-28); `GOALS.md §3` `R*` corrections.
- `milestones/M2-tiering-cost-model.md` § "Measured anchors available at kickoff".
- Related: [[kv-cache-policy-tradeoffs]] (now carries a correction banner),
  [[check-the-branch-tip-before-baselining]], [[h2d-host-device-bandwidth]] (has its own set of
  known-wrong host-wall bandwidth figures, same root cause: timing a call that returns at queue
  submission).
