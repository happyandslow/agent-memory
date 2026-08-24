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

- Remote branch `lexu/staging/m1-ragged-execution-study`, based on
  `77d6d407328f46314c90238d799f9ed5402d55b6`; C1-M implementation commit
  `4a4e6c3d11b8b77b835446cde507351141f95f6c`; study/evidence tip
  `a24beb4c6c3dcb4595dfd940fe5b8672ae9e1048` (verified equal to the GitHub
  branch ref on 2026-08-24)
- GitHub branch: <https://github.com/happyandslow/WaferEngine/tree/lexu/staging/m1-ragged-execution-study>
- `docs/analysis/m1-s4-c1-s256-manual-comparison-provenance.md`
- `docs/analysis/m1-s4-c1-workload-step-review.md`
- `cs3-c1-s256-manual-comparison/run-20260824T0340Z/`
- `tools/m1_s4/collect_c1_s256_manual_comparison.py`
- Canonical standalone insert: `projects/WaferEngine-staging/meetings/2026-08-24-m1-s4-ragged-c1.pptx`
- Canonical editable source: `projects/WaferEngine-staging/meetings/2026-08-24-m1-s4-ragged-c1-src/`
- Appended weekly deck: `projects/WaferEngine-staging/meetings/2026-08-24.pptx`, slides 9–12
- ContextBase: <https://context.ed-aisys.com/doc/2026-08-23-study-review-m1-s4-c1-and-workload-shape-selW5g7f72>
