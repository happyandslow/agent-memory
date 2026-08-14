# MeshJIT code de-duplication does not imply loaded-SRAM savings — 2026-08-12

**Project:** WaferEngine-staging
**Author:** codex
**Status:** drained
**Drained to:** `memory/topics/meshjit-code-dedup-sram-latency.md` (2026-08-14)

## What happened / finding

- When evaluating a 20x20-PE MeshJIT / duplicate-pattern prototype, do not use the reduction in replicated ELF/code-image bytes as evidence of lower loaded PE SRAM. In the 40-configuration experiment, `all_replicas` had the lowest aggregate and peak loaded SRAM (13.0697%), despite keeping all three candidate leaf functions resident on every PE.
- The sparse placements save the three candidate code images (1,060 B total) but retain runtime infrastructure at receivers: a 1 KiB fixed staging image, receive/forward and indirect-dispatch state, and, for `catalog_cache`, a 3 KiB cache. These costs can dominate the saved leaf `.text` bytes.
- The same setup was device-cycle dominated by fully static replication: `all_replicas` was the sole strict cold/warm Pareto point at 1,663 cycles. Sparse variants were at least 1,771 cycles warm and 23,971 cycles cold. A small one-shot leaf invocation does not amortize fetch/reload/selector and communication waits.
- Scope: this was a tiny Transformer code-distribution experiment, not a full LLM kernel: 400 PEs in a 20x20 mesh, eight matrix stages, and a length-20 vector pair per PE executing one of `dot`, `scaled_dot`, or `residual_dot`; RMSNorm, softmax, GELU, and tensor redistribution were host-side.

## Implications / next actions

- [ ] To claim a practical MeshJIT memory or latency benefit, measure released usable `.text` capacity and amortization over repeated phase-local reuse; code-byte de-duplication alone is insufficient.

## Pointers

- ContextBase: `duplicate-pattern — Full experiment report` (2026-08-07).
- ContextBase: `duplicate-pattern — Interactive HTML report` (2026-08-07); visualization only, no additional measurements.
