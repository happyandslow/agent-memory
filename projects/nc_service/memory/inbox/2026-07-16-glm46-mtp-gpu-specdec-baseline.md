# GLM-4.6 + MTP GPU-spec-dec baseline MEASURED on EIDF 8×H100

Date: 2026-07-16. Ran GLM-4.6-FP8 as an alternative verifier + its native MTP as the
GPU-spec-dec competitor baseline (the head-to-head Kimi couldn't do — Kimi has no MTP).
**Status:** drained

## Deploy (huge contrast vs Kimi)
- Downloaded `zai-org/GLM-4.6-FP8` (355B, FP8) → /ckpt in **~8.5 min** (HF fast, ~675MB/s).
- Load: **~4 min** (FP8 W8A8, `CompressedTensorsW8A8Fp8MoE`, NO marlin repack), **41.9GB/GPU
  used, ~28GB free** (vs Kimi 72GB/1GB, 72-min load). Fits 8×H100 with huge headroom.
- GOTCHA: crashed at bring-up on `CUDASymmetricMemory init_multicast_for_block` (CUDA
  multicast / NVLink SHARP unavailable in the k8s pod). FIX: add
  `--disable-custom-all-reduce --enforce-disable-flashinfer-allreduce-fusion` → NCCL
  allreduce fallback. Works but unoptimized (penalizes GLM's 92-layer allreduce).
- MTP launch (nextn auto-loaded from same ckpt): `--speculative-algorithm EAGLE
  --speculative-num-steps 1 --speculative-eagle-topk 1 --speculative-num-draft-tokens 2`
  (draft-model-path auto-set to the model; loads `Glm4MoeForCausalLMNextN`, 0.93GB).

## RESULT (bs=1, cuda_graph=True, 256-tok decode, temp0)
| config | throughput | TPOT | speedup | acceptance |
|---|---|---|---|---|
| GLM-4.6 vanilla | 58 tok/s | 17.2 ms | 1× | — |
| GLM-4.6 + MTP | 85.5 tok/s | 11.7 ms | **1.47×** | accept_len 1.80, accept_rate 0.80 |

- MTP proposes 1 token, ~80% accepted → ~1.8 tokens/round (matches DeepSeek-V3 MTP 85-90%).
- **1.47× is the same-hardware MEASURED GPU-spec-dec competitor** (unoptimized/NCCL
  allreduce). Published optimized MTP ≈ 1.8× → real competitor band ~1.47–1.8×.
- GLM-4.6 92 layers → bs=1 decode is layer-latency+allreduce bound; vanilla 17.2ms is
  SLOWER than Kimi's 9.2ms (Kimi 61 layers + Kimi used fast allreduce).

## For the hybrid eval
- This is the ② competitor Kimi couldn't provide. If they switch verifier to GLM, the
  hybrid must beat 1.47–1.8×. Their Cerebras 1.7B draft (K=16-31, ~10 accept/round) is
  far stronger than MTP (K=1, 1.8/round) → should clear it easily — that's the "why
  Cerebras" quantified comparison. Caveat: GLM vocab 151552 ≠ Kimi 163840 → draft retrain.
- Open: optimize GLM allreduce (get multicast working / use custom P2P allreduce, not
  NCCL) to get the fair/optimized MTP number (~1.8×).
