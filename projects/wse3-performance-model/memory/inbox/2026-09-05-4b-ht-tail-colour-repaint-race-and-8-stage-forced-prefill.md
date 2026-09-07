**Status:** drained   <!-- drained 2026-09-07 by daily maintain pass -->

# 4B HT tail has a latent colour-repaint race that any faster hidden-state cadence triggers; 8-stage forced prefill measured 7,373 / 6,326 tok/s — 2026-09-05

**Project:** wse3-performance-model
**Author:** claude (session 4b-wide-layer; hunt by subagent 4b-thin-stage-forced)
**Status:** captured

## Situation

You are making the Qwen3-4B decode pipeline deliver hidden states to the
HT tail faster than autoregressive decode does (forced prefill, pair
scheduling, thin stages, batching across rows), or you see corrupt top-k
records that are deterministic and alternate between two frozen values.

## Gotcha (measured on CS-3)

The tail's **top-k X-merge repaints the shared reduce/broadcast colours
1–5 to X mode on the root row** and assumes the *next* step's Y-phase
logits-reduce traffic cannot reach a root-row router during that window.
That holds when successive hidden states are ≥ ~150K cycles apart
(autoregressive decode, 4-stage forced prefill) and breaks when they
arrive ≈ 12K cycles apart (two tokens per row): misrouted Y partials enter
the X-merge → top-k arg words carrying bf16 value halves, saturated fake
logits, a frozen 2-cycle of records, and a deadlock at TOP_K 20 / 8K.
The compute blocks were correct throughout.

**Fix** ("ysafe" Y-phase admission gate in `ht_tail.csl`): after restoring
Y routes, each root-row PE sends one wavelet down its column on the
then-idle broadcast colour; non-root PEs drain it before the next step's
tail work; per-column FIFO with the sumsq broadcast keeps streams aligned;
emit/drain counts balance per round including early stop. Zero measurable
cost. Patch: `demo/qwen3-4b-thin-stage/step1b-role-split.patch`; hunt:
`step1b-status.md`.

**Why the simulator never showed it:** local sims compile with SDK 2.10,
the appliance with 1.13.2, and the sim's 6-column tail X-merge fits inside
the sim's hidden-state gap — five clean sim geometries were not evidence
of device correctness. Also: a DSD copy is ≈ 4 % faster than the 1.13.2
memcpy lowering (kept as idiom).

## Numbers (750 MHz, byte-identical records)

- 4 stages (rows): 5,006 tok/s @2K, 4,507 @8K (Round 37).
- 8 stages (ATTN and FFN independent, two tokens per row): **7,373 @2K
  (101,723 cyc/tok), 6,326 @8K (118,550)** — 1.47× / 1.40× the 4-stage
  rate = T_row / T_attn, 6.6× serial decode; measured / predicted 1.044 /
  1.024, i.e. no pipelining penalty. wsjobs lhgcurbqytb7crgetkhbwk,
  dpgl8fsv9fmdhutvkbqp92.

## Pointers

- Report Rounds 37–39: `docs/reports/2026-09-04-4b-wide-layer-session-report.md`
- Related: `2026-09-04-4b-block-times-vs-batch-and-thin-stage-sram-fit.md`

## Production forced path (2026-09-05, later) — gated at the same rates

Tail computes the logits flow once per round (final step only), per step
it only drains the hidden state; head feed sharded by band column (128 B/PE
at a 4,096 budget) via two static ping-pong CE-relay chains. Device: 2K
7,377 tok/s, 8K 6,326 — equal to the verify build (< 0.03 %), so the tail
was not binding at 8 stages; the skip matters for thin stages (14–20K
cycle periods). wsjobs 3ef5h5eql38sxxfe2zazre, krjgzzijgtatakhqm9v5gn,
vdexixxz6bdsvfmvequom3, u2yb3psg6yfakcqmycywjb.

Two more device-only gotchas: (1) a colour passed as a raw int leaves the
router entry disabled — use registered Color objects with host-painted
routes; one wavelet on such a colour stalls everything silently; (2)
per-window runtime colour repaints "proven race-free by causality" hang at
device scale (margin = one hop vs gather variance over 256 rows) — use
static relays instead. Write-up: `demo/qwen3-4b-thin-stage/production-forced-README.md`.
