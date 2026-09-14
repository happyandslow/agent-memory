# Which of two weeks' contested numbers survived: the ones with a control attached — 2026-09-14

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured
**Procedural — promotion candidate (see PLAYBOOK § promotion); proposed, not installed.**

## What happened / finding

Situation: you hold a number (a fabric constant, a per-PE budget, a stage cost,
a bug diagnosis) and are about to price a design or name a cause from it.
Across ~15 contested claims over 2026-09-07…14, exactly one property predicted
which survived: **whether the measurement had a control attached.**

Survived (all had one): root-off-midpoint control on the range test; vanilla
control on the KV column check; ATTN-only anchor cross-validating a mini compile
to +0.1 %; layer-count normalisation against a one-layer build; `cs_readelf`
verifying *structure* (both bodies live) not just a total; per-PE closure
(segments reconstruct the end-to-end interval to 0.03 %); a delay control that
must land in the right segment; contiguous-vs-scattered with only placement
varied; corrupted-input negative controls that must reject.

Retracted (none had one): FP re-association as a parity mechanism; the per-PE
MAC model as a time predictor (inverted the pacing stage); "fusion is
SRAM-ahead" from a derived parameter count; "K prefill never lands" from a
post-decode dump (a boundary stop showed it landed and was overwritten later);
an off-by-one read from a `[:plen]` slice too narrow to distinguish it from
"never written"; "13 cyc/word" measured on a receive-and-re-emit relay and read
as transport cost (real receive floor ~1.17 — an 11× error priced into two
sessions' designs); "scatter costs ~4× via hop count" despite a height ladder
already showing chain length barely matters; and "35,536 ≈ 256 × 139, a serial
chain" — **arithmetically self-consistent and wrong** (source: a tree).

Three sub-lessons the cases separate:
1. **Instrument property ≠ world property.** Isolate what the probe/testbed/
   guard/print-cap contributes before attributing its number to the thing
   measured (relay double-counting; a debug slice's display width read as its
   reach; a shared print budget hiding the rarer failure; a size guard that
   skips at the only geometry that matters).
2. **Consistency with itself is not a control.** A fit that fits is still a
   hypothesis; label it, then check the source before anyone builds on it.
3. **Carry a correct measurement's implication forward.** Before predicting,
   ask what existing measurements already say; two sessions had the ladder's
   −1.4 % in hand and still reached for a hop multiplier.
When a symptom is "X is wrong at the end", ask *when* it became wrong and build
the probe that answers that (boundary stops), not a wider dump of the end state.

## Implications / next actions

- [ ] **Promotion proposal for Le:** a skill triggered when about to cite,
  price from, or diagnose from a measured number — "what control is attached to
  this number? if none, it is a hypothesis: label it, and design the control
  (positive/negative/closure/structural) before building on it." Trigger
  vocabulary: "measured", "the constant is", "this explains", "it must be",
  "the numbers agree". Passes the altitude test (no file/bug named).

## Pointers

- Worked cases: `docs/reports/2026-09-13-layoutC-performance-conclusion.md`
  (correction banner, §5b, §7); `docs/reports/2026-09-14-tall-per-stage-timing.md`
  §4 (closure), 4b-wide-layer session report Rounds 128–174.
- Private Claude memory (this machine): `instrument-property-read-as-world-property.md`.
