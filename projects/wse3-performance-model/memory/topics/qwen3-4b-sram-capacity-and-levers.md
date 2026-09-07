# Qwen3-4B SRAM capacity and levers

- Compiled-artifact measurement shows ATTN code/control, not weights, is the first-order SRAM cost for 4B decode; host-computed route tables remove `comm_mod.init` at roughly +5 KB/PE free SRAM and passed CS-3 verification for the slim tree.
- KV demand is 0.5625 B/token/ATTN-PE; after route-table slimming, device MAX_SEQ_LEN is 29,184 at bsz=1. The score buffer, not KV, is the analytical wall unless chunked/online softmax scoring is built.
- SRAM levers should be priced with the normalized supply/merit-order methodology and a demand curve `G(C)`; host per-token streaming is not viable because decode scans the whole KV each token.
