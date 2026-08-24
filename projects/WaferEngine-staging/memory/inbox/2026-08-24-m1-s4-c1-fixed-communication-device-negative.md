# M1-S4 C1 fixed-communication device negative — 2026-08-24

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

- When a future M1/S4 analysis asks whether skipping one lane's local decode
  work can speed up a fixed-extent `bsz=2` full-model round, use the
  construction-matched manual C1 matrix rather than the earlier automatic
  Experiment-A K0 anchor. The two constructions differ by 12.2363% in mean raw
  cycles and cannot be mixed in a speedup ratio.
- The real-CS-3 matrix fixed `S=256`, `N=1024`, `F=769`, `G=255`, Qwen3-1.7B,
  `bsz=SLOT_COUNT=2`, and varied lane-1 rejoin delta
  `K in {0,256,512,768}`. All 20 serial attempts passed strict replay; raw TSC
  cycles are authoritative.
- Matched K0 mean was 288953017.6 cycles. Mean speedup for K=256/512/768 was
  respectively -0.0328%, -0.0924%, and -0.0297%. K=768 avoided 767 timed
  lane-steps, 37.49% of the `2 x 1023` timed lane-step rectangle, but did not
  reduce device critical path. The means were non-monotonic, so a linear
  active-lane saving fit is unsupported and no break-even was observed.
- This is a negative result for the implemented C1-M predicate surface with
  fixed communication, not for C2 independent progress, communication
  compaction, EOS masking, energy, fairness, or continuous batching. Those
  remain unmeasured and must not inherit a positive speedup from C1-M.
- Collector replay must count distinct job IDs, not raw job-ID occurrences. A
  successful run emitted the same ID in both normal and DiskPressure events;
  treating occurrences as jobs caused a false 19/20 rejection. The corrected
  collector preserves first-seen order and still rejects two different IDs.

## Implications / next actions

- [ ] Replay realistic traces with C1-M critical-path gain set to zero (or a
      clearly labelled sub-0.1% sensitivity), while preserving operation-work
      reduction separately from throughput.
- [ ] Do not launch the conditional 85-run position matrix unless the trace
      model shows that a position-dependent upper bound could change the
      implementation decision.
- [ ] Keep C2, active-lane communication compaction, EOS masking, and SRAM
      accounting as separately reviewed mechanisms/routes.

## Pointers

- Branch `lexu/staging/m1-ragged-execution-study`, branch point `77d6d407`
- `docs/analysis/m1-s4-c1-s256-manual-comparison-provenance.md`
- `docs/analysis/m1-s4-c1-workload-step-review.md`
- `cs3-c1-s256-manual-comparison/run-20260824T0340Z/`
- `tools/m1_s4/collect_c1_s256_manual_comparison.py`
- `docs/slides/2026-08-24-m1-s4-ragged-c1/m1-s4-ragged-c1-weekly-insert-2026-08-24.pptx`
- `docs/slides/2026-08-24-m1-s4-ragged-c1/deck.json`
- ContextBase: <https://context.ed-aisys.com/doc/2026-08-23-study-review-m1-s4-c1-and-workload-shape-selW5g7f72>
