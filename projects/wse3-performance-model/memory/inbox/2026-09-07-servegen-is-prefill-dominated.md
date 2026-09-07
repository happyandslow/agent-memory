# ServeGen conversations are prefill-dominated, the opposite of the agentic trace — 2026-09-07

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## The situation this applies to

You are deciding what an on-chip KV store is *for* — serving one request with a
longer context, or keeping many requests' KV so their prefill is not recomputed
— and you want to know which way a real multi-tenant reasoning workload
pushes. Two traces are available and they disagree, so quoting either one alone
will mislead.

## Finding — on the same turns, ServeGen spends 4× more tokens on prefill than on decode

Computed from the released per-turn counts (`turn_metrics.csv`), so both
quantities come from the **same population** — the published tables had quoted
incremental prefill per turn from the conversations set against output per
request from the model-level release, which is not a like-for-like comparison.

| turns ≥ 1 (n = 4,104) | p25 | p50 | p90 | p99 | mean | total |
|---|--:|--:|--:|--:|--:|--:|
| incremental prefill | 320 | **2,107** | 9,499 | 43,973 | 4,509 | **18.51M** |
| decode (output) | 539 | **1,003** | 2,104 | 3,933 | 1,158 | **4.75M** |

- **By tokens the workload is prefill-dominated: 3.9 : 1 on turns ≥ 1 (80/20),
  4.8 : 1 across all turns.**
- **Per turn the two are much closer** — median ratio 2.1×, prefill exceeds
  decode on 67% of turns. The gap between "2.1× at the median" and "3.9× in
  total" is the tail: incremental prefill's p99 is 43,973 against decode's
  3,933, so a minority of turns carry the imbalance.

## Why it is the opposite of the agentic trace, which is the useful part

ServeGen conversations **re-enter their own output** — 83.4% of turn pairs grow
by at least the previous output, reasoning included. The Claude Code agentic
trace strips extended thinking, so only ~5% of decoded tokens re-enter later
context, and once aggregated that trace is decode-heavy. **The re-entry policy
of the harness, not the model, decides which side dominates.** Any claim of the
form "this workload is decode-heavy / prefill-heavy" is really a claim about
the harness.

## Implication for the KV-store question

A workload whose tokens are 80% incremental prefill is one where **not
recomputing matters more than decoding faster**. That is evidence for the
"many requests cached" case rather than the "one request longer" case — and it
is also the case where a fast decoder-as-prefiller is doing the bulk of the
work rather than the tail.

## Caveat

ServeGen carries no harness information, so incremental prefill here is the
**verbatim-history upper bound**; a harness that trims or summarises sends
less. The two traces bracket the real answer rather than settling it.

## Pointers

- `analyses/2026-09-05-servegen-trace-study/` — `results/turn_metrics.csv`,
  generator `05_incr_vs_decode.py`, figure `figures/incremental_vs_decode.png`
- `docs/analysis/2026-09-05-servegen-reasoning-workload-first-pass.md`
- `docs/reports/2026-09-04-4b-wide-layer-session-report.md` Rounds 107, 121
