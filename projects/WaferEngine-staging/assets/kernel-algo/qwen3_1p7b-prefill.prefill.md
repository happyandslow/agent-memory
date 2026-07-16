# prefill.csl — serpentine layer pipeline, chunked GQA attention

> Kernel algorithm walkthrough. Model `qwen3_1p7b-prefill`, ref config `test_sim_2x4_kv_varlen.json`
> (2×4 blocks, 8×8 PE/block, 8 layers → 1 layer/block). Diagram: `qwen3_1p7b-prefill.prefill.svg`.
> Comms taxonomy per the `cerebras-kernel-comm-patterns` skill. Citations `prefill.csl:LINE`.

## Core idea — one program is a whole transformer-layer stage, streamed chunk by chunk

Every PE in the fabric runs this one file. It computes a **contiguous slice of transformer layers**
(prefill.csl:9-14): `distribute_layers` (launch.py:152) hands block `b` layers `[offset,offset+count)`,
banked by layer (`set_layer(l)` repoints the weight pointers, prefill.csl:237). Blocks are tiled as a
**serpentine snake** (launch.py `pipeline_index:739`, W→E on even block-rows, E→W on odd) and pass the
running hidden state `X` block→block along it (`enter_source_shuttle`/`arm_dest_block_and_run`).

Within a block the prompt is processed as **chunks** of `CHUNK_SIZE` tokens (`current_chunk`,
prefill.csl:288); each chunk runs the full layer stack via a 14-state flag machine `prefill_struct`
(prefill.csl:1492) — `rmsnorm → QKV matmul → QK-norm Q/K → RoPE Q/K → attention → O matmul → residual →
RMSNorm → up/gate matmul → SwiGLU → down matmul → residual/next-layer`. Attention is **chunked
FlashAttention-2**: chunk `c`'s queries attend causal chunk-pairs `0..c` (`attn_pair`, prefill.csl:1048),
each pair's partial `(m,l,O)` folded by `flash_combine` (prefill.csl:1365, the P-8 FA-2 rescale). Projected
K and raw V are banked per `[layer][chunk]` (`cache_kv`, prefill.csl:783) so later chunks re-read them.

The two heavy movements are the two the skill separates: **projections are Cannon** (P-3, tokens sharded
on X, contraction on Y), and **norm/softmax reductions are chain all-reduces** (P-1/P-7) along the axis the
quantity is sharded on. Nothing is ever routed by a key; every count is derived from PE coordinates.

## Data distribution on PEs

One region spans the whole `Pw×Ph` fabric; each PE finds its block via block-local `local_px/local_py`
(prefill.csl:9-14). A block is a square `P_BLOCK_SIZE × P_BLOCK_SIZE` grid (ref: 8×8). **Prefill is
token-sharded on X, feature-sharded on Y** — the transpose of decode.

| Tensor | Sharding | Per-PE width |
|---|---|---|
| sequence (chunk tokens) | **X** (`local_px`) | `chunk_len_per_pe = CHUNK_SIZE/P` (ref = 1) |
| hidden `dim` (X_tile, X_norm, Z, residual, RMSNorm gain) | **Y** (`local_py`) | `dim_per_pe` |
| Q-output columns (attn_out) | **Y** | `attn_per_pe = gqa_group_size · kv_cols` |
| K/V head-dim columns | **Y** | `kv_cols` (one kv-head band slice, RoPE-pad aware) |
| FFN inner dim | **Y** | `ffn_dim_per_pe` |
| KV cache banks `K/V_cache_bank[layer][chunk]` | **Y** (feature) × banked over layer,chunk | `kv_tile_size = kv_cols·reduce_len` |
| transformer layers | **block** (serpentine slice) | `layers_in_this_block` |

Per-PE storage is **feature-major, seq-minor**: `X_tile[f·reduce_len + s]` (prefill.csl:17-20). This is
MeshGEMM's native left-operand order, so `Mt = reduce_len = bsz·chunk_len_per_pe` is constant across all
four projections and one Cannon driver (`setup_matmul`, prefill.csl:560) serves them all. A **kv-head band**
is `pes_per_kv_head` Y-rows holding `gqa_group_size` Q-heads + one K/V copy; QK-norm and Q@Kᵀ reduce over
this band along Y (`all_reduce_k_band`, a P-7 band reduce). `X_tile` carries a **2-word
metainfo tail** (`request_n_chunks`, `last_token_chunk_pos`, prefill.csl:249-255) that rides every shuttle
untouched — a G-4 budget header folded into the activation tile.

## Communications + which task owns each step

**Phase 0 · boot (init_task, prefill.csl:1570)**
- `comm.init()` reads coords and paints, once: the reduce colors (1,2,5), both shuttle axes (N/S 3,4;
  E/W 12,13), the MeshGEMM interleave (6-11). `kv_egress` switch gets `ring_mode + pop_on_advance`
  (prefill.csl:1577). Then `enter_request()`.

**Phase 1 · X arrives (enter_request → enter_x_chain / arm_dest_block_and_run)**
- `enter_request` (prefill.csl:1539) resets `current_chunk`, serve-state, the egress switch, then routes X
  in: **block 0** calls `enter_x_chain` (prefill.csl:729) — rebind IQ4 to the parity-correct x_chain color,
  peel this column's `[dim,seq]` chunk into `X_tile`, **forward the rest east** (G-2 FIFO peel + G-1 parity
  chain, from HT_head, a **P-6** region crossing); `x_chain_recv_finish → x_chain_fwd_finish → start_layers`.
  **Non-first blocks** call `arm_dest_block_and_run` (prefill.csl:1527) — `comm.enter_dest_shuttle[_drained]`
  receives the tile from the serpentine-previous block (**P-5 shuttle**), then `start_layers`.

**Phase 2 · the per-chunk layer machine (prefill_struct, prefill.csl:1492)** — each `p_*` ends by
re-entering `prefill_struct` at the next flag:
- `rmsnorm_full` (flag 0, prefill.csl:320) — local sum-of-squares, then `comm.all_reduce_full` over the
  hidden `dim` on **Y** (**P-1** two-phase chain all-reduce), rsqrt, scale.
- `p_qkv_matmul` (flag 1) → `setup_matmul(X_norm, QKV_weight → XQKV)`: **P-3 Cannon** — `left_matrix_shift`
  skews A `mm_root` hops on the x channel (B's skew folded into the host weight upload), then `P` ×
  `two_hop_comm` (left hops Y, right hops X), rendezvoused by `left/right_matrix_finish → two_hop_comm_finish
  → next_step` (prefill.csl:648-663), f32 accumulate → bf16.
- `p_qk_norm_q/k` (flags 2,3) — `qk_norm` RMSNorm over `head_dim`, a **band-scoped** reduce
  `comm.all_reduce_k_band` (**P-7**, `comm.reconfig(2)` paints the kv-band routes).
- `p_rope_q/k` (flags 4,5) — local RoPE θ=1e6 on interleaved even/odd feature pairs; `p_rope_k` calls
  `cache_kv` (K now final) to bank K and V at slot `[layer][chunk]` (prefill.csl:783). No comms.
- `p_attn_score` (flag 6) — **chunked FA-2 attention**, the comms-densest phase:
  - `attn_pair_begin` (prefill.csl:1347) stages this pair's banked K/V into ring-safe scratch, then
    `comm.enter_qkt_reduce` paints the four-color band chain **once per pair** (queues 7,0 + reduce 1,2).
  - **Stage A** `attn_score_step` (prefill.csl:1171): `Q·Kᵀ` over `P` key-block hops — K X-hops on the y
    channel (`comm.attn_right_hop`, async, queue 3, rendezvous `attn_finish`), each hop's band partial
    reduced to a **cycling root** with **zero repaint** (`comm.attn_score_reduce`, **P-7** cycling-root).
  - **Stage B** `p_attn_softmax` (prefill.csl:1189): α-scale, causal mask on the diagonal pair only, then
    per-`(b,h,q)` max-reduce and sum-reduce via `comm.attn_vec_allreduce` (**P-8/P-1**, max then sum),
    stopping *before* normalize (leaves `m_pair, l_pair, exp`).
  - **Stage C** `p_attn_scorev` (prefill.csl:1222): `out = score·V` as a **rectangular P-3 Cannon ring** —
    Score (left) shifts **band-local along Y** on the x channel (`rebind_x_to_band` time-multiplexes
    reduce queues 5,6,1 onto band colors 18-20), V (right) re-hops full-P along X (`attn_right_hop`);
    band-shift → V-hop → MAC serialized per step (`scorev_compute`, prefill.csl:1313).
  - `scorev_terminal → restore_x_band` (drains the band OQ, rebinds 5,6,1 back to reduce colors, G-14) →
    `scorev_drain_done` (prefill.csl:1298): `flash_combine` folds the pair, then next pair or
    `attn_finalize` (divide `O_run/l_run`).
- `p_o_matmul` (flag 7, Cannon), `p_z_residual` (flag 8, `Z = X + O`), `p_rmsnorm_z` (flag 9, P-1),
  `p_upgate_matmul` (flag 10, Cannon), `p_swiglu` (flag 11, local SiLU poly), `p_down_matmul` (flag 12,
  Cannon), then the terminal.
- `p_ffn_residual_next_layer` (prefill.csl:1442) — `X = Z + down`; `current_layer++`. **More layers** →
  `set_layer`, flag 0, loop. **Layers done** → decode the metainfo tail; if `out_shuttle_dir != 0`,
  `comm.enter_source_shuttle(&X_tile)` ships X (+ tail) to the serpentine-next block (**P-5**, a blocking
  rendezvous).

**Phase 3 · loops and egress**
- **per-chunk loop**: `current_chunk < request_n_chunks-1` → block 0 re-arms `seed_chunk_x`, dest blocks
  `arm_dest_block_and_run`, both → `start_layers` for chunk `c+1`.
- **last chunk**: the final serpentine block's last-token column gathers its dim shard and `emit_z_last_token`
  ships it **WEST** to HT_tail on `z_drain_color` (prefill.csl:691, a **P-6** region-crossing point-to-point).
- **KV egress** (`kv_egress != 0`, `start_kv_egress` prefill.csl:901): each PE **switch-gathers** its K then
  V banks **EAST** to the row colmux (**P-4 seam**, canonical PATTERN-B switch gather — head emits, others
  forward-then-emit, turn handed east by a `SWITCH_ADV` control wavelet); the row-head prepends
  `request_n_chunks` (**G-4** header), banks ride 2-fp16/u32 (**G-12** payload-opaque `@mov16`), varlen =
  runtime segment **count** × comptime **length**. `@queue_flush` drains OQ4 then the empty handler re-arms
  ingress (**G-14** flush-gated rebind).
- **per-request loop**: `enter_request` re-arms for the next request (serve-loop residency).

## Communication summary

| Movement | color / queue | direction | pattern | task / fn |
|---|---|---|---|---|
| X in (block 0, from HT_head) | x_chain 14,15 / IQ4,OQ4 | X east | **G-1 parity + G-2 peel**; region-cross **P-6** | `enter_x_chain` |
| X in (dest blocks, from prev block) | N/S 3,4 or E/W 12,13 / q7,0 | snake hop | **P-5 shuttle** | `enter_dest_shuttle[_drained]` |
| RMSNorm / FFN-norm reduce (dim) | reduce 1,2 + bcast 5 / q5,6,1 | Y chain | **P-1** two-phase all-reduce | `all_reduce_full` |
| QK-norm reduce (head_dim) | reduce 1,2 / q5,6 | Y band | **P-7** band reduce | `all_reduce_k_band` |
| QKV / O / up-gate / down matmul | x 6-8, y 9-11 / q2,3 | Cannon ring | **P-3 Cannon** | `two_hop_comm` |
| Q·Kᵀ K-hop | y 9-11 / q3 | X full-P hop | Cannon operand shift + **P-7** cycling-root reduce | `attn_right_hop` / `attn_score_reduce` |
| softmax max/sum | reduce 1,2 + bcast 5 | band | **P-8** (max then sum) | `attn_vec_allreduce` |
| Score×V band-shift | band 18,19,20 / q5,6,1 (rebound) | Y band-local | **P-3** rectangular Cannon (left) | `left_matrix_shift` |
| Score×V V-hop | y 9-11 / q3 | X full-P | **P-3** rectangular Cannon (right) | `attn_right_hop` |
| cross-pair fold | — (local) | — | **P-8** FA-2 `(m,s)` rescale | `flash_combine` |
| X out → next block | N/S 3,4 or E/W 12,13 / q7,0 | snake hop | **P-5 shuttle** | `enter_source_shuttle` |
| last-token z → HT_tail | z_drain 16 / OQ4 (OQ7 if egress) | X west | region-cross **P-6** | `emit_z_last_token` |
| KV egress → host | kv_egress 21 / OQ4 | X east (switch) | **P-4 seam** + G-4 + G-12 + G-14 | `kv_egress_emit_k/v/adv` |
| metainfo tail (rnc, last-tok) | rides X_tile on the shuttles | with X | **G-4** budget header | (folded into X_tile) |

Correctness is **count-exactness** (prefill.csl:803-810 spells out the varlen invariant: runtime segment
*count*, comptime segment *length*; a runtime `@set_dsd_length` on a fabric DSD would degenerate the
appliance routing rectangle). No key routing, no acks — a wavelet-count mismatch is a silent hang.

## One line

One program on every PE is a whole transformer-layer stage; blocks are serpentine pipeline stages passing
`X` along a snake (P-5/P-6), each chunk drives a 14-state flag machine whose two heavy moves are **Cannon
projections** (P-3) and **chain all-reduces** (P-1/P-7), attention is **chunked FlashAttention-2** with a
rectangular Score×V Cannon ring and a `(m,s)` cross-chunk fold (P-8), and finished KV is switch-gathered to
the host (P-4) — every movement a compile-time permutation of PE coordinates, never a keyed route.
