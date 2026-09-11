# LayoutC versus original 4B numerical attribution — 2026-09-11

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## What happened / finding

- When a changed pipeline differs from NumPy, a current-source vanilla comparator cannot establish whether the original baseline shared the discrepancy. The user-specified upstream 4B path is pinned to `b136ab64b3f5575c72fb722fb972ef5c77f4c9fe`, tree `7120f9085805f8702bd49cbda1f67f6d7e94ccd7`; the local SRAM baseline matches all 35 upstream files.
- Real CS-3, full 4B single-layer dimensions, synthetic BF16 fixtures, 33 supplied decode inputs, prefill1280/capacity1536, 16 PEs per reduction group: original and current vanilla at two 256×256 blocks are bitwise identical for integer and random fixtures. All four tested geometries match on integer. Random tall/original differs by 0.147389% L2; shrinking square256 to square128 differs by 0.305503%. Every completed full output is exactly reproduced by its source-derived operation order.
- Shared NumPy disagreement already exists upstream: polynomial SiLU versus sigmoid, score precision, RoPE arithmetic, and reduction/normalization order. Integer upstream L2 drops from 0.372348% to 0.121058% when only CPU SiLU is matched. This is attribution, not mathematical acceptance: the unchanged maxabs gate still fails.
- Correction to prior capture's unexplained mini remainder: CPU reduction must receive color0 then color1 with the side determined by root parity (group-index parity in phase2). Fixing the former unconditional high-leg-first CPU model exactly reproduces both previous mini random outputs too. No maintained kernel changed.

## Implications / next actions

- Preserve mathematical and operation-order references separately. Decide the intended numerical contract before changing operators; do not loosen thresholds to pass.
- Larger-group full-size attempts blocked; group16 controls completed, but the internal blocking mechanism remains unlocalized. No default-group fix or full-model/group-feedback acceptance is claimed.

## Pointers

- [Report, source sites, jobs, and reproducible evidence](/home/lexu/wse3-performance-model/docs/reports/2026-09-11-layoutC-upstream-numerical-attribution.md).
- [Original receive order](/home/lexu/wse3-performance-model/demo/qwen3-4b-decode-sram/code/qwen3_4b-decode-baseline/src/comm_lib/comm_pe.csl:785); [root parity mapping](/home/lexu/wse3-performance-model/demo/qwen3-4b-decode-sram/code/qwen3_4b-decode-baseline/src/route_calc.csl:58).
- Refines `2026-09-11-layoutc-cs3-three-way-numerics.md`; does not invalidate its measured arrays. This is a project-specific attribution, not a new general skill.
