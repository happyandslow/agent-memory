# e2e vs pdSeparate — CS-3 Device Validation, Real-Weights Gap, Max-Context

Session 2026-07-05: quick-validate the two end-to-end qwen3_1p7b deployments on
CS-3 (real WSE-3), check real-weights inference, and characterize KV-eviction
tradeoffs ([[kv-cache-policy-tradeoffs]]).

## CS-3 device results

Launched via `/cs3-runner` (gateway warm, no OTP needed this session; repo synced
to `CS-3:~/rsync/WaferEngine-staging-rsync/`). Timeout guards pd=1200s / e2e=2400s.

| Model | Config | Result | wsjob | Timings |
|---|---|---|---|---|
| **qwen3_1p7b-e2e** (fused, on-chip KV relay) | `test_device_2x2blk_kv` (seq 512 / prefill 256) | ✅ **PASS — first-ever hardware run** | `wsjob-dhpbbq2k8azqra5szlb2ct` | compile **291.3s**, run **6.9s**; decode **2240 tok/s** (446 µs/tok), prefill **5880 tok/s**; `SUCCESS: decode top-1 invariant over 256 steps` |
| **qwen3_1p7b-e2e-pdSeparate** (PD-disagg, host-DRAM KV) | `test_device_2x2blk_kv` (seq 4096 / prefill 2048) | ❌ **Compile FAIL** — prefill.csl per-PE SRAM overflow | `wsjob-mffesnuwgdr4awuhdjoqtg` | `.bss` top 0x10DCB = **69,067 B** vs 48 KB budget, overlaps `.filters` |

- **e2e**: footprint 645×1028 of 762×1176. First confirmation the fused
  co-resident artifact + on-chip prefill→decode KV relay (`KV_TRANSFER=1`) runs on
  hardware. Validates PIPELINE correctness on **mock weights** (top-1 invariant),
  not real-model accuracy.
- **pdSeparate**: `M-B3_M-B4_STATUS.md` recorded this same config passing
  (`wsjob-pqywyqn6kezfctyfylwp3u`) but **as uncommitted work** → the committed tree
  has **regressed** / the prior pass was fragile. Fails at the prefill compile,
  before decode.
- Transient gotcha: one e2e launch died `Permission denied (publickey)` (rc=255) —
  warm gateway window lapsed mid-run; a re-check + retry succeeded. Shared account
  `congjiehe`: identify own jobs by **workflow id**, not USER (a blanket
  `cancel-mine` would kill other tenants).

## Real weights — NOT wired (both models)

Neither model can do real Qwen3-1.7B inference today. `WEIGHT_SCALE = 0.05  # HF
weights override` (both `launch.py:47`) is **aspirational** — every weight tensor
is `np.random.RandomState(seed).rand(...)*0.05` (mock). No HF/safetensors/
checkpoint loader, no CLI/config hook, and **no Qwen3 `gpu_reference` oracle** (only
llama3 exists). Device configs *are* true Qwen3-1.7B geometry (dim 2048, ffn 6144,
28 layers, vocab 151936) so the fabric holds the real model — but filled with
random numbers → garbage tokens. The oracle (`qwen3_1p7b-decode/host/oracle_fp16.py`)
only checks self-consistency vs the mock RNG.

Data-layout plumbing IS HF-aligned (`_zpad` padding, `_perm_WQ/_perm_WO/
_reshard_K_dim`, bf16-as-uint16 upload, tied lm_head, Qwen3 RoPE + QK-norm), so
enabling real weights = replace RNG draws with real tensor slices + add a tokenizer
+ a Qwen3 oracle. Additive, not a rewrite. **Deferred by Le this session.**

## Max context length (pdSeparate, 48 KB/PE budget)

Pinned by local `cslc` compile-only sweeps (SDK 2.10) + a per-PE byte model,
validated within 2% against two hardware anchors (256→LINK, 2048→OVERFLOW).

**Byte model** (2×2 layout, P_BLOCK_SIZE=256, 7 layers/PE-block; `s = PREFILL_LEN/256`):
`prefill_total ≈ 30,112 (code) + 13,470 (weights ∝ layers/block) + 1,504·s + 200·s²`.
The **`200·s²` score/mask term** (attn_tmp/score/mask f32 + score_h fp16) is the
context limiter; `KV_EGRESS=1` adds ~0 bytes. Decode is **linear**: ~124 B per 256
tokens of MAX_SEQ_LEN.

- **Prefill (binding kernel): max PREFILL_LEN ≈ 512 tokens.** 256 LINKS (measured);
  512 predicted PASS (~1.8 KB margin, killed mid-compile so not measured); 768
  marginal fail (+0.7 KB); 2048 measured fail (+19 KB).
- **Decode (not binding): MAX_SEQ_LEN ~7–8 K** before its linear KV overflows;
  holds 4096 in ~2 KB/PE.

**Bottom line:** max context on the shipped 2×2/7-layer layout ≈ **4096 total, but
only with prompt ≤ ~512** (rest generated). The shipped `test_device_2x2blk_kv`
(prompt 2048) fails **only** because of PREFILL_LEN=2048, not MAX_SEQ_LEN. A **2×4**
layout (4 layers/block, frees ~4.8 KB) roughly doubles the prompt cap to **~1024**
(pdSeparate ships no 2×4 config; inferred from the standalone-prefill 2×4 baseline
that fits at 92.6%). Caveat: local SDK 2.10 vs cluster 1.13.2 share `arch=wse3`'s
48 KB map, so the PASS(≤512)/FAIL(≥1024) split is robust; only the 768 case is
codegen-marginal.

## Launch mechanics (for reruns)

- Device entry: `models/<m>/run_device.sh <cfg>` → `launch_device.py` (fixed
  `FILES_TO_STAGE` list — every new `.csl` MUST be added or compile dies) →
  `SdkLauncher` (self-allocates appliance, substitutes `%CMADDR%`, runs
  `cs_python launch.py --cmaddr ...`). Self-contained; no external cmaddr.
- pdSeparate = **orchestrator in `launch.py`**: forks prefill then decode
  subprocesses (same `--cmaddr`), bridging KV via a temp `kv_handoff.npz`.
- Remote cmd must `source ~/miniconda3/etc/profile.d/conda.sh && conda activate csl`
  (only that env has `cerebras.sdk.client`).
- e2e configs use small seq (512/256); pdSeparate configs use large seq (4096/2048)
  — which is exactly why pdSeparate overflows and e2e doesn't.

## Last updated

2026-07-05.
