# qwen3_1p7b-e2e — On-chip data layout of the PREFILL half (+ relay seam)

Scope: the bottom (prefill) half of `models/qwen3_1p7b-e2e`, plus the passive
relay seam that bridges prefill → decode. Decode-half internals are out of scope
except where the prefill→decode KV contract requires them.

Ground truth config: `model_config/test_device_2x2blk_kv_prof.json`
(real Qwen3‑1.7B dims). All file:line citations are to
`models/qwen3_1p7b-e2e/…` unless noted.

**Rotation up front (the single most important framing).** Prefill is *rotated
90° vs decode*: **sequence is sharded along the X axis, hidden/kv dim along the
Y axis** (`src/prefill/prefill.csl:4-7`, `src/prefill/route_calc.csl:3-10`). Per-PE
storage is still **feature-major / seq-minor** — every activation matrix is
`[feature, seq]` indexed `f*reduce_len + s`, `reduce_len = bsz*seq_len_per_pe`
(`prefill.csl:17-20,165`). Only the *mesh axis* flipped, not the local memory
order. Consequences traced throughout:

- All RMSNorm / QK‑Norm sums contract over *dim*, which is along Y → **norm
  reduces run on the Y axis** (`route_calc.csl:3-10`, `comm_pe.csl:4-6`).
- MeshGEMM contracts over dim/ffn (Y‑sharded) → **left activation hops along Y,
  right weight hops along X** (`comm_pe.csl:63-67,600-606`).
- GQA runs per kv‑head **Y band**; the score reduce is a Y‑band reduce to a
  cycling root; the Score×V ring shifts score band‑local along Y and V full‑P
  along X (`prefill.csl:949-955`).
- The inter‑block serpentine shuttle moves each PE's `[dim,seq]` tile to the
  same-local-coord PE one block over.

With this config `seq_len_per_pe = 1` and `reduce_len = 1` (see below), so the
seq/`s` sub-index collapses to a single element; the `[feature, seq]` formula
still holds but the seq extent is 1. This is called out where it matters.

---

## Derived constants (test_device_2x2blk_kv_prof.json)

`build_prefill` uses `seq_len = PREFILL_LEN = 256` (not MAX_SEQ_LEN) as the
sharded sequence length (`launch.py:2076`). No padding path runs here —
`build_prefill` asserts exact divisibility (`launch.py:2096-2097`), unlike
`build_decode` which pads.

| Constant | Value | Derivation (source) |
|---|---|---|
| Pw, Ph | 512, 512 | config |
| P_X_BLOCK_NUM, P_Y_BLOCK_NUM | 2, 2 | config |
| P_BLOCK_SIZE (P) | **256** | Pw/P_X_BLOCK_NUM (`launch.py:2065`) |
| N_blocks | **4** | P_X·P_Y (`launch.py:2066`) |
| dim | 2048 | config |
| head_dim | 128 (never sharded) | config; scalar `head_dim_total` |
| kv_dim | **1024** | n_kv_heads·head_dim = 8·128 (`launch.py:2094`) |
| ffn_dim | 6144 | config |
| n_heads / n_kv_heads | 16 / 8 | config |
| seq_len (prompt) | **256** | = PREFILL_LEN (`launch.py:2076`) |
| **dim_per_pe** | **8** | dim/P = 2048/256 (`launch.py:2098`) |
| **kv_dim_per_pe** | **4** | kv_dim/P = 1024/256 (`launch.py:2099`) |
| **seq_len_per_pe** | **1** | seq_len/P = 256/256 (`launch.py:2100`) |
| **ffn_dim_per_pe** | **24** | ffn_dim/P = 6144/256 (`launch.py:2101`) |
| **reduce_len** (Mt) | **1** | bsz·seq_len_per_pe = 1·1 (`launch.py:2102`, `prefill.csl:165`) |
| **gqa_group_size** (g) | **2** | dim_per_pe/kv_dim_per_pe = 8/4 (`launch.py:2104`); = n_heads/n_kv_heads ✓ |
| group_num | 16 | config |
| pe_num_per_group | 16 | P/group_num (`launch.py:2112`) |
| root_1st_phase | 8 | pe_num_per_group/2 (`launch.py:2113`) |
| **root_2nd_phase** | **136** | (group_num/2)·pe_num_per_group + root_1st = 8·16+8 (`launch.py:2114`) |
| **pes_per_kv_head** | **32** | P/n_kv_heads = 256/8 (`launch.py:2116`) |
| kv_head_root | 16 | pes_per_kv_head/2 (`launch.py:2117`) |
| **pes_per_q_head** | **32** | = pes_per_kv_head (Q is kv‑interleaved) (`launch.py:2121`) |
| q_head_root | 16 | = kv_head_root (`launch.py:2122`) |
| **n_kv_blocks** | **8** | P/pes_per_kv_head = 256/32 (`prefill.csl:173`) |
| **fused_qkv_Nt** | **16** | dim_per_pe + 2·kv_dim_per_pe = 8+8 (`prefill.csl:166`) |
| **upgate_Nt** | **48** | 2·ffn_dim_per_pe (`prefill.csl:178`) |
| n_pairs_q / n_pairs_k | 4 / 2 | dim_per_pe/2, kv_dim_per_pe/2 (`prefill.csl:179-180`) |
| rope_hp (pairs per K band) | 2 | kv_dim_per_pe/2 (`prefill.csl:353`) |
| attn_tile | 1 | seq_len_per_pe² (`prefill.csl:174`) |
| attn_score_size | 2 | g·bsz·attn_tile = 2·1·1 (`prefill.csl:175`) |
| attn_vec_size | 2 | g·bsz·seq_len_per_pe (`prefill.csl:176`) |
| **kv_tile_size** | **4** | kv_dim_per_pe·reduce_len = 4·1 (`prefill.csl:177`) |
| score_total | 16 | n_kv_blocks·attn_score_size = 8·2 (`prefill.csl:956`) |
| **max_layers_per_block** (L) | **7** | distribute_layers(28,4)=[7,7,7,7] (`launch.py:2087-2088,155-181`) |
| layer_counts / offsets | [7,7,7,7] / [0,7,14,21] | `distribute_layers` |
| bsz | 1 | config |
| HT_WIDTH_head | 128 | P/2 (`launch.py:2637`) |
| V_per_pe_head | 1187 | vocab/HT_WIDTH_head = 151936/128 (`launch.py:2639`) |
| head_shift_len | 9497 | V_per_pe_head·dim_per_pe + 1 = 1187·8+1 (`launch.py:2640`) |
| ids_per_head_col | 2 | 2·reduce_len (`launch.py:2641`) |
| HT_WIDTH_tail | 128 | config |
| V_per_pe_x (tail) | 1187 | vocab/HT_WIDTH_tail = 151936/128 (`launch.py:2137`) |
| HT_LM_HEAD_K | 9496 | V_per_pe_x·dim_per_pe = 1187·8 (`launch.py:2813`) |
| pe_num_per_group_x | 16 | min(16, HT_WIDTH_tail/2) (`launch.py:2145`) |
| root_1st_phase_x / 2nd_x | 8 / 72 | (`launch.py:2149-2150`) |
| total_y_pes | 512 | = Ph, N‑shift step count (`launch.py:2379`) |
| prefill_len_per_pe (decode) | 1 | PREFILL_LEN/P = 256/256 (decode `kv_in` sizing) |

Serpentine order (2×2) = `(0,0)→(1,0)→(1,1)→(0,1)`
(`launch.py:2326-2333`, `pipeline_index`). Hops: EAST, SOUTH, WEST. First block =
`(0,0)` (top-left, `is_x_receiver`); last block = `(0,1)` (west, `is_z_sender`).
Each of the 4 blocks runs 7 layers.

Fabric geometry (`launch.py:2929-2941,2180-2184,2755-2756`):
`PLACE_X=132`, decode rows y∈[1,512], **relay** rows y∈[513,514] (`Pw×2`),
prefill demux row y=514, prefill block region origin `(132,515)` spanning
`512×512`, `pf_ht_head`/`pf_ht_tail`/`pf_logits_mux` in the west band at x=4.

---

## Module: pf_demux (`src/prefill/demux.csl`; built `launch.py:2704-2743`)

Role: distribute the host token-id sequence along X (the sequence axis) into
HT_head. A `HWh×1 = 128×1` store-and-forward chain (NOT `P×1`; width = HT_head
width = P/2). PE `lx` peels its column's `ids_per_pe = 2·reduce_len = 2` i32 ids,
forwards the rest EAST, and emits its own 2 ids SOUTH on `tok_bcast_color` (id 7)
into the HT_head column below (`demux.csl:1-6`).

| Tensor | Sharding (X/Y/repl/bank) | Local symbol & shape | Dim order slow→fast | Op it feeds |
|---|---|---|---|---|
| token ids | **X = seq/block-col** (1 col, 128 PEs along X); no Y | `own_buf: [OWN=2]u32` (`demux.csl:24`) | `[id]` contiguous, FIFO peel then forward (`demux.csl:42-45,58-76`) | token embedding lookup in HT_head |
| kickoff sentinel | PE 0 only | `kickoff_buf:[1]u32` (`demux.csl:35`) | scalar | forward-start TSC anchor (→ HT_tail is_tsc_pe) |

Host transform: `tok_seq = rng.integers(0,vocab,(P, reduce_len))` reshaped
`(HWh, ids_per_head_col)` then `.view(u32)` (`launch.py:2742-2743`). Head col `lx`
owns block cols `2lx, 2lx+1` (each block col contributes `reduce_len` ids).
Two parity-alternating chain colors (A even hops / B odd hops) avoid adjacent-PE
color conflict (`launch.py:2723-2731`). Streamed W→E from a single host input
port on Edge.LEFT (`launch.py:2732-2739`).

---

## Module: pf_ht_head (`src/prefill/ht_head.csl`; built `launch.py:2646-2701`)

Role: **token embedding LUT** (Qwen3 `embed_tokens`) via an X-axis vocab
rotation, then eastward X‑handoff of the embedded hidden state into block 0.
Region = `HT_WIDTH_head × P = 128 × 256`, placed at `(4, 515)`, abutting block
0's west edge. The `P_BLOCK_SIZE` *param* here is set to `HWh=128` (the rotation
cycle length), NOT the block size (`launch.py:2648`).

Per-PE topology: **X column = seq/output slot** (each of 128 cols owns TWO block-col
seq chunks, `2·reduce_len=2` ids/slots) and, at any rotation step, ONE rotating
vocab chunk; **Y row = embedding dim** (each row owns `dim_per_pe=8` features of
the embedding).

| Tensor | Sharding (X/Y/repl/bank) | Local symbol & shape | Dim order slow→fast | Op it feeds |
|---|---|---|---|---|
| W_E (embedding matrix) rotating chunk | vocab-rows→X (`V_per_pe_head=1187` rows/col), dim-cols→Y (`dim_per_pe=8`/row); the vocab chunk **rotates** across X over 128 hops | `we_buf_0/we_buf_1: [SHIFT_LEN=9497]@fp16` double-buffered (`ht_head.csl:71-72`) | `[V_per_pe(1187)][dim_per_pe(8)]` row-major + 1 trailing `chunk_col` tag word at `[WE_LEN]` (`ht_head.csl:53-54,134-149`) | embedding lookup (compare id∈chunk range → copy W_E row) |
| token ids | replicated ‖ Y (N→S multicast fans one column's ids down all rows) | `token_id_buf: [2·reduce_len=2]i32` (`ht_head.csl:62`) | `[slot]` | compare against chunk vocab range |
| embedded X out | seq→X (chunk c → block col `2lx+c`), dim→Y | `X_tile: [OWN_LEN = 2·dim_per_pe·reduce_len = 16]@fp16` (`ht_head.csl:64`) | **chunk-major** `[2][dim_per_pe][reduce_len]`, `dst = (s/reduce_len)·dim_per_pe·reduce_len + s%reduce_len` (`ht_head.csl:143-146`) | X handoff → block 0 (`x_chain`) |

Host transform (`launch.py:2691-2700`): `W_E_full = randn(vocab,dim)*0.1` bf16;
PE(gx,gy) is seeded `we_buf_0[gx*head_shift_len .. +WE_LEN-1] =
W_E_full[gx*V:(gx+1)*V, gy*dim_per_pe:(gy+1)*dim_per_pe].reshape(-1)`, trailing
word 0. `we_buf_0` doubles as the host-loaded initial chunk *and* the rotation
buffer (a third `W_E_tile` copy would not fit 48 KB SRAM at P=256, `ht_head.csl:68-71`).

Algorithm: `HWh` two-hop y-channel rotation steps; at each step `compare_record`
resolves any token id landing in the resident chunk's `[chunk_base, chunk_hi)`
range into `X_tile` (`ht_head.csl:129-175`). **x_chain handoff**: after rotation,
an ordered concat chain east on parity-alternating colors 14/15 — PE `lx`
forwards the `lx` upstream chunks (`fwd_len = lx·OWN_LEN`) then emits its own 2
chunks; the east edge carries `[chunk 0 … chunk P-1]` in seq order and block 0's
cols peel their own (`ht_head.csl:177-214`, `launch.py:2680-2685`,
`prefill.csl:661-691`). Op: Qwen3 `embed_tokens` → residual stream seed for
block 0 (`X_tile`).

---

## Module: prefill block region (`src/prefill/prefill.csl`; built `launch.py:2338-2595`)

ONE `Pw×Ph = 512×512` code region (`pf_block`) spanning the whole fabric; logical
`P×P=256×256` blocks found via block-local `lx/ly` from fabric coords minus
`region_origin` (`prefill.csl:8-15`, `comm_pe.csl:210-247`). Each of the 4 blocks
runs its `layers_in_this_block = 7` layers, weights banked by layer
(`set_layer(l)` repoints working pointers, `prefill.csl:231-240`), then shuttles
its `[dim,seq]` output to the serpentine-next block.

**Mesh sharding of every per-PE tile:** X = seq (`px` owns `seq_len_per_pe=1`
token), Y = dim/kv_dim (`py` owns `dim_per_pe=8` / `kv_dim_per_pe=4` features).

### Weight banks (host-preloaded bf16, banked by layer; `prefill.csl:206-219`)

All are `[max_layers_per_block(7) * per_layer_size]` and set via `sym_all`
(`launch.py:2286-2296,2443-2454`), which fills a `[Ph, Pw·per_pe]` array keyed on
block-local `(lx,ly)` and calls `set_symbol_all`. Fills are block-local (identical
across the 4 blocks): norms = ones, matmul weights = fresh `randn*0.1` (mock,
numerically meaningless).

| Tensor | Sharding | Local symbol & shape | Dim order slow→fast | Op / contraction / collective |
|---|---|---|---|---|
| input_layernorm γ | dim→Y (`dim_per_pe`/row); replicated ‖ X; banked by layer | `rms_w_x_bank:[L·dim_per_pe]@fp16` (`prefill.csl:206`) | `[layer][feature]`; used as `gain_ptr[d]` (`prefill.csl:308`) | RMSNorm(X), contracts dim over **Y** → `all_reduce_full` (`prefill.csl:296`) |
| post_attention_layernorm γ | same as above | `rms_w_z_bank:[L·dim_per_pe]` (`prefill.csl:207`) | `[layer][feature]` | RMSNorm(Z), Y `all_reduce_full` (`prefill.csl:1223-1224`) |
| q_norm γ | dim→Y; banked | `q_norm_w_bank:[L·dim_per_pe]` (`prefill.csl:208`) | `[layer][feature]`, `l_q_norm_w[d]` (`prefill.csl:932`) | q_norm over head_dim → **Y band** `all_reduce_q_band` / `attn_vec_allreduce` |
| k_norm γ | kv_dim→Y; banked | `k_norm_w_bank:[L·kv_dim_per_pe]` (`prefill.csl:209`) | `[layer][kv_feature]` | k_norm over head_dim → **Y band** `all_reduce_k_band` (`prefill.csl:330,937`) |
| W_qkv (fused q/k/v_proj) | contraction dim→Y, output fused_qkv→(matmul) | `W_qkv_bank:[L·dim_per_pe·fused_qkv_Nt]` = `[L·8·16]` (`prefill.csl:210`) | `[layer][Kt=dim_per_pe][Nt=fused_qkv_Nt]` (right-matrix order, `comm_pe.csl:512`) | q/k/v_proj MeshGEMM, contracts **dim (Y)** |
| W_o (o_proj) | `W_o_bank:[L·dim_per_pe·dim_per_pe]`=`[L·8·8]` (`prefill.csl:211`) | `[layer][Kt=dim_per_pe][Nt=dim_per_pe]` | o_proj MeshGEMM, contracts dim (Y) |
| W_upgate (fused gate/up_proj) | `W_upgate_bank:[L·dim_per_pe·upgate_Nt]`=`[L·8·48]` (`prefill.csl:212`) | `[layer][Kt=dim_per_pe][Nt=upgate_Nt]` | gate|up MeshGEMM, contracts dim (Y) |
| W_down (down_proj) | `W_down_bank:[L·ffn_dim_per_pe·dim_per_pe]`=`[L·24·8]` (`prefill.csl:213`) | `[layer][Kt=ffn_dim_per_pe][Nt=dim_per_pe]` | down MeshGEMM, contracts **ffn (Y)** |
| RoPE cos/sin (Q) | pair→Y (within-head), token→X; NOT banked (layer-invariant) | `freqs_q_cos/sin:[n_pairs_q·reduce_len]=[4]@fp16` (`prefill.csl:216-217`) | `[pair][token]`, `i*reduce_len+m` (`prefill.csl:368-377`) | RoPE θ=1e6 on Q (`p_rope_q`) |
| RoPE cos/sin (K) | pair→Y, token→X; not banked | `freqs_k_cos/sin:[n_pairs_k·reduce_len]=[2]@fp16` (`prefill.csl:218-219`) | `[pair][token]` | RoPE on K (`p_rope_k`) |

RoPE host fill (`launch.py:2298-2324,2451-2454`): angle `pos·θ^(-2j/head_dim)`,
`pos = lx·seq_len_per_pe + m%seq_len_per_pe` (prompt starts at position 0 — X
shards seq). **Q freqs use `q_interleaved=True`**: per-PE Q is g slots of
`kv_dim_per_pe`, within-head offset `(ly%pes_per_kv_head)·kv_dim_per_pe`
(`launch.py:2312-2314`). K freqs use the plain within-head map
`(ly·kv_dim_per_pe)%head_dim`.

### Activations / intermediates (`prefill.csl:242-252`)

All `[feature, seq]`, index `f*reduce_len+s`; here `reduce_len=1`. `[feature,seq]`
**holds** for every entry below (confirmed against the DSD extents and the
`f*reduce_len` strides).

| Tensor | Sharding | Local symbol & shape | Dim order slow→fast | Op |
|---|---|---|---|---|
| running hidden X | dim→Y, seq→X | `X_tile:[dim_per_pe·reduce_len=8]@fp16` (`prefill.csl:243`) | `[feature][seq]` | residual stream (input to each layer / RMSNorm) |
| normalized X | dim→Y | `X_norm:[8]` (`prefill.csl:244`) | `[feature][seq]` | left operand of QKV MeshGEMM |
| fused Q\|K\|V | fused_qkv→Y (after matmul), seq→X | `XQKV:[fused_qkv_Nt·reduce_len=16]@fp16` (`prefill.csl:245`) | `[feature][seq]`; Q at `XQ_off=0`, K at `XK_off=dim_per_pe·reduce_len=8`, V after | q/k/v; **Q host-interleaved**: g=2 head slots of `kv_dim_per_pe=4` (`prefill.csl:169-172,1059`) |
| GQA output | dim→Y | `attn_out:[8]` (`prefill.csl:246`) | `[feature][seq]` (per head h: `kv_dim_per_pe` feats, `out_acc_f32[h*kv_tile_size+…]`) | o_proj input |
| o_proj out | dim→Y | `h1:[8]` (`prefill.csl:247`) | `[feature][seq]` | Z = X + h1 |
| attn residual | dim→Y | `Z:[8]` (`prefill.csl:248`) | `[feature][seq]` | post_attention RMSNorm input |
| normalized Z | dim→Y | `Z_norm:[8]` (`prefill.csl:249`) | `[feature][seq]` | left operand of up/gate MeshGEMM |
| gate\|up | upgate→Y | `z_upgate:[upgate_Nt·reduce_len=48]` (`prefill.csl:250`) | `[feature][seq]`; gate `[0:ffn·rl]`, up `[ffn·rl:]` (`prefill.csl:882-883`) | SwiGLU |
| silu(gate)·up | ffn→Y | `z3:[ffn_dim_per_pe·reduce_len=24]` (`prefill.csl:251`) | `[feature][seq]` | down_proj input |
| down out | dim→Y | `h2:[8]` (`prefill.csl:252`) | `[feature][seq]` | X = Z + h2 (next layer) |

Norm scratch `sq_f32/local_sum_f32/inv_f32/col_f32` are f32 (`prefill.csl:254-259`);
RMSNorm is fp32-internal for HF parity (`prefill.csl:282-312`).

### Per-layer phase machine (`prefill_struct`, `prefill.csl:1261-1276`)

`rmsnorm_x → qkv_matmul → qk_norm_q → qk_norm_k → rope_q → rope_k(+cache_kv) →
attn_score(A/B/C) → o_matmul → z_residual → rmsnorm_z → upgate_matmul → swiglu →
down_matmul → ffn_residual/next_layer`. After the last layer: `done_flag=1`, then
serpentine shuttle out (`enter_source_shuttle`) OR z-emit (last block), then
`start_kv_transfer` (`prefill.csl:1238-1258`).

### MeshGEMM (the subtle part) — `setup_matmul` / `two_hop_comm` / `out_acc_f32`

`C[Mt,Nt] = X[Mt,Kt] @ W[Kt,Nt]`, `Mt=reduce_len`, `Kt=dim_per_pe`(or
`ffn_dim_per_pe`), `Nt=fused_qkv_Nt / dim_per_pe / upgate_Nt`
(`prefill.csl:521-530`). Left matrix (`X_norm`, stored `[Kt,Mt]=[feature,seq]`) is
MeshGEMM's **native left order** — no transpose (`prefill.csl:19-20`). Right
matrix (`W`) is `[Kt,Nt]`. The full contraction over `dim` (Y‑sharded,
`P_BLOCK_SIZE=256` shards) is realized by `P_BLOCK_SIZE` systolic steps.

- **Skew / `mm_root`**: prefill keeps only the FORWARD systolic channel and
  emulates the reference's bidirectional skew with the forward-only offset
  formula `total_shift_step = if lpx==0 → 0; else if lpx even → P - lpx/2; else
  (lpx+1)/2` (`prefill.csl:534-543`). `mm_root = P_BLOCK_SIZE` (full ring) covers
  the offset budget. `left_matrix_shift` runs the skew hops on the **x channel**
  (left channel, queue 2), reusing the systolic step channel (no dedicated
  x_shift, `comm_pe.csl:64-67,690-709`).
- **`two_hop_comm` step loop** (`comm_pe.csl:711-741`, driver `prefill.csl:572-601`):
  per step, **left (activation) hops along Y on the x-colors** (host-painted N/S,
  ids 6/7/8, keyed on `ly`, `launch.py:2526,2545-2554`); **right (weight) hops
  along X on the y-colors** (host-painted E/W, ids 9/10/11, keyed on `lx`,
  `launch.py:2527,2535-2543`). Each step the PE `@fmachs` its resident `[Kt]`
  slice into `out_acc_f32` over `mm_Kt` inner iters.
- **Accumulation**: `out_acc_f32:[max_out_buf]f32` cleared to 0 before the P steps
  (`prefill.csl:566-568`), accumulated across all steps, then `@fs2h` cast f32→bf16
  into the output activation (`prefill.csl:593-600`).

Output feature (qkv/dim/upgate) ends sharded along Y, seq along X — matching the
next stage's expected layout. Collective: MeshGEMM (systolic), NOT a named
all_reduce; the contraction axis is dim/ffn (Y).

### Attention (stages A / B / C) — the subtle part

GQA runs **per kv-head Y band** (`pes_per_kv_head=32` rows = one kv head =
`gqa_group_size=2` Q heads + one K/V copy, `prefill.csl:169-172`). `n_kv_blocks=8`
key-block slots per band PE.

**Stage A — `score = Q@Kᵀ`** (`prefill.csl:1073-1087`, `p_attn_score`):
K does `P_BLOCK_SIZE` X-hops on the **right (y) channel** (`attn_right_hop`,
`comm_pe.csl:583-598`); V re-hops separately in stage C. Per hop the band's f32
partial tile reduces over the kv-band Y rows to a **CYCLING root** via
`attn_score_reduce` (`comm_pe.csl:411-454`): at hop `n` the partial for key block
`orbX[n][lx]` reduces to band-PE `attn_root_seq[n]` and is stored at slot
`attn_slot_seq[n]` (counter `c=(posX[lx]+n)%P` → root=`store_pe[c%pkh]`,
slot=`c/pkh`). No broadcast — score stays with the root.

- `attn_tmp_f32:[attn_score_size=2]f32` — per-step partial `[b][h][k][q]`
  (`prefill.csl:958,1053-1071`).
- `score_f32:[score_total=16]f32` — counter-stored, `[slot][b][h][k][q]`,
  `score_f32[blk*attn_score_size + (h*sq+k)*sq + q]` (`prefill.csl:959,1005-1007`).
  **This is an attention score layout, NOT `[feature,seq]`** — the `[feature,seq]`
  rule does not apply to score/mask tensors.

**Stage B — softmax** (`p_attn_softmax`, `prefill.csl:1092-1116`): alpha scale
`1/√head_dim`, add host `attn_mask`, per-q-head max/sum via `attn_vec_allreduce`
(Y band, `comm_pe.csl:458-496`), exp, normalize. Masked entries carry `-3e38` and
exp to 0 — no per-element branching.

- `attn_mask:[score_total=16]f32` (`prefill.csl:970`) — additive causal mask
  (0 keep / `-3e38` mask), **counter-stored** `[slot][b][h][k][q]` matching
  `attn_root_seq/slot_seq`. Host build (`launch.py:2468-2490`): for column `lx`,
  hop `n` files block `b=orbX[n][lx]` at `(root=store_pe[c%pkh], slot=c//pkh)`;
  on band-PE `pib`, filled slots are those with `root==pib`; `b>lx` → whole tile
  masked, `b==lx` → strict lower-triangle masked (`np.tril_indices(sq,k=-1)`),
  broadcast over `(b,h)`.
- `softmax_max_f32/ssum_f32:[attn_vec_size=2]f32` (`prefill.csl:966-967`).

**Stage C — `out = score@V`** as a counter-based rectangular MeshGEMM ring
(`p_attn_scorev`, `prefill.csl:1126-1201`): a **dual preskew** (`scorev_pre =
[pS, pV]`) then `P_BLOCK_SIZE` ring steps.

- Score (LEFT) shifts **band-local along Y** on the x-channel, reusing the reduce
  colors 1/2/5 (queues 5/6/1, idle during attention) via `rebind_x_to_band`
  (`comm_pe.csl:503-571`). Preskew `pS` hops (`scorev_score_preskew`).
- V (RIGHT) re-hops **full-P along X** on the y-channel (`attn_right_hop`).
  Preskew `pV` hops (`scorev_v_preskew_step`).
- Both fused per step by `two_hop_comm`; slot read at ring step `s` =
  `scorev_slot_seq[s]` (`prefill.csl:1166-1191`).
- `score_h/score_h_scratch:[score_total=16]@fp16` — ping-pong ring operand
  (`prefill.csl:962-965`). `out_acc_f32` accumulates `[dim_per_pe,seq]`
  (`out_acc_f32[h*kv_tile_size+b*seq_len_per_pe]`, stride `reduce_len` over the
  `kv_dim_per_pe` feats), `@fs2h`→`attn_out` (`prefill.csl:1176-1197`).

Host counter tables (`_scorev_tables`, `launch.py:104-148`; sets
`attn_root_seq/attn_slot_seq/scorev_slot_seq/scorev_pre`, `launch.py:2492-2511`):
built from `_attn_rawhop_table` (systolic ±2 block-edge-wrap orbit `orbX`, and the
band orbit `orbY`), `posX`, `store_pe=orbY[:,0]`, `pS=posX%pkh`,
`pV=(-eposY)%pkh`, `preskew_off[lx][pib]=(posX[lx]+pV[pib])%P`.

- `attn_root_seq/attn_slot_seq:[P=256]i16` — replicated ‖ Y (per column `lx`),
  `col_root/col_slot` (`prefill.csl:975-976`, `launch.py:2499-2504`).
- `scorev_slot_seq:[P=256]i16` — per PE, `((preskew_off[lx][pib]+n)%P)//pkh`
  (`prefill.csl:979`, `launch.py:2505-2506`).
- `scorev_pre:[2]i16` = `(pS[lx], pV[pib])` (`prefill.csl:980`, `launch.py:2507`).

### KV cache (the cross-half critical part)

`cache_kv` (`prefill.csl:707-713`), called at the end of `p_rope_k` (K is final
post-QK-Norm+RoPE; V untouched since QKV): copies the K region of `XQKV`
(`ptr XK_off`) → `K_cache_bank[cur_layer]`, and the V region (`XK_off+kv_tile_size`)
→ `V_cache_bank[cur_layer]`. Both `[feature,seq]`, `kv_tile_size = kv_dim_per_pe·
reduce_len = 4`.

| Tensor | Sharding | Local symbol & shape | Dim order slow→fast | Op |
|---|---|---|---|---|
| K cache | kv_dim→Y, seq→X, banked by layer | `K_cache_bank:[L·kv_tile_size]=[7·4=28]@fp16` (`prefill.csl:702`) | `[layer][feature][seq]`, slot `cur_layer*kv_tile_size` | GQA K (post q/k norm + RoPE) |
| V cache | kv_dim→Y, seq→X, banked | `V_cache_bank:[L·kv_tile_size]=[28]@fp16` (`prefill.csl:703`) | `[layer][feature][seq]` | GQA V (raw from QKV) |

### KV→decode transform (`prefill.csl:715-758`, `kv_transform`)

After all layers, `start_kv_transfer` runs the block-local funnel (A: E/W sweep to
diagonal, B: N/S column emit so `tile(lx,ly)` lands on `PE(ly,lx)`, a transpose),
then `kv_transform` re-lays each tile into **decode slab order** in
`kv_xfer_bank:[2·L·kv_tile_size=56]@fp16` banked per `(layer, K|V)`
(`prefill.csl:724-758,838-841`). Source `kv_keep` is `[f][b][s]`
(`src_off = f*reduce_len + b*seq_len_per_pe`):

- **K stays interleaved = identity map onto decode's `XKCache` order.** Dst
  `(b*kv_dim_per_pe + f)*seq_len_per_pe` → `[b][f][s]` (batch outermost). K rows
  are already `[lo0,hi0,…]` interleaved from the GQA perm + interleaved RoPE, so
  the feature map onto decode is identity (`prefill.csl:739-751`).
- **V is transposed `[f][b][s] → [b][s][f]`** (`kv_col_dst` stride `kv_dim_per_pe`,
  base `b*seq_len_per_pe*kv_dim_per_pe + f`, `prefill.csl:752-754`).

Then `kv_north_shift` (state 4) ships `2·L=14` tiles per column north through the
relay seam into decode; each prefill region row `gy` sends `total_y_pes - gy`
tiles, receives one fewer (`prefill.csl:846-874`, `comm_pe.csl:985-998`).

### KV profiler (guarded by KV_PROFILE=1)

`kv_prof_pf:[4]f32` = `[A cycles, B cycles, done, pad]` (A = gather+transform,
B = north shift, `prefill.csl:769-875`). One reporter PE at `(Pw-1,Ph-1)=(511,511)`
(`launch.py:2395-2396`) also emits a 4-u32 burst SOUTH → `pf_kv_prof_mux`
forwarder → host.

---

## Module: pf_ht_tail (`src/prefill/ht_tail.csl`; built `launch.py:2757-2821`)

Role: final norm + lm_head + top-K + on-chip sampling → first generated token.
Region `HT_WIDTH_tail × P = 128 × 256` at `(4, 771)` (the last block's Y rows,
`ht_tail_y = PLACE_Y + by_last·P = 515+256`, so its dim-shard rows align with the
last block, `launch.py:2755-2756`). The last block's east column (`z_emit_lx=255`)
gathers the last-token dim shard and ships it WEST on `z_drain_color` (id 16) via
manual fabric; the tail multicasts it in (`prefill.csl:620-645`,
`launch.py:2556-2565`).

**Sharding: vocab → X (`V_per_pe_x=1187`/col), dim → Y (`dim_per_pe=8`/row)**
(`ht_tail.csl:1-2`).

| Tensor | Sharding | Local symbol & shape | Dim order slow→fast | Op |
|---|---|---|---|---|
| lm_head weight | vocab→X, dim→Y | `lm_head_tile:[V_per_pe_x·dim_per_pe = 9496]@fp16` (`ht_tail.csl:90`) | `[V_per_pe_x(vocab-outer)][dim_per_pe(dim-inner)]` row-major (`ht_tail.csl:88,332-341`) | lm_head matvec, contracts dim over **Y** (`tail_logits_reduce`) |
| final norm γ | dim→Y; replicated ‖ X vocab cols | `W_final_norm_tile:[dim_per_pe=8]@fp16` (`ht_tail.csl:102`) | `[feature]` | `model.norm` RMSNorm on Z (`tail_final_rmsnorm`) |
| Z slice (last hidden) | dim→Y | `z_slice_buf:[bsz·dim_per_pe=8]@fp16` (`ht_tail.csl:91`) | `[batch][dim_inner]` (`prefill.csl:622-644`) | drained from z_drain; norm + matvec input |
| logits partials | vocab→X (partial per col), contract dim→Y | `partials_buf:[bsz·V_per_pe_x=1187]f32` (`ht_tail.csl:94`) | `[batch][vocab_local]` | lm_head; f32 accumulate (HF parity) |

Host transform (`launch.py:2812-2820`): `lm_head_tile = randn(P, HT_WIDTH_tail·
HT_LM_HEAD_K)*0.05` bf16 (mock); `W_final_norm_tile = ones`. lm_head is
row-major vocab-outer/dim-inner (the K‑outer `[K,N]` orientation the in-outer
GEMV idiom expects; cf. skill `wse-csl-gemv-weight-tile-transposed`).

Pipeline (`ht_tail.csl:5-9`): (1) drain Z; (2) final RMSNorm (fp32) + lm_head
matvec → `partials[V_per_pe_x,bsz]`; (3) **Y allreduce contracting dim** (2-phase,
no broadcast) → logits land on `root_2nd_phase=136` row; (4) root row local top-K
then **X-axis 2-phase merge-reduce** over the 128 vocab cols (reuses the reduce
colors via runtime X/Y route reconfig, fenced by `tail_xready_color`) then
categorical sampling; (5) south: root-row east-most PE emits top-K + sampled
token to the mux. TSC PE at `(HT_WIDTH_tail-1, root_2nd_phase)=(127,136)`
(`launch.py:2791`) times forward-start→end.

---

## Module: pf_logits_mux (`src/prefill/mux.csl`; built `launch.py:2825-2849`)

Role: one-shot egress adaptor. `HT_WIDTH_tail × 1 = 128×1` at `(4, 1027)`. Only the
east-most PE is active: it drains the `wlts_per_step` u32 blob from the north
(HT_tail east-most) and forwards it EAST to the host, then drains + forwards an
8-u32 TSC burst piggybacked after (`mux.csl:1-47`).

| Tensor | Sharding | Local symbol & shape | Dim order | Op |
|---|---|---|---|---|
| logits blob | single active PE (east-most) | `blob:[N=wlts_per_step]u32` (`mux.csl:13`) | `[TOP_K·bsz val (2-packed f16)][TOP_K·bsz i32 arg][bsz sampled][pad]` (`mux.csl:2-4`, `launch.py:2800-2803`) | first-token result → host stream |
| TSC burst | east-most PE | `tsc_blob:[8]u32` (`mux.csl:23`) | `[start0..2][pad][end0..2][pad]` | benchmark timing → host |

No compute; store-and-forward. The host output stream is created from
`mux_host_port` (`launch.py:2842-2849`).

---

## Module: pf_kv_prof_mux (`src/kv_prof_mux.csl`; built `launch.py:2600-2628`)

Role: 1-PE host-I/O adaptor for the block region's KV profiler reporter
(mirrors the logits mux). `Pw×1 = 512×1` placed one row south of the block
region at `(132, 1027)` (`PLACE_Y+Ph`). East-most PE drains the reporter's 4-u32
burst arriving from the NORTH and forwards it EAST to the host; all other PEs
inert (`kv_prof_mux.csl:1-45`). Only built when `KV_PROFILE=1`.

| Tensor | Sharding | Local symbol & shape | Dim order | Op |
|---|---|---|---|---|
| profiler burst | east-most PE only | `blob:[N=4]u32` (`kv_prof_mux.csl:17`) | prefill `[A][B][done][pad]` | profiler A/B cycles → host |

---

## Module: relay seam (`src/relay.csl`; built `launch.py:2863-2877`)

**Passive** `Pw×2 = 512×2` region at `(132, 513)`, between decode's bottom block
row and prefill's top block row (`relay.csl:1-5`). No tasks, no compute, no storage
— `comptime {}` only. The host paints three colors:

- `17` (`kv_xfer_color_0`) and `21` (`kv_xfer_color_1`): with `KV_TRANSFER=1`,
  painted **SOUTH→NORTH pure transit** (`transit_rp`) so the prefill→decode
  KV-cache stream crosses the seam (prefill egress → decode ingress); else
  RAMP/RAMP reserved (`launch.py:2871-2874`).
- `22` (`kv_reserve_c`): reserved RAMP/RAMP either way (`launch.py:2875`).

**What transits, in what order:** the KV north-shift stream. Per `(layer, K|V)`
phase (14 phases = `2·max_layers_per_block`), a tile of
`bsz·kv_dim_per_pe·prefill_len_per_pe = 1·4·1 = 4` @fp16 words flows north; the
whole stream is `2·L=14` tiles per column, shifted `total_y_pes=512` blocking
steps north (`prefill.csl:851-855`, `comm_pe.csl:985-998`). Parity: even fabric
rows send on 21 / recv on 17, odd rows swap (`launch.py:2224,2575-2580`).

---

## Axis-role summary

| Axis | Prefill role | Decode role (contrast) |
|---|---|---|
| **X (px, `lx`)** | **sequence** (`seq_len_per_pe=1` token/PE); right-matrix (weight) hop; V full-P hop; kv-head **not** here | dim |
| **Y (py, `ly`)** | **dim / kv_dim** (`dim_per_pe=8`, `kv_dim_per_pe=4`); all norm reduces; left-matrix (activation) hop; kv-head **band** (32 rows); score band-local shift | sequence |
| Replicated | RoPE tables block-local (identical per block); norms γ ‖ X; `attn_root_seq/slot` ‖ Y; final-norm γ ‖ X | — |
| Banked by layer | all 8 weight banks, K/V cache, kv_xfer_bank (7 layers/block) | — |

Collectives (all on **Y** in prefill): `all_reduce_full` (whole-col, root 136),
`all_reduce_q_band`/`all_reduce_k_band` (32-row kv band, root 16),
`attn_score_reduce` (kv band → cycling root), `attn_vec_allreduce` (kv band → fixed
root 16). Projections use the MeshGEMM systolic ring (contract dim/ffn over Y,
left hops Y / right hops X), NOT an all_reduce.

---

## Prefill → decode layout contract

This is the one cross-half fact to get exactly right. After a prefill block
finishes its `L=7` layers, per `(layer, K|V)` it funnels its K/V cache tiles to
the block diagonal (E/W sweep), transposes tile→PE via an N/S column emit so
`tile(lx,ly)` lands on `PE(ly,lx)`, re-lays each into **decode slab order**
(`kv_transform`), and north-shifts `2L=14` tiles per column through the passive
relay seam into the decode region, where decode row `r` keeps its own mirror tile
and forwards the rest (`prefill.csl:715-758,846-874`; `comm_pe.csl:985-998`;
`decode.csl:1344-1394`). The layout each side agrees on: **K is stored
pair-interleaved and maps by identity** — prefill writes
`[b][f][s]` (`(b·kv_dim_per_pe+f)·seq_len_per_pe`) and decode's `XKCache_tile`
reads exactly `[b][kv_dim_per_pe][seq_len_per_pe]` at
`(l·bsz+b)·kv_dim_per_pe·seq_len_per_pe + f·seq_len_per_pe` (`decode.csl:1372-1383`,
`prefill.csl:749-751`); **V is transposed to `[b][s][f]`** — prefill writes
`b·seq_len_per_pe·kv_dim_per_pe + f` strided by `kv_dim_per_pe`, decode's
`XVCache_tile` reads `[b][seq_len_per_pe][kv_dim_per_pe]` at
`(l·bsz+b)·seq_len_per_pe·kv_dim_per_pe` (`decode.csl:1384-1392`,
`prefill.csl:752-754`). The transfer tile size is
`bsz·kv_dim_per_pe·prefill_len_per_pe = 4` @fp16 (`decode.csl:1349`,
`prefill.csl` `kv_tile_size` with `reduce_len=prefill_len_per_pe=1`), batch
outermost. `KV_TRANSFER` requires `decode.PREFILL_LEN == prefill.PREFILL_LEN`
(the RoPE start position) and `n_layers`/`bsz` to match (`launch.py:2919-2929`).

---

## Inconsistencies / ambiguities / things worth flagging

1. **`seq_len_per_pe = reduce_len = 1` for this config.** With PREFILL_LEN=256 and
   P_BLOCK_SIZE=256, each X-PE owns exactly one prompt token. The `[feature,seq]`
   `f*reduce_len+s` indexing degenerates (`s∈{0}`), `attn_tile=1`, score tiles are
   1×1. All formulas hold but many stride terms vanish; anyone generalizing this
   doc to a config with `seq_len_per_pe>1` must re-check the score/mask counter
   layouts. This is a real constraint, not a bug.

2. **Mock weights only.** Every prefill weight (`W_qkv/W_o/W_upgate/W_down`,
   `lm_head_tile`) is `randn*0.1`/`*0.05`; norms/final-norm γ = ones
   (`launch.py:2443-2454,2814-2818`). This launcher is structural/timing
   validation — numerics are meaningless. Real HF weights would need the
   documented perms (`_perm_WQ`/`_reshard_K_dim`/`_perm_WO`, used on the decode
   side `launch.py:1384-1436`) to land in the pair-interleaved GQA layout; the
   RoPE fills already assume that interleave (`launch.py:2298-2324`).

3. **`score_f32`/`attn_mask`/`score_h` are NOT `[feature,seq]`.** They use an
   attention-specific counter-stored `[slot][b][h][k][q]` layout
   (`prefill.csl:1005-1013`). The task's "confirm feature-major everywhere"
   applies to activation/weight tiles; score/mask tensors are a documented
   exception, not a violation.

4. **Color id 21 is triple-purposed** across the stacked artifact (decode
   `UP_A_color`, prefill `kv_xfer_color_1`, relay reserve) and id 23 is
   double-purposed (decode `post_embed_x`, prefill `kickoff`). Safe only because
   the painted PE sets are wafer-physically disjoint (`launch.py:2223-2239`);
   noted here because it looks alarming in isolation.

5. **`build_prefill` does no dim padding** (asserts exact divisibility,
   `launch.py:2096-2097`), whereas `build_decode` has a full `_pad_to`/`_zpad`
   path. For real Qwen3 dims everything divides, so this is fine — but a prefill
   config with an indivisible dim/vocab would hard-fail at build, while the decode
   half would silently pad. Asymmetry worth remembering.

6. **`prefill_len_per_pe` naming.** Decode calls the transfer's per-PE seq extent
   `prefill_len_per_pe` (=1 here); prefill's equivalent is `reduce_len`/
   `seq_len_per_pe`. They are numerically equal by the `PREFILL_LEN` match
   assertion, but the two halves use different symbol names for the same axis —
   easy to misread when cross-referencing `decode.csl:1349` against
   `prefill.csl:177`.
