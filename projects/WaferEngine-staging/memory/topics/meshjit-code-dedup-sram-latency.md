---
summary: MeshJIT code-byte de-duplication does not automatically reduce loaded PE SRAM or latency; measure retained runtime infrastructure, usable .text capacity, and phase-reuse amortization.
tags: [waferengine-staging, meshjit, sram, latency, code-dedup, experiment]
---

# MeshJIT code de-duplication versus loaded SRAM and latency

## Summary

A 20×20-PE MeshJIT duplicate-pattern prototype showed that reducing replicated ELF/code-image bytes is not sufficient evidence of lower loaded PE SRAM or lower latency. Sparse placement removes leaf `.text` copies, but receiver-side runtime infrastructure can dominate the saved bytes.

## Findings — 2026-08-14

Drained from `memory/inbox/2026-08-12-meshjit-code-dedup-does-not-imply-loaded-sram-savings.md`:

- In the 40-configuration duplicate-pattern experiment, `all_replicas` had the lowest aggregate and peak loaded SRAM (13.0697%) even though all three candidate leaf functions stayed resident on every PE.
- Sparse placements saved the three candidate code images (1,060 B total), but retained receiver infrastructure: a fixed 1 KiB staging image, receive/forward and indirect-dispatch state, and for `catalog_cache` a 3 KiB cache. These overheads can exceed the saved leaf `.text`.
- Device cycles were also dominated by fully static replication for this tiny workload: `all_replicas` was the sole strict cold/warm Pareto point at 1,663 cycles. Sparse variants were at least 1,771 cycles warm and 23,971 cycles cold.
- Scope is deliberately narrow: 400 PEs in a 20×20 mesh, eight matrix stages, one length-20 vector pair per PE, and one of `dot`, `scaled_dot`, or `residual_dot`; RMSNorm, softmax, GELU, and tensor redistribution were host-side.

## Rule

Do not cite code-byte de-duplication as a practical MeshJIT memory or latency win by itself. A credible claim must measure released usable `.text` capacity, receiver runtime overhead, and amortization over repeated phase-local reuse.

## Pointers

- ContextBase: `duplicate-pattern — Full experiment report` (2026-08-07).
- ContextBase: `duplicate-pattern — Interactive HTML report` (2026-08-07); visualization only, no additional measurements.
