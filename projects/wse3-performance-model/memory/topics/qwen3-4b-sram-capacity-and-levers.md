# Qwen3-4B SRAM capacity and levers

- Compiled-artifact measurement shows ATTN code/control, not weights, is the first-order SRAM cost for 4B decode; host-computed route tables remove `comm_mod.init` at roughly +5 KB/PE free SRAM and passed CS-3 verification for the slim tree.
- KV demand is 0.5625 B/token/ATTN-PE; after route-table slimming, device MAX_SEQ_LEN is 29,184 at bsz=1. The score buffer, not KV, is the analytical wall unless chunked/online softmax scoring is built.
- SRAM levers should be priced with the normalized supply/merit-order methodology and a demand curve `G(C)`; host per-token streaming is not viable because decode scans the whole KV each token.

## 2026-09-14 update — compiled per-PE totals, fusion, near-pool gate

Source: `inbox/2026-09-14-fused-block-fits-sparse-cache-and-trace-placement.md`.

- Compiled per-PE totals (`demo/qwen3-4b-thin-stage/results/cs3/out_S1B_2K/msize.txt`,
  2K, 9 layers/block): ATTN 31.75 KB, FFN 29.77 KB, HT head 30.67, **HT tail
  43.27 — the binding region**. ATTN > FFN despite FFN's 2.85× weights:
  footprint is not weight-dominated (consistent with the first bullet above).
- **Fused ATTN+FFN block fits:** 45,040 B/PE at 5 layers/8K (mini compile at real
  per-PE config, +0.1 % vs the ATTN anchor); `.text` dedupes (22,348 vs
  31,820 summed). Context ceiling ≈17.6K (5L) / 29K (4L) vs split ≈26.1K.
- **Sparse tile (1 compute + 3 storage):** storage PE 18,560 B free for KV
  (~59.4K tok), compute PE 1,246 B (fails to link at 8K), tile 2.59× dense KV.
- **Near-pool lever gate "≤2 cyc/word, unmeasured"** now has a simfab number
  inside it with ~40 % headroom: ~1.17 cyc/word via fabin-operand FMA — and
  that is the score-GEMV shape the lever needs. Not banked: simfab, prices the
  pattern not the built path, needs re-pricing at real per-step volume.
- **Named constraint: 512 B D-cache window** (`decode.csl:156` comptime assert)
  fails for a fused image (576 B) and for layout C's A3 — a kernel property.
- Trace placement: fusion 17.6K / split 26K / farm 167K analytical all sit
  below the Claude-Code agent median (197K); reopener is chunked scoring.
