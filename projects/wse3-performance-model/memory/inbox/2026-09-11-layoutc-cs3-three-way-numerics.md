# Tall Layout C: first-step error versus a three-way baseline — 2026-09-11

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## Finding

When the tall group has a large first-step error despite correct QKV delivery,
check column readiness before A2 changes the shared collective axis. On CS-3,
a Y barrier before `a2_layer_body()` removed the integer-2 startup discrepancy;
no-barrier and descriptor-priming-only controls reproduced the failure. The
final probe-free patch then matched old side-by-side ATTN+FFN exactly for 33
integer-valued steps (mini width 16, heights 10/32/20, hidden 320, one layer).

Le requires NumPy / old layout / new layout comparison with identical logical
input, parameters and initial KV. Random BF16 33-step outputs differed between
layouts by relative L2 0.07007564%; captured QKV plus operation-order diagnostics
reproduce both downstream outputs exactly. This is not a new acceptance gate:
the original NumPy absolute-error gate still fails, shared SiLU(0) is nonzero,
and three old-projection diagnostic Q values remain unexplained upstream.
Do not label all remaining error as hardware precision or claim the 4B group
is validated. Full geometry was compile-only; feedback/head/tail were not run.

## Pointer

The report and immutable raw/reproduction artifacts carry job IDs, checksums,
controls, numerical limits and the next gate:
`/home/lexu/wse3-performance-model/docs/reports/2026-09-11-layoutC-cs3-three-way.md`.
Patch site:
`/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/src/tall_stage.csl:157`.
