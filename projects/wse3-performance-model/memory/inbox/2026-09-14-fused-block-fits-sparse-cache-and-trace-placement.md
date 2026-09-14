# Fusing ATTN+FFN onto one block fits in SRAM; the ladder still misses the agent case — 2026-09-14

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## What happened / finding

Situation: deciding whether to fuse a decoder layer's attention and FFN onto one
256×256 block (KV in local SRAM) vs keep the original two alternating blocks —
and how much context each layout actually holds. The SRAM verdict swung three
times from derivations before a compile settled it; only the compiled numbers
below are load-bearing.

- **Why fusion pays (measured basis, no MAC model):** the two original blocks
  *alternate* — one idle at a time (period T_attn+T_ffn, not max; one ~3.7 %
  wrap overlap). So one block time-multiplexing both roles gives the same period
  at half the area: 8 fused × 4.5 layers × 17,688 = 79,596 cyc/token vs the
  pipelined split's 9 × 11,886 = 106,974 → **1.34× at fixed wafer**, vs
  pipelining's measured 1.47× at 1× area.
- **Compiled per-PE totals (`msize.txt`, step-1b split, 2K):** ATTN 31.75 KB >
  FFN 29.77 KB despite FFN's 2.85× weights → per-PE footprint is **not
  weight-dominated** (ATTN carries ~15 KB non-weight); **HT tail 43.3 KB/PE is
  the wafer's binding region**, not either compute block.
- **Fusion fits (mini local compile at real per-PE config, validated to +0.1 %
  against the ATTN `msize.txt` anchor):** fused 5 layers / 8K context =
  **45,040 B < 49,152**, because `.text` does **not** sum — the linker keeps one
  copy of shared helpers (matvec/cast/comm/RMSNorm): fused `.text` 22,348 vs
  ATTN 21,444 + FFN 10,376 = 31,820. **Context ceiling ≈ 17.6K tokens (5-layer
  blocks), 29K (4-layer); split ≈ 26.1K.** Verified `cs_readelf --sym`: both
  bodies live in the fused ELF, only the own body in each specialized ELF.
- **Named kernel constraint:** the **512 B D-cache window**
  (`@comptime_assert(exp_p + 2·silu ≤ 512)`, `decode.csl:156`) fails when fused
  (576 B, real `ld.lld` link failure) and on layout C's A3 — two independent
  builds, same wall. Workaround: SiLU scratch to bank SRAM, +304 B.
- **Sparse-as-cache tile (1 compute + 3 storage per 2×2), compiled:** storage
  PE frees 18,560 B for KV (≈59.4K-token own ceiling; 16 attention-only FUNC
  symbols dead-code-eliminated), compute PE keeps only 1,246 B (**cannot hold its
  own 8K slice — link failure**), tile KV **2.59× dense**: 88 vs 32 resident
  2K requests, 21 vs 8 at 8K. Attention cost of sparsifying ≈ the +11.9 %
  quarter-density floor; scatter placement adds a **fixed +24 cyc** (simfab),
  not the predicted multiplicative hop penalty. Open: one-request-sharded vs
  many-requests reading; production comm strided membership unassessed.
- **Trace placement — no rung reaches the agent harness.** Claude-Code inputs
  p10 47K / p50 197K / p90 616K / p99 930K; ServeGen ≤23K; Mooncake p99 62–85K.
  Fusion 17.6K, split 26K, KV farm's *analytical* 167K (score-buffer wall) all
  sit **below the agent median**. Both fusion and the farm serve the
  short-context multi-tenant bucket; fusion is a "use the card well" gain, not a
  unique capability. Reopener = chunked scoring (lever C3, owned by
  `4b-chunked-softmax`).

## Implications / next actions

- Fusion is the best throughput-per-area layout available (~17.6K ctx), gated
  now on a real fused kernel (only a compile-only skeleton exists) and the
  D-cache phase-sharing fix.
- [ ] Decide sparse tile's sharding model (independent requests vs
  position-sharded single request) before any build — it changes what the tile
  is for; compute-PE KV must be minimal/streamed regardless.
- [ ] `stream-microbench`'s integrated distributed-attention prototype
  (dense vs 4-compute+12-storage, T ∈ {128,512,2048}) is in flight on simfab;
  its composed-vs-integrated gap is the next number; device batch pending.

## Pointers

- `docs/reports/2026-09-13-layoutC-performance-conclusion.md` §7 (fusion,
  sparse, placement), §5b
- `docs/reports/2026-09-13-fused-block-sram-compile.md` (+ §7 sparse capacity),
  `demo/fused-block/sram/out/evidence.json`
- `docs/reports/2026-09-14-scatter-collective-microbench.md`,
  `docs/reports/2026-09-13-fused-block-streaming-microbench.md`
- `docs/diagrams/2026-09-13-fused-block-pe-images.png`
- 4b-wide-layer Rounds 150–174 (its session report) for the cross-checks
