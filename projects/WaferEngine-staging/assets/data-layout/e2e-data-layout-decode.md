# On-chip data layout — DECODE half of `qwen3_1p7b-e2e`

Ground-truth config: `models/qwen3_1p7b-e2e/model_config/test_device_2x2blk_kv_prof.json`
(real Qwen3-1.7B dims). Only the decode half is covered (regions built by
`build_decode`, `launch.py:238`). Nothing here touches `src/prefill/`.

All `file:line` citations are into `models/qwen3_1p7b-e2e/`. The decode block-PE
kernel is `src/decode/decode.csl`; collectives `src/decode/comm_lib/comm_pe.csl`;
routing `src/decode/route_calc.csl`.

Fabric-axis convention (proved in `route_calc.csl:66-70` + header `:5-8`):
**`local_px` = fabric X (block-local column 0..255), `local_py` = fabric Y
(block-local row 0..255).** `Y_*_reduce_*` routes are N↔S (fabric Y);
`X_*_reduce_*` / `X_kv_head_*` routes are W↔E (fabric X). Snake runs along X;
inter-region pipeline hops are Y+1.

---

## Derived constants (this config)

| Constant | Value | Derivation (launch.py) |
|---|---|---|
| `Pw`,`Ph` | 512, 512 | config |
| `P_X_BLOCK_NUM`,`P_Y_BLOCK_NUM` | 2, 2 | config |
| `P_BLOCK_SIZE` | **256** | `Pw // P_X_BLOCK_NUM` = 512/2 (`:255`) |
| `N_blocks` | 4 | `P_X_BLOCK_NUM*P_Y_BLOCK_NUM` (`:443`) |
| `group_num` | 16 | config |
| `dim` (padded) | 2048 | `_pad_to(2048, lcm(256,128)=256)` → no pad (`:356`) |
| `dim_true` | 2048 | RMSNorm divisor (`:345`, `decode.csl:573`) |
| `head_dim` | 128 | config; never padded (scalar) |
| `kv_dim` | 1024 | `n_kv_heads*head_dim` = 8·128; pad_to 256 → 1024 (`:357,384`) |
| `ffn_dim` (padded) | 6144 | `_pad_to(6144,256)` → no pad (`:358`) |
| `seq_len` (padded MAX_SEQ_LEN) | 512 | `_pad_to(512,256)` (`:359`) |
| `n_heads`,`n_kv_heads` | 16, 8 | `dim/head_dim`, `kv_dim/head_dim` (`:364-365`) |
| `vocab_true` | 151936 | config |
| **`vocab_pad`** | **152064** | `_pad_to(151936, lcm(256,128)=256)` = 594·256 (`:360`) |
| **`vocab_pad_count` (total)** | **128** | 152064 − 151936 (masked in tail, `launch.py:1755`) |
| `dim_per_pe` | **8** | `dim/P_BLOCK_SIZE` = 2048/256 (`:389`) |
| `kv_dim_per_pe` | **4** | `kv_dim/P_BLOCK_SIZE` = 1024/256 (`:390`) |
| `seq_len_per_pe` | **2** | `seq_len/P_BLOCK_SIZE` = 512/256 (`:391`) |
| `ffn_dim_per_pe` | **24** | `ffn_dim/P_BLOCK_SIZE` = 6144/256 (`:392`) |
| `gqa_group_size` | **2** | `dim_per_pe/kv_dim_per_pe` = 8/4 (`:396`; = 16/8) |
| `_dim_per_pe`,`_kv_dim_per_pe` | 8, 4 | `(x/2)*2` (even, `decode.csl:27-28`) |
| `pe_num_per_group` | **16** | `P_BLOCK_SIZE/group_num` = 256/16 (`:414`) |
| `root_1st_phase` | **8** | `pe_num_per_group/2` (`:415`) |
| `root_2nd_phase` | **136** | `(group_num/2)*pe_num_per_group + root_1st_phase` = 8·16+8 (`:441`) |
| `pes_per_kv_head` | **32** | `P_BLOCK_SIZE/n_kv_heads` = 256/8 (`:421`) |
| `kv_head_root` | **16** | `pes_per_kv_head/2` (`:440`) |
| `prefill_len_per_pe` | **1** | `PREFILL_LEN/P_BLOCK_SIZE` = 256/256 (`:380`) |
| `max_output_len` (decode steps) | **256** | `MAX_SEQ_LEN − PREFILL_LEN` = 512−256 (`:276`) |
| `layer_counts` / `offsets` | [7,7,7,7] / [0,7,14,21] | `distribute_layers(28,4)`: x=7,y=0 (`:448`) |
| **`max_layers_per_block`** | **7** | `max(layer_counts)` (`:449`) |
| `HT_WIDTH_head` | 128 | `P_BLOCK_SIZE//2` (`:511`) |
| `HT_WIDTH_tail` | 128 | config (`:512`) |
| `HT_X_OFFSET` | 0 | `HT_WIDTH_tail − HT_WIDTH_head` (`:516`) |
| `V_per_pe_y` | **594** | `vocab_pad/P_BLOCK_SIZE` = 152064/256 (`:435`) |
| `V_per_pe_x` | **1188** | `vocab_pad/HT_WIDTH_tail` = 152064/128 (`:1745`) |
| `HT_W_E_K` | 9504 | `V_per_pe_y·2·dim_per_pe` = 594·16 (`:436`) |
| `HT_LM_HEAD_K` | 9504 | `V_per_pe_x·dim_per_pe` = 1188·8 (`:1901`) |
| `batch_per_pe_step` | 4 | `bsz·dim_per_pe/2` u32 (`:458`) |
| `KPIPE_K` / `KPIPE_M_PER_PIPE` | 8 / **32** | `P_BLOCK_SIZE/KPIPE_K` (`:594`, `decode.csl:1319`) |
| tail X-topk `pe_num_per_group_x` | 16 | `min(16, HT_WIDTH_tail//2)` (`:1778`) |
| tail `root_1st_phase_x`/`root_2nd_phase_x` | 8 / 72 | group_num_x=8; `(8/2)·16+8` (`:1786-1787`) |
| topk south blob (`south_wlts_per_step`) | 4 | val_wlts 1 + arg 1 + tok 1 → pad→4 (`:1872-1881`) |
| `bsz`,`TOP_K` | 1, 1 | config |

Padding note: this config is "clean" — the only real padding is **vocab
151936→152064 (128 dummy ids)**. `dim`/`kv_dim`/`ffn`/`seq` all already divide,
so every per-PE extent equals its divisible-case value and the byte stream is
identical to the unpadded path (`launch.py:367`, `_pad_to` identity).

Every weight tile is banked `[max_layers_per_block(=7) * <per-layer extent>]`
(`decode.csl:363-463`); `set_layer(l)` (`decode.csl:474-492`) repoints `ptr_*`
to `bank[l*extent]`. Each of the 4 blocks holds exactly 7 layers so no tail
zero-pad occurs here (shorter blocks would zero-pad, `launch.py:1670-1676`).

---

## Module: x_demux (`src/decode/demux.csl`; built `launch.py:691-776`)

Region **1 col × `P_BLOCK_SIZE`(=256) rows**, placed at fabric (2, PLACE_Y). A
store-and-forward Y-column that scatters the host-seeded X[0] across the 256
hidden-shard Y-PEs. Single-shot: only decode step 0 (`demux.csl:1-4`); later
tokens close on-chip via HT_tail→tok_bcast→HT_head.

| Tensor | Sharding (X/Y/repl/banked) | Local symbol & shape | Dim order slow→fast | Op it feeds |
|---|---|---|---|---|
| X[0] seed slice | **hidden dim → Y** (dim_per_pe=8 per row); 1 col only | `own_buf: [OWN_B=4]u32` = 8 f16 = `bsz*dim_per_pe` (`demux.csl:42`) | `[batch, dim_per_pe]` (packed u32 pairs) | input to HT_head embedding relay (`out_color`=pre_embed_x, `:752`) |

- **Host transform** (`launch.py:3006-3020`): `host_x = W_E_full[token_id]`
  (the tied-embedding row, seed 2024, `dim`-long). Then
  `reshape(bsz, P_BLOCK_SIZE, dim_per_pe).transpose(1,0,2)` ⇒ axis0 = the 256
  Y-PEs each owning `dim_per_pe` contiguous hidden features → **hidden dim on Y**.
  Streamed as one host input stream into demux PE 0 (Edge.TOP), which keeps its
  own 8 f16 and forwards `(P−k−1)·B` u32 south to PE k+1 (`demux.csl:106-131`).
- **Operation**: token-embedding *delivery* (not compute at step 0). Each PE
  drains its own `dim_per_pe` slice and sends it EAST on `pre_embed_x_color`
  (id 18) into HT_head's west edge (`demux.csl:12`, `launch.py:751`).

---

## Module: ht_head (`src/decode/ht_head.csl`; built `launch.py:808-992`)

Region **`HT_WIDTH_tail`(=128) cols × `P_BLOCK_SIZE`(=256) rows**, at
(HT_HEAD_X=3, PLACE_Y). Token-embedding lookup (`embed_tokens`). With
`HT_X_OFFSET=0` here, all 128 columns are active embedding columns (no west
relay-only columns). Diagonal pairing: column `x` owns diag PEs at py=2x (upper)
and py=2x+1 (lower) (`ht_head.csl:5,247-249`).

| Tensor | Sharding | Local symbol & shape | Dim order slow→fast | Op it feeds |
|---|---|---|---|---|
| `W_E` (token embedding = tied lm_head) | **vocab → Y** (V_per_pe_y=594 rows/PE); **hidden → X** (2·dim_per_pe=16 cols/PE) | `W_E_tile: [V_per_pe_y*2*dim_per_pe = 9504]@fp16` per PE (`ht_head.csl:60`) | `[vocab_row(594), hidden(16)]` row-major (`launch.py:983-984` `tile.reshape(-1)`) | embedding gather → `embed_buf` → C2 east to row_0 |
| embedded X (per step) | diagonal-resident; hidden 2·dim_per_pe on the diag column | `embed_buf: [bsz*dim_per_pe=8]@fp16` (`ht_head.csl:64`) | `[batch, dim_per_pe]` | `c2_color`(post_embed_x id 23) → row_0 host-X receiver |
| token id (step ≥1) | replicated per column (tail emits full band) | `token_id_buf: [bsz]i32` (`ht_head.csl:63`) | `[batch]` | selects `W_E` row: `py_b=t/V_per_pe_y`, `v_off=t%V_per_pe_y` (`ht_head.csl:294-300`) |

- **Sharding detail**: `W_E_full` (vocab_pad × dim) is tiled so PE (py, x_local)
  holds rows `[py·594 : (py+1)·594]` and hidden columns
  `[x_local·16 : (x_local+1)·16]` (`launch.py:960-984`). Because the diag
  pairing gives column x **2·dim_per_pe** hidden positions, the embedding
  identity `HT_WIDTH_head·2·dim_per_pe == dim` (128·16 = 2048) holds
  (`launch.py:520`). The "**diag-pair split**": the 16 hidden columns owned by
  column x are split into an upper half `dim_per_pe` (rows offset
  `v_off·16`) and lower half (`+dim_per_pe`), gathered to the two diag PEs
  py=2x / py=2x+1 via the UP_A/UP_B (NORTH) and DOWN_A/DOWN_B (SOUTH) relay
  chains (`ht_head.csl:126-226`).
- **Op**: `embed_tokens` lookup. Step 0 the diag PE just drains the host C1
  stream into `embed_buf`; step ≥1 it gathers `W_E[token]` across the column
  and emits east every step (`ht_head.csl:277-309`). Vocab (Y) and hidden (X)
  are **partitioned, not reduced** here — no allreduce; delivery only.

---

## Module: decode block rows (`src/decode/decode.csl`; built `launch.py:1024-1236`)

`P_Y_BLOCK_NUM`(=2) row regions, each **`Pw+2`(=514) cols × `P_BLOCK_SIZE`(=256)
rows** = 1 west strip (lcl_x=0) + `Pw`(=512) block cols (lcl_x 1..512, two
`P_BLOCK_SIZE`=256 block columns per row) + 1 east strip (lcl_x=513). Row 0 is
the chain start (host-X in); row 1 (`last_row`, odd) snakes WEST and its edge col
streams Z to HT_tail. Blocks hold 7 layers each, banked.

Within one 256×256 block: **`local_py` (Y) shards the model hidden dim; `local_px`
(X) shards the head/feature dim after the QKV projection and the KV-head bands.**
The X-input is broadcast so every Y-PE in a column starts each layer holding the
same `dim_per_pe` hidden slice for its column, and the P_BLOCK_SIZE Y-PEs
together hold the full hidden dim (RMSNorm reduces over them).

### Per-layer weight / cache tensors (each banked ×7)

| Tensor | Sharding | Local symbol & shape (per layer) | Dim order slow→fast | Op it feeds / matmul contract axis |
|---|---|---|---|---|
| `input_layernorm` γ | input hidden → Y; **replicated across X** | `W_attn_norm_tile: [dim_per_pe=8]@fp16` (`:374`) | `[dim_per_pe]` | RMSNorm(X); Y-reduce of sumsq |
| `post_attention_layernorm` γ | same | `W_ffn_norm_tile: [8]@fp16` (`:378`) | `[dim_per_pe]` | RMSNorm(Z) |
| `q_proj` W | in-dim → Y, **out(head) dim → X** | `Q_weight_tile: [dim_per_pe*dim_per_pe = 64]@fp16` (`:383`) | `[in_dim_per_pe(8), out_dim_per_pe(8)]` K-outer | q_proj; **contracts Y** |
| `k_proj` W | in→Y, out(kv) →X | `K_weight_tile: [dim_per_pe*kv_dim_per_pe = 32]@fp16` (`:389`) | `[in(8), out_kv(4)]` | k_proj; contracts Y |
| `v_proj` W | in→Y, out(kv) →X | `V_weight_tile: [8*4 = 32]@fp16` (`:392`) | `[in(8), out_kv(4)]` | v_proj; contracts Y |
| `q_norm` γ | head_dim band → X (RoPE-pair order); tiled ×gqa | `q_norm_tile: [dim_per_pe=8]@fp16` (`:402`) | `[gqa(2)·kv_dim_per_pe(4)]` pair-interleaved | q_norm (per-head RMS over head_dim); **X kv-head reduce** |
| `k_norm` γ | head_dim band → X | `k_norm_tile: [kv_dim_per_pe=4]@fp16` (`:404`) | `[kv_dim_per_pe]` pair-interleaved | k_norm |
| `o_proj` W | **in(head)→X, out(hidden)→Y** | `O_weight_tile: [dim_per_pe*dim_per_pe=64]@fp16` (`:453`) | `[out(8), in(8)]` (post `.transpose(1,0,2)`) | o_proj; **contracts X** |
| `up_proj` W | in(hidden)→Y, out(ffn)→X | `UP_weight_tile: [dim_per_pe*ffn_dim_per_pe = 192]@fp16` (`:456`) | `[in(8), ffn(24)]` | up; contracts Y |
| `gate_proj` W | same | `GATE_weight_tile: [8*24 = 192]@fp16` (`:459`) | `[in(8), ffn(24)]` | gate; contracts Y |
| `down_proj` W | **in(ffn)→X, out(hidden)→Y** | `DOWN_weight_tile: [ffn_dim_per_pe*dim_per_pe = 192]@fp16` (`:462`) | `[out(8), in(24)]` (post `.transpose(1,0,2)`) | down; **contracts X** |
| RoPE state (θ=1e6) | head-dim pair band → X; replicated across Y; **layer-invariant** (not banked) | `cos_cur_f32/sin_cur_f32/delta_*_f32: [_dim_per_pe/2 = 4]f32` (`:421-424`) | `[pair index]` | RoPE recurrence (`rope_step_advance`, `:502`) |
| **K cache** | **kv_dim → X (per kv-head band), seq → Y** | `XKCache_tile: [bsz*kv_dim_per_pe*seq_len_per_pe = 8]@fp16` /layer (`:447`) | `[batch, kv_feature(4), seq(2)]` — feature-major | score = Q·K |
| **V cache** | **kv_dim → X, seq → Y** | `XVCache_tile: [bsz*seq_len_per_pe*kv_dim_per_pe = 8]@fp16` /layer (`:450`) | `[batch, seq(2), kv_feature(4)]` — seq-major | output = score·V |

### Working/activation tensors

| Tensor | Sharding | Local symbol & shape | Dim order slow→fast | Op |
|---|---|---|---|---|
| X (hidden state) | hidden → Y; replicated across X (post bcast) | `X_tile / X_input_tile: [bsz*dim_per_pe=8]@fp16` (`:354,360`) | `[batch, dim_per_pe]` | layer input; residual base |
| QKV packed | Q region hidden→Y then X; K/V kv-shard | `QKV_tile: [bsz*(dim_per_pe+2*kv_dim_per_pe)=16]@fp16` (`:606`); fp32 shadow `QKV_f32` (`:610`) | `[Q(8) | K(4) | V(4)]` (`:602-606`) | QKV projection + reduce |
| score (attn logits) | per Q-head-group; **seq → Y (iter_num cols local)** | `score: [gqa_group_size*bsz*seq_len_per_pe = 4]@fp16` (`:626`); fp32 `score_f32` (`:630`) | `[gqa(2), batch, seq(2)]` | softmax; alpha=1/√head_dim |
| attn output | hidden(head) → X (pre o_proj) | `scratch_dim_a` via `ptr_output`; fp32 `scratch_dim_a_f32` (`:551,634`) | `[batch, dim_per_pe]` | o_proj input |
| h1 (o_proj out) | hidden → Y | `scratch_dim_b` `ptr_h1`; fp32 `scratch_dim_b_f32` (`:552,636`) | `[batch, dim_per_pe]` | attn residual add |
| ffn up|gate | ffn → X | `ffn_up_gate_tile: [bsz*2*ffn_dim_per_pe=48]@fp16` (`:642`); fp32 shadow (`:646`) | `[up(24) | gate(24)]` | SwiGLU |
| ffn swiglu | ffn → X | `ffn_swiglu_tile: [bsz*ffn_dim_per_pe=24]@fp16` (`:692`) | `[ffn_dim_per_pe]` | down_proj input |
| Z (layer out) | hidden → Y | `Z_tile: [bsz*dim_per_pe=8]@fp16` (`:698`) | `[batch, dim_per_pe]` | next layer X / result to HT_tail |
| RMSNorm scratch | — | `X_fp32_buf: [dim_per_pe=8]f32` (`:568`); `local_sum_f32:[bsz]f32` | `[dim_per_pe]` | fp32 sumsq |
| QK-Norm sumsq | fused Q+K | `qknorm_sum_g_f32: [(gqa_group_size+1)*bsz = 3]f32` (`:621`) | `[Q-groups(2) | K(1)]` | X kv-head reduce |

### Host-side weight transforms (`launch.py:1384-1630`)

- `shard_3d(W, in_per_pe, out_per_pe, swap_xy)` (`:1469`): reshapes
  `(P·in, P·out)` → `(P, in, P, out)` → transpose. **`swap_xy=False`:
  `(0,2,1,3)` ⇒ axis0=input-band=**Y** owns input rows, axis1=**X** owns output
  cols**. `swap_xy=True` (K cache only): `(2,0,1,3)` ⇒ Y owns seq (cols), X owns
  kv_dim (rows). `flatten_shard` (`:1483`) then reshapes to `(Y=256, X·K)` for
  `set_symbol_all`.
- `_perm_WQ` (`:1384`): reorders Q output cols into HF-RoPE-pair +
  kv-head-interleaved order so on-chip GPT-J interleaved-pair RoPE matches HF
  `rotate_half`; output cols map to X-PE bands.
- `_reshard_K_dim(W, axis)` (`:1414`): same HF-pair reshuffle on a kv_dim axis
  (K weight axis=1 out cols; K-cache prefill axis=0 rows).
- `_perm_WO` (`:1436`): permutes O input rows to match `_perm_WQ`'s output order,
  then `shard_3d(...).transpose(1,0,2)` (`:1512`) swaps the (out,in) tile
  assignment so o_proj reduces along X. `down_proj` gets the same `.transpose`
  (`:1626`).
- `_tile_head_vec` (`:1536`): reshards head_dim `q_norm`/`k_norm` vectors into
  the interleaved RoPE-pair per-X-band layout (Q tiled ×gqa_group_size,
  replicated across Y).
- RoPE θ=1e6 (`ROPE_THETA`, `:51`); `cos_cur = cos(prefill_len·inv_freq)`,
  `delta = cos(inv_freq)` etc. (`:1567-1592`).

### The axis-role switch (the subtle part)

Traced through `decode_layer_body` (`decode.csl:1229-1289`) with the reduce each
op invokes (each collective's *axis* is set by `reconfig_allreduce_axis`
+ the `local_px`/`local_py` argument):

1. `rmsnorm_x` → `all_reduce_bsz_f32(local_py, …)` (Y, `decode.csl:754`) —
   contracts hidden ⇒ **hidden on Y** (256 Y-PEs each `dim_per_pe`=8, RMS divisor
   = `true_model_dim`=2048, `decode.csl:573`).
2. q/k/v_proj → `all_reduce_bsz_dim_QKV_fusion(local_py, …)` (Y, `:1236`) —
   contracts the input hidden (Y). **Output feature/head dim now lives on X**:
   each column `local_px` owns a distinct `dim_per_pe`/`kv_dim_per_pe` output
   slice, replicated across Y after the reduce-broadcast. *This is where the
   switch happens* — the QKV matmul contracts Y, so its output is X-sharded.
3. `reconfig_allreduce_axis(3)` → kv-head X routes. `qk_norm_q_k` →
   `all_reduce_qk_kv_head_scoped(px_in_kv_head, …)` (`:951`) contracts head_dim
   across the `pes_per_kv_head`=32 PEs of one kv-head band along **X**.
4. `score_matvec_mult` (Q·K, contract head_dim) →
   `all_reduce_bsz_g_seq_len_kv_head_scoped(px_in_kv_head, …)` (`:1051`) — **X,
   kv-head-scoped**. `process_kv` (`:968`) writes the new token on the single PE
   with `local_py == step % P_BLOCK_SIZE` ⇒ **sequence laid along Y** (token t →
   row t mod 256, local seq column `iter_num = t // 256`).
5. `reconfig(0)` → Y. `softmax_score` normalizes over all seq positions →
   `all_reduceMax_bsz_g` / `all_reduce_bsz_g(local_py, …)` (`:1074,1100`) reduce
   **along Y** (seq is on Y).
6. `output_matvec_mult` (score·V, contract seq) →
   `all_reduce_bsz_dim(local_py, …)` (`:1151`) — **Y** (seq on Y). Attention
   output is now head/feature-dim, still on X.
7. `reconfig(1)` → X. `o_matvec_mult` (o_proj, contract head dim) →
   `all_reduce_bsz_dim(local_px, …)` (`:1158`) — **X**. Output hidden dim →
   back on Y (weight cols per Y-PE), ready for the residual `Z = X + h1`.
8. `rmsnorm_z` (Y), up/gate → `all_reduce_bsz_ffn_dim_ZZ_fusion(local_py, …)`
   (`:1271`) — **Y** (contract hidden), output ffn on X.
9. `reconfig(1)` → X. `down_matvec_mult` (contract ffn) →
   `all_reduce_bsz_dim(local_px, …)` (`:1218`) — **X**. Output hidden → Y.
10. `reconfig(0)` back to Y for the next layer.

So the hidden dim ping-pongs **Y → (QKV) → X-feature → (o_proj contracts X) → Y →
(up/gate) → X-ffn → (down contracts X) → Y**. Projections that contract the
model hidden dim reduce along **Y**; projections that contract a head/feature/ffn
dim reduce along **X**; head_dim (q/k norm, score) is kv-head-scoped **X**; seq is
**Y**.

### K vs V cache asymmetry (`process_kv`, `decode.csl:968-1002`)

Same logical `[b][kv_dim_per_pe][seq]` data, stored transposed to match each
consumer's GEMV stride:

- **K**: `[b][kv_dim_per_pe][seq_len_per_pe]` (feature-major). Write is
  **strided**: dest base `&ptr_XKCache[b*kv_dim_per_pe*seq_len_per_pe + iter_num]`,
  extent `kv_dim_per_pe`, **stride `seq_len_per_pe`** (`decode.csl:980-984`) —
  drops the token's `kv_dim_per_pe` features down column `iter_num`.
  `score_matvec` reads it advancing `right_matrix` by `seq_len_per_pe` per
  K-position (`:1041`).
- **V**: `[b][seq_len_per_pe][kv_dim_per_pe]` (seq-major). Write is
  **contiguous**: dest base `…[iter_num*kv_dim_per_pe]`, extent `kv_dim_per_pe`,
  **stride 1** (`decode.csl:993-997`) — one whole V row. `output_matvec` reads
  advancing `right_matrix` by `kv_dim_per_pe` per K-step (one V row, `:1147`).

Host prefill seeding matches: K uses `swap_xy=True` + `_reshard_K_dim(axis=0)`
(X owns kv_dim rows, Y owns seq) (`launch.py:1603-1605`); V uses plain
`shard_3d` (`:1607`). Under `kv_transfer=1` (this config) the host cache seed is
**zero** (`:1602`) and the prefill region fills it on-device via
`kv_ingress` (`decode.csl:1424-1463`); the received tile arrives already in decode
slab order — K pair-interleaved `[b][kv_dim_per_pe][plen]`, V `[b][plen][kv_dim_per_pe]`.

### fp32 shadow buffers

Matmul partials accumulate fp32 (`@fmachs`) and the cross-PE allreduce runs fp32
for HF parity, cast back to bf16 before the elementwise ops:
`QKV_f32:[16]f32` (`:610`), `score_f32:[4]f32` (`:630`),
`scratch_dim_a_f32/b_f32:[8]f32` (`:551-552`, o_proj/output/h2),
`ffn_up_gate_f32:[48]f32` (`:646`), `X_fp32_buf:[8]f32` /
`qknorm_sum_g_f32:[3]f32` (RMS/QK-Norm sumsq). SiLU is a fp32 SIMD-4 degree-6
polynomial with its own f32 scratch pinned to D-cache (`decode.csl:671-690`).

### West/east strips (`decode_strip.csl`; dispatch `decode.csl:1465-1542`)

Each row region has a west (lcl_x=0) and east (lcl_x=513) strip column, shape
uniform `Pw+2`. Only strips with real inter-region traffic run the K-pipe relay
(`strip_realness`, `launch.py:203`); "fake" strips only forward
pre_embed_x/result colors via compile-time paint. A **real strip PE holds ONE
row-shard of Z** in transit between block columns:

| Tensor | Sharding | Local symbol & shape | Dim order slow→fast | Op |
|---|---|---|---|---|
| Z row-shard (K-pipe) | one PE = one (pipe k, own-cell) shard of the inter-block Z hop | `strip_buf: [bsz*dim_per_pe=8]@fp16` (`decode_strip.csl:31`) | `[batch, dim_per_pe]` | inter-block Z relay across the block-column seam |

The K-pipe runs along Y with `KPIPE_K`=8 pipes and `KPIPE_M_PER_PIPE`=32
own-cells/pipe (`decode.csl:1319`); pipe `k = ly mod 8`, own-index `i = ly div 8`
(`decode.csl:1501-1502`). Sender own_i forwards `i·B` upstream wavelets; receiver
own_j forwards `(M−1−j)·B` (`decode_strip.csl:114-124`).

### KV-profiler reporter

One block PE per decode build — east-most block col (rep_bx=Pw=512), south-most
row (rep_by=255) of the **last** region — sets `is_kv_prof_reporter=1`
(`launch.py:1291-1293`) and streams its `kv_ingress` cycle count
`kv_prof_burst_dec: [4]u32 = [C, done, pad, pad]` (`decode.csl:1410`) east on
`kv_prof_out_color` to the kv_prof_mux forwarder.

---

## Module: ht_tail (`src/decode/ht_tail.csl`; built `launch.py:1727-1957`)

Region **`HT_WIDTH_tail`(=128) cols × `P_BLOCK_SIZE`(=256) rows**, at
(ht_tail_x=3, PLACE_Y + last_row·256). Final `LlamaModel.norm` + `lm_head` +
top-K + on-chip categorical sampling. **Orientation is transposed vs the
embedding head: vocab → X, dim → Y.**

| Tensor | Sharding | Local symbol & shape | Dim order slow→fast | Op / contract axis |
|---|---|---|---|---|
| `lm_head` W (tied to `W_E`, seed 2024) | **vocab → X** (V_per_pe_x=1188 rows/PE); **dim → Y** (dim_per_pe=8) | `lm_head_tile: [V_per_pe_x*dim_per_pe = 9504]@fp16` (`ht_tail.csl:91`) | `[vocab_row(1188), dim(8)]` row-major, vocab-outer/dim-inner (`launch.py:1916-1917`) | lm_head matvec; **contracts dim (Y)** |
| final `norm` γ | dim → Y; **replicated across X** (all 128 cols) | `W_final_norm_tile: [dim_per_pe=8]@fp16` (`ht_tail.csl:103`) | `[dim_per_pe]` | final RMSNorm on Z |
| Z slice (lm_head input) | dim → Y | `z_slice_buf: [bsz*dim_per_pe=8]@fp16` (`ht_tail.csl:92`) | `[batch, dim_per_pe]` | RMSNorm→matvec (in-place) |
| logits partials | vocab → X; fp32 | `partials_buf: [bsz*V_per_pe_x = 1188]f32` (`ht_tail.csl:95`) | `[batch, V_per_pe_x]` | Y-reduce (no bcast) |
| top-K (value,id) | replicated on root row after X merge | `topk_val: [TOP_K*bsz+VAL_PAD = 2]@fp16`, `topk_arg: [TOP_K*bsz=1]i32` (`ht_tail.csl:231-232`) | **round-outer/batch-inner `r*bsz + b`** (`ht_tail.csl:230,249`) | X 2-phase merge-reduce → sampling |
| sampled token | root-row, X-broadcast | `pred_token_buf: [bsz]i32` (`ht_tail.csl:225`) | `[batch]` | north→HT_head tok_bcast, south→mux |

- **Compute** (`ht_tail.csl:329-337`): `partials[V_per_pe_x] = lm_head_tile @
  z_slice` — left = `z_slice` (dim_per_pe on this Y-PE), right = `lm_head_tile`
  (`dim_per_pe × V_per_pe_x`), `@fmachs` fp32. Contracts `dim_per_pe`, the Y
  shard.
- **The Y allreduce contracts dim with NO broadcast** (`ht_tail.csl:6,647`):
  the 2-phase Y reduce leaves the full logits only on the `root_2nd_phase`(=136)
  row (there is no broadcast-back leg, unlike the block reduces). That root row
  then does local top-K, the **X-axis** 2-phase merge-reduce over
  `HT_WIDTH_tail`=128 columns (`root_2nd_phase_x`=72, reusing the reduce colors
  via runtime X/Y route reconfig fenced by `tail_xready_color`), then categorical
  sampling → next token.
- **Vocab padding mask**: column `x_local` owns vocab ids
  `[x_local·1188, (x_local+1)·1188)`; the dummy ids `≥151936` sit in the top
  columns' trailing local indices, masked to `NEG_SENT` before top-K via
  `vocab_pad_count` (`launch.py:1755-1759`, `ht_tail.csl:27,823-838`).
- **Egress**: only the root-row east-most PE (`tail_my_x_local==127`) emits the
  replicated global top-K south to the mux (`ht_tail.csl:187-208`): per step
  `TOP_K*bsz` f16 values (`@fmovh`) + `TOP_K*bsz` i32 ids + `bsz` sampled tokens,
  padded to even (`south_wlts_per_step`=4). North it emits the sampled token on
  `tok_bcast_color` to HT_head (skipped on the last step).

---

## Module: logits mux (`src/decode/mux.csl`; built `launch.py:1971-2016`)

Region **`HT_WIDTH_tail`(=128) cols × 1 row**, one row south of HT_tail's bottom,
placed at (HT_HEAD_X=3, mux_y+256). Only the east-most PE (`is_last_pe`) is
active — the global top-K is replicated across the tail root row, so a single
column carries it.

| Tensor | Sharding | Local symbol & shape | Dim order slow→fast | Op |
|---|---|---|---|---|
| per-step top-K blob | 1 active PE (east-most); rest inert | `blob: [N = wlts_per_step = 4]u32` (`mux.csl:13`) | `[val | arg | tok | pad]` per step | forward north→host (Edge.RIGHT) |
| TSC tail burst | same | `tsc_blob: [8]u32` (`mux.csl:29`) | `[start×3, pad, end×3, pad]` | one-shot benchmark drain after last step |

- Pure relay: drains one step's blob from the north (`in_color`) and forwards it
  east to the host stream (`host_color`), `MAX_OUTPUT_LEN`=256 times, then drains
  the piggybacked 8-u32 TSC burst (`mux.csl:36-56`). No compute, no reshard.

---

## Module: kv_prof_mux (`src/kv_prof_mux.csl`; built `launch.py:1310-1332`)

Region **1 col × `P_BLOCK_SIZE`(=256) rows**, placed east of the last block
region, bottom PE aligned with the reporter's south-most row. One-shot host-I/O
adaptor turning the reporter block PE's east egress into a 1-PE host stream (host
ports must be 1-PE).

| Tensor | Sharding | Local symbol & shape | Dim order slow→fast | Op |
|---|---|---|---|---|
| KV-profiler burst | 1 active PE (bottom `is_last_pe`); rest inert | `blob: [N=4]u32` (`kv_prof_mux.csl:17`) | decode = `[C, done, pad, pad]` | drain from block region (WEST→RAMP), forward south to host |

- Pure relay (`kv_prof_mux.csl:28-34`): drains the reporter's 4-u32 burst and
  re-emits it out a 1-PE `Edge.BOTTOM` host port. Edge-agnostic; the same file
  serves both halves.

---

## Axis-role summary (X = fabric-X `local_px`, Y = fabric-Y `local_py`)

| Pipeline stage | Fabric X meaning | Fabric Y meaning | Reduce axis (contract) |
|---|---|---|---|
| **x_demux** (1×256) | (single column) | hidden dim shard (dim_per_pe=8/PE) | none (scatter) |
| **ht_head** (128×256) | hidden dim (2·dim_per_pe/col, diag-pair) | vocab shard (V_per_pe_y=594/PE) | none (embedding gather) |
| decode: **X_tile / RMSNorm** | replicated (post X-bcast) | **model hidden dim** (8/PE) | RMSNorm sumsq → **Y** |
| decode: **QKV projection** | — (input replicated) | input hidden dim | **Y** (contract hidden) |
| decode: **post-QKV Q/K/V, q/k-norm, RoPE, score** | **head/feature dim** (kv-head bands of `pes_per_kv_head`=32) | **sequence** (token t → row t mod 256; `seq_len_per_pe`=2 rounds) | head_dim → **X kv-head-scoped**; seq (softmax) → **Y** |
| decode: **output = score·V** | head/feature dim | sequence | **Y** (contract seq) |
| decode: **o_proj** | attention head dim (input) | hidden dim (output) | **X** (contract head dim) → hidden back on Y |
| decode: **rmsnorm_z, up/gate** | replicated / ffn (output) | hidden dim (input) | **Y** (contract hidden) |
| decode: **down_proj** | ffn dim (input) | hidden dim (output) | **X** (contract ffn) → hidden back on Y |
| **ht_tail** (128×256) | **vocab shard** (V_per_pe_x=1188/PE); top-K merge along X | **hidden dim** (8/PE) | lm_head → **Y (no broadcast)**; top-K merge → **X** |
| **logits mux** (128×1) | 1 active PE (top-K replicated) | (single row) | none (relay) |

Cache orientation summary: **K = `[b][kv_feature][seq]` (feature-major, strided
write), V = `[b][seq][kv_feature]` (seq-major, contiguous write)** — both with
kv_feature on X and seq on Y, transposed relative to each other only to match
their GEMV strides.

---

## Notes / observed inconsistencies

1. **Stale route_calc header.** `route_calc.csl:5-6` says "seq_len + KV-head
   bands along X". In the decode kernel seq is contracted along **Y**
   (`output_matvec_mult` uses `all_reduce_bsz_dim(local_py,…)`; softmax reduces
   along Y). What actually lives on X is the head/feature/ffn dim (o_proj,
   down_proj, q/k-norm, score). The "seq_len along X" phrasing is misleading for
   decode; only "KV-head bands along X" is accurate.
2. **`kv_profile` reporter double-init dance.** The reporter defers its TSC
   egress until the OQ7 empty-queue handler fires post-ingress
   (`comm_pe.csl:1321-1336`, `decode.csl:1565-1575`) — intentional (avoids
   mis-routing a residual KV tile) but non-obvious; flagged only as a
   subtlety, not a bug.
3. **Config vs code comment mismatch (not a bug).** The `launch.py:287-306`
   commentary describes a *different* device config (`P_BLOCK_SIZE=128`,
   `Pw=256`, vocab pad to 152064 = lcm(128,256)). The actual
   `test_device_2x2blk_kv_prof.json` gives `P_BLOCK_SIZE=256`; the derived
   constants above are computed for the real config. Both land on
   `vocab_pad=152064`, but via different multiples (256 vs 128), so the comment's
   arithmetic does not literally apply to this config.
4. **HT_X_OFFSET=0 here** ⇒ every ht_head column is an active embedding column;
   the "west relay-only columns" described in `launch.py:502-510` /
   `ht_head.csl:14-17` are empty in this config (they exist only when
   `HT_WIDTH_tail > HT_WIDTH_head`).
