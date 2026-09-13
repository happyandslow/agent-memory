# Half the block area does not imply faster single-layer execution — 2026-09-13

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

When estimating the new LayoutC pipeline from its smaller PE footprint, keep
single-layer serial latency separate from whole-model pipeline throughput.
Real CS-3 tests of the current 128×80 A1 / 128×256 A2 / 128×160 A3 layout
versus pinned original 256×256 ATTN + 256×256 FFN measured:

- Prefill1280: 102,511 versus26,377 cycles (3.886×).
- Prefill5120: 104,330 versus28,000 cycles (3.726×).

These are medians of three independent run medians, batch1/BF16/one layer,
capacity8192, identical dense synthetic logical weights and inputs (seed910),
33 decode tokens with first4 timing samples excluded. Every output matched
its geometry-aware operation-order reference. Reserved compute area is
65,536 versus131,072 PEs; Head/Tail and inter-layer feedback are excluded.

The interval includes a common on-wafer START/all-row-completion boundary.
Its empty control costs8,231–8,232 cycles; no naive subtraction was applied
because completion can overlap computation. D2H happens after all timing.
Do not cite these numbers as pure arithmetic latency, five-layer feedback
cost, trained-model performance, or full-pipeline throughput. No bottleneck
was localized by this comparison alone.

[Report, precise scope, raw measurements and reproduction](/home/lexu/wse3-performance-model/docs/reports/2026-09-13-layoutC-single-layer-performance.md).
