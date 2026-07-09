# qwen3_1p7b-e2e — on-chip data layout reference

Generated 2026-07-09 from source (session `e2e-kernel-qa`). Two documents, split
by wafer half. Ground truth throughout is
`model_config/test_device_2x2blk_kv_prof.json` — the **real Qwen3-1.7B** dims
(`dim=2048`, `head_dim=128`, `ffn=6144`, 16 Q-heads / 8 KV-heads, vocab 151936,
28 layers) on a 512×512 fabric.

| Document | Covers |
|---|---|
| [`e2e-data-layout-decode.md`](e2e-data-layout-decode.md) | x_demux · ht_head · decode block rows (+ west/east strips, KV-prof reporter) · ht_tail · logits mux · kv_prof_mux |
| [`e2e-data-layout-prefill.md`](e2e-data-layout-prefill.md) | pf_demux · pf_ht_head · prefill block region · pf_ht_tail · pf_logits_mux · pf_kv_prof_mux · relay seam |

Each tensor is documented with: (1) partition/replication across the PE region
and which logical dim maps to which fabric axis; (2) the local CSL symbol, its
shape, and the **dim order slow→fast** as actually indexed; (3) the host-side
transform that produced it; (4) the Qwen3-1.7B operation it feeds and which axis
that op contracts.

Companion: [`../decode-kpipe/kpipe-south.svg`](../decode-kpipe/kpipe-south.svg)
(inter-block-row Z transfer), [`../prefill-decode-transfer/e2e-topology-full.svg`](../prefill-decode-transfer/e2e-topology-full.svg)
(floorplan — **known to be wrong about the strip columns**, see the session Q&A log).

## Shared derived constants

`P_BLOCK_SIZE = 256`, 4 blocks, `max_layers_per_block = 7`.

| Constant | Decode | Prefill |
|---|---|---|
| `dim_per_pe` | 8 | 8 |
| `kv_dim_per_pe` | 4 | 4 |
| `gqa_group_size` | 2 | 2 |
| `ffn_dim_per_pe` | 24 | 24 |
| `seq_len_per_pe` | **2** (MAX_SEQ_LEN 512 / 256) | **1** (PREFILL_LEN 256 / 256, = `reduce_len`) |
| `prefill_len_per_pe` | 1 | — |
| `pes_per_kv_head` / `kv_head_root` | 32 / 16 | 32 / 16 |
| `pe_num_per_group` | 16 | 16 |
| `root_1st` / `root_2nd_phase` | 8 / 136 | 8 / 136 |
| vocab used | **152064** (padded) | **151936** (raw) |
| `V_per_pe_y` / `V_per_pe_x` | 594 / **1188** | — / **1187** |

## The two facts most worth knowing

**1. The axis roles are not fixed — hidden ping-pongs Y→X→Y→X→Y in decode.**
`X_tile` / RMSNorm shard the model hidden dim along **Y**. The QKV projection
contracts that hidden input along Y, so its *output* feature/head dim lands on
**X**. From there head_dim lives on X (kv-head bands of 32 PEs) and **sequence
lives on Y** (`process_kv` writes on the PE with `local_py == step % 256`).
`o_proj` contracts head dim along X, putting hidden back on Y; up/gate contract
hidden along Y (ffn out on X); `down_proj` contracts ffn along X, hidden back
on Y. `ht_tail` then flips again: vocab on X, dim on Y.

Prefill is **rotated 90°**: sequence along X, dim/kv_dim along Y. Local storage
is feature-major/seq-minor (`[feature, seq]`, `f*reduce_len + s`). That rotation
is exactly why the KV handoff transposes V but not K.

**2. The two halves disagree about vocab padding.** `build_decode` pads
151936 → 152064 (`lcm(256,128)`) and masks the 128 dummy logits via
`vocab_pad_count` before top-K. `build_prefill` does **no padding at all** — it
asserts exact divisibility (`launch.py:2136`) and hardcodes `vocab_pad_count = 0`
(`launch.py:2766`). Both work today only because 151936 divides 128 but not 256.
A dim/vocab that failed prefill's assert would hard-fail the build while decode
padded happily.

## Inconsistencies found in the source while writing these

1. **`src/decode/route_calc.csl:5` is stale/wrong.** Its header says
   "seq_len + KV-head bands along X". In decode the **seq axis is along Y** —
   `decode.csl:958` says so explicitly, and the reduces confirm it: softmax
   (`all_reduceMax_bsz_g`, `all_reduce_bsz_g`) and `output_matvec` contract the
   sequence via `local_py`, while `score_matvec` contracts head_dim kv-head-scoped
   on X. Only head/feature/ffn dims and KV-head bands live on X.
2. **`launch.py:287-306`** P_BLOCK_SIZE commentary describes a different device
   config (`P_BLOCK_SIZE=128, Pw=256`) than the shipped one; both reach
   vocab_pad=152064 but via different lcm multiples, so the comment's arithmetic
   does not literally apply.
3. **`HT_X_OFFSET = 0`** in every shipped config, so ht_head's "west relay-only
   columns" (the decoupled-width code path) are dead and their `W_E_tile`
   zero-fill is vestigial.
4. Prefill's `score_f32` / `attn_mask` / `score_h` are deliberately **not**
   `[feature, seq]`; they use a counter-stored `[slot][b][h][k][q]` layout.
   Documented exception, not a violation.
5. All prefill weights are mock (`randn * 0.1`). Real HF weights would need the
   decode-side permutations (`_perm_WQ`, `_reshard_K_dim`, `_perm_WO`) to reach
   the pair-interleaved GQA layout the RoPE fills already assume.
