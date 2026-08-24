---
summary: M1-S4 C1 fixed-communication ragged-prefix benchmark semantics, seed boundary, workload projection, and real-CS-3 negative timing result.
tags: [waferengine-staging, m1, s4, c1, ragged, prefix-reuse, fixed-communication, cs3, workload]
---

# M1-S4 C1 ragged fixed-communication benchmark

## Updates — 2026-08-24

Drained four 2026-08-23..24 M1-S4/C1 captures into this topic.

- C1-M covers equal-prompt, P-aligned prefix hits that differ by lane: one global decode/RoPE position starts at `S = min(R_i)`, and lane `i` rejoins after token-step delta `R_i - S`. It does not need a per-lane RoPE cursor, but it also does not compact communication; collectives/transfers and many maps keep fixed `bsz * width` extent.
- The device-KV seed boundary is a benchmark construction obligation. `KVStore.truncate()` and `round_reset()` change host logical/cursor state but do not clear resident `XKCache_tile`/`XVCache_tile` bytes. A positive C1 benchmark may preserve a longer lane's already-seeded `[S, R_i)` device bytes by suppressing `process_kv` writes until rejoin, but only if a prior completed same-slot seed physically wrote the exact tokens through `R_i`. Positive C1 also requires `KV_TRANSFER=1` so rejoin metadata is installed fail-closed.
- Host work is larger than the four-byte lower-bound device threshold state. Correct production C1 needs per-lane retained/rejoin state, preserve/no-truncate transitions for longer hits, unequal matched-prefix ledger bases, and commit logic that ignores redundant forced inputs before rejoin. Prefix masking and EOS masking are separate; EOS needs later cross-region mask propagation and per-lane actual-length commit.
- Workload review: TraceLab v0.0.2 was SHA-256 verified (`11ce51ec0a25e3d1d95b025bca2f7d1647e47571eb7cc968acd5fc64d4b4fb65`) and profiled separately from Mooncake. Raw TraceLab rows are mostly outside the current 1,792-token device envelope (only 28 full-round executable rows; no FIFO `bsz=2/4` batch is geometrically executable), but still preserve useful shape. Mooncake ToolAgent supplies exact 512-token block-hash history but capped output and weak first-block grouping. Use a shape-preserving projection and keep TraceLab/Mooncake separate; do not claim device speedup from trace token-work until a C1 CS-3 cost surface exists.
- Real-CS-3 fixed-communication C1 result was negative. Matched manual matrix: `S=256`, `N=1024`, `F=769`, `G=255`, Qwen3-1.7B, `bsz=SLOT_COUNT=2`, lane-1 rejoin `K in {0,256,512,768}`, 20 serial accepted runs. K0 mean was 288,953,017.6 cycles; K=256/512/768 speedups were -0.0328%, -0.0924%, and -0.0297%. K=768 avoided 767 timed lane-steps (37.49% of the lane-step rectangle) but did not reduce the device critical path.
- The negative result applies to the implemented C1-M predicate surface with fixed communication. C2 independent progress, communication compaction, EOS masking, energy/fairness, continuous batching, and SRAM accounting remain separate mechanisms and must not inherit a positive speedup.

Next gates: replay realistic traces with C1-M critical-path gain set to zero or a clearly labelled sub-0.1% sensitivity; do not launch the conditional 85-run position matrix unless a trace model says its upper bound could change the decision; keep C2/compaction/EOS/SRAM as separately reviewed routes.

Pointers: `docs/analysis/m1-s4-c1-workload-step-review.md`, `docs/analysis/m1-s4-real-workload-shape.md`, `docs/analysis/m1-s4-c1-s256-manual-comparison-provenance.md`, `docs/slides/2026-08-24-m1-s4-ragged-c1/`, `projects/WaferEngine-staging/meetings/2026-08-24-m1-s4-ragged-c1.pptx`.
