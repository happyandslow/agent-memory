---
topic: pe-sram-memory-breakdown
tags: [waferengine, wse3, sram, qwen3, pr14, resource-analysis]
date: 2026-08-04
---

# Per-PE SRAM profile of PR #14 real Qwen3-1.7B decode + prefill

Re-profiled the **real deployment** decode + prefill kernels at PR #14 head
(WaferAGI/WaferEngine #14 "Real Qwen3 1.7B Serving", CongjieHe:real_qwen3_1p7,
commit `a8ab2a5`, 2026-08-04). This is the actual 2×4-block, P_BLOCK_SIZE=256,
28-layer (split [2,4,4,4,4,4,4,2], max 4 layers/block), seq-8192 config — NOT the
2×2/seq-512 config the 2026-06-28 breakdown used.

## Method (reproducible, all local — no cluster needed)
- `git worktree add --detach /home/lexu/we-sram-profile congjie/real_qwen3_1p7`.
- Local `cs_python launch_sim.py --compile-only` (cmaddr=None simfab, SdkTarget.WSE3,
  bf16) compiles the FULL real 512×1024 fabric locally in **50 s (decode) / ~510–540 s
  (prefill)** on this 1.5 TB / 128-core box. Per-PE ELF memory layout is byte-equivalent
  to a real-device compile (target/param-determined, not placement-determined).
  IMPORTANT: cs_python SIF cannot mount /tmp — run under /home/lexu.
- `tools/pe_mem_breakdown/run_breakdown.py --elfs-only` (source restored from branch
  `lexu/pe-mem-breakdown`; the working-tree copy was pycache-only). `elf_read` tool =
  SDK `cs_readelf`.
- Configs: decode `test_device_2x4block_seq8192.json`; prefill
  `device_8k_c256_baseline.json` (CHUNK_SIZE=256) and `device_8k_c512_whole_tile_flash.json`
  (CHUNK_SIZE=512). Prefill "optimization-stage" configs are IDENTICAL except CHUNK_SIZE +
  a label — `lifetime_arena`/`whole_tile_flash` are the same config; OPTIMIZATION_STAGE is a
  summary label, not a kernel gate. The differing SRAM verdicts in `results/raw/` came from
  earlier commits, not configs. So at PR head there are only 2 prefill operating points: c256, c512.

## Headline numbers (per-PE, 48 KB budget), tightest PE per role
| kernel / role | code | weights | kv | activ | system | free | %used |
| --- | --: | --: | --: | --: | --: | --: | --: |
| decode compute (4-layer block) | 26232 | 6452 | 2052 | 268 | 5046 | **9098** | **81.5%** |
| decode compute (2-layer end block) | ~10500 | 6448 | 2048 | 38 | ~4295 | ~25800 | ~47% |
| decode ht_tail (lm_head) | 13652 | 19024 | 0 | 8 | 7264 | **8916** | **81.9%** |
| decode ht_head (embedding) | 2372 | 19008 | 0 | 0 | 1740 | 26032 | 47.0% |
| prefill compute c256 | 30260 | 6628 | 2048 | 638 | 3904 | **5466** | **88.9%** |
| prefill compute c512 | 30664 | 6628 | 2048 | 796 | 4686 | **4074** | **91.7%** |
| prefill ht_head (mock 38 KB embed) | 1504 | 37988 | 0 | 1026 | 1926 | 6698 | 86.4% |
| prefill ht_tail (lm_head) | 12084 | 19008 | 0 | 8 | 7114 | 10774 | 78.1% |

## Findings
1. **`.text` code is the #1 per-PE cost in BOTH kernels** — 25.6 KB decode / ~30 KB prefill
   = 53–61% of the 48 KB budget, ahead of weights. Confirms the 2026-06-28 conclusion on the
   current PR.
2. **The prefill compute PE is the binding constraint of the whole real deployment: 88.9%
   (c256) → 91.7% (c512), only ~4–5 KB free.** Decode has ~2× the headroom (~9 KB free, ~82%).
   Whoever raises seq-len / chunk / adds kernel code hits prefill first.
3. c256→c512 adds ~950 B (activations+system from chunk_len_per_pe 1→2); weights/kv/code flat.
   Pushes prefill 88.9→91.7%.
4. Movement vs 2026-06-28 (2×2/seq512): decode code 22.6→25.6 KB (+3 KB kernel growth from
   on-device KV transfer, PR #13/#14); decode weights 11.2→6.3 KB (4 layers/block in real 2×4
   vs 7/block in 2×2); decode KV 0.23→2.0 KB (seq 8192 vs 512). Prefill code ~23→~30 KB (+7 KB)
   — prefill overtook decode as the tightest kernel.
5. Same-role PEs uniform except the decode compute split into 4-layer vs 2-layer classes (block
   schedule); the ~700 B intra-4-layer-class code spread is central-vs-edge routing.

## Artifacts
- Worktree + logs + breakdowns: `/home/lexu/we-sram-profile/` (RESULTS_sram_profile.md,
  bd_decode_real/, bd_prefill_c256/, bd_prefill_c512/ with CSV + stacked PNGs).
- Snapshot of the two model dirs at PR head: scratchpad `snapshot-pr14/`.

## Related
- [[pe-sram-memory-breakdown]] (the 2026-06-28 device breakdown this refreshes)
- [[project_decode_worker_seqlen_ceiling]], `tools/pe_mem_breakdown/`
