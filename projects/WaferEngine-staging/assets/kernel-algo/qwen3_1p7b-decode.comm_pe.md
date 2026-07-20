# comm_pe.csl — the decode block's communication toolbox

> Kernel algorithm walkthrough. Model `qwen3_1p7b-decode`, ref config `test_sim_2x2block_kv_varlen.json`
> (2×2 blocks, 8×8 PE/block, `bsz=2`). Diagram: `qwen3_1p7b-decode.comm_pe.svg`.
> Comms taxonomy per the `cerebras-kernel-comm-patterns` skill (P-*/G-*).
> **Git state:** working tree of branch `lexu/staging/s6a-inner-pe-kv-route-a` with the
> **uncommitted S6a KV-retain work** applied (`retain_rt` gating in `decode.csl`,
> `round_reingress_id` / `kv_rebind_to_ingress_flush` in this file). Not `main`, not `fcfc8c1`.
> This file has **no `main()`** — every function here is *called by* `decode.csl`'s drivers.

## Core idea — one reduce skeleton, eight payloads, three axes

Prefill's `comm_pe.csl` is a *pattern zoo* (Cannon, band shifts, serpentine shuttle, a reconfig
route machine). Decode's is the opposite: **one collective shape — a two-phase chain all-reduce plus
a router-multicast broadcast — instantiated eight times at different payload extents, and steered
onto one of three physical axes by repainting five colors.**

That collapse is structural, not a simplification. Decode's per-token step has `m = 1` token, so
every GEMM is a **GEMV** whose contraction is sharded across PEs. By the comm-patterns Gate-2
crossover rule (Cannon wins iff `m > d`, and output-stationarity buys nothing when `C` is a vector),
`m = 1` forces P-1 all-reduce everywhere. **There is no Cannon, no `two_hop_comm`, no
`left_matrix_shift`, no band operand shift, and no `run_shuttle` in this file** — those five
prefill entry points simply do not exist here. What replaces the shuttle is a plain synchronous
P-6 point-to-point send plus a P-2 broadcast (`inter_block_send_z` / `inter_block_recv_x_sync` /
`intra_block_x_broadcast_y_bsz_dim`, `comm_pe.csl:1281-1318`).

The correctness story is the same as prefill's — **count-exactness + backpressure, no acks, no
credits**. Both ends of every link derive the same wavelet count from block-local coordinates set
once in `init()` (`comm_pe.csl:630-681`). A mismatch is a silent hang, never an error.

But decode's *fencing* story is different and worth stating precisely, because it is written into
the source as an invariant (`comm_pe.csl:1325-1334`):

> `reconfig_allreduce_axis` repaints the **shared** reduce/broadcast colors **with no explicit
> barrier**. It is race-free *only* because every `all_reduce_*` on those colors is **synchronous**
> and **ends in a multi-tx broadcast** — per-child router backpressure makes the collective
> self-fencing, so the colors are globally quiescent on return.

Prefill buys its safety with explicit `@queue_flush` drains and T29 empty-queue handlers around
every rebind. Decode buys it with a *structural* argument instead, and the header spells out the
three conditions that must all hold (call only at a collective boundary; never make an
`all_reduce_*` async; keep the broadcast multi-tx). Breaking any one is a **device-only, sim-green
C1 hang**. Decode uses a real `@queue_flush` + empty-queue handler in exactly one place — the KV
ingress queue borrow (below), which is *not* a collective.

## Data distribution the collectives assume

A block is one `P_BLOCK_SIZE × P_BLOCK_SIZE` square (8×8 in the ref config; 256×256 on device).
Blocks own a **contiguous slice of transformer layers** (`distribute_layers`), never a shard of one
tensor — so nothing is ever reduced across blocks.

| Axis | Owns | Reduces that contract over it |
|---|---|---|
| **Y (rows, `local_py`)** | HIDDEN dim shard, `dim_per_pe = dim/P` (8 in ref cfg) — **and** the KV **sequence** shard: PE `py` owns absolute positions `py, py+P, py+2P, …`, `kv_len_per_pe = MAX_SEQ_LEN/P` (4) | RMSNorm sumsq; QKV projection; FFN up/gate; **softmax max + sum** (contracts over KV positions) |
| **X (cols, `local_px`)** | attention Q-column shard `attn_per_pe` (8) / K,V column shard `kv_cols` (4) / FFN width `ffn_dim_per_pe` (16) | O-projection; FFN down-projection |
| **kv-head band (a run of `pes_per_kv_head` X-PEs)** | one KV head's head-dim slice; `pes_per_kv_head = P/n_kv_heads` (4), root at band middle `kv_head_root = 2` | QK-Norm sumsq; Q·Kᵀ score reduce (contracts over head_dim) |
| **block boundary** | the pipeline handoff of the `[bsz, dim_per_pe]` hidden tile | P-6 `inter_block_send_z` / `inter_block_recv_x_sync` |

**Note the axis flip vs prefill.** Prefill's kv-head band runs along **Y**; decode's runs along
**X** (`launch.py:466-469`, "KV-head bands lie along X"; `comm_pe.csl:982-986`, "over
`pes_per_kv_head` X-PEs"). And prefill's X axis is *sequence*, while decode's X axis is
*attention/FFN column width* — decode's sequence lives on Y. Do not carry prefill's axis intuition
across.

Reduce buffers are **f32** throughout for HF parity; only the softmax-max reduce and the
inter-block/intra-row hidden-tile moves are 16-bit. The fabric send/recv DSDs are dtype-agnostic
(extent + queue only) and are shared between the f32 and bf16 paths (`comm_pe.csl:501-517`).

## The functions, grouped by pattern

### P-1 two-phase chain all-reduce — the workhorse (6 of the 8 variants)

The engine is identical in all six: **phase 1** reduces inside a group of `pe_num_per_group = P/group_num`
PEs toward `root_1st_phase`; **phase 2** reduces among the `group_num` group roots toward
`root_2nd_phase`; then a **P-2 router-multicast broadcast** back from `root_2nd_phase`
(`@mov32` from the root; every other PE does one `@mov32` from the broadcast fabin). Ref config:
`group_num=4 → pe_num_per_group=2, root_1st_phase=1, root_2nd_phase=5` (`launch.py:416-470`).
Add-stage depth is `P/(2g) + g/2`, minimized at `g = √P`; the device config picks `g=16` for `P=256`.

Each variant is **the same code with a different comptime extent** — the Gate-3 "step 0" move
(a new payload on a channel that already runs, costing zero colors and zero queues):

| Function | `file:line` | Extent (ref cfg value) | Buffer dtype | Driven from |
|---|---|---|---|---|
| `all_reduce_bsz_f32` | `comm_pe.csl:685-763` | `bsz` (2) | f32 | RMSNorm sumsq — `decode.csl:315, 934` |
| `all_reduce_bsz_dim` | `comm_pe.csl:1035-1113` | `bsz·dim_per_pe` (16) | f32 | Score×V out (Y), O-proj (X), FFN-down (X) — `decode.csl:1346, 1353, 1413` |
| `all_reduce_bsz_dim_QKV_fusion` | `comm_pe.csl:1115-1193` | `bsz·(attn_per_pe + 2·kv_cols)` (32) | f32 | Q,K,V in **one** reduce — `decode.csl:1431` |
| `all_reduce_bsz_ffn_dim_ZZ_fusion` | `comm_pe.csl:1195-1273` | `bsz·2·ffn_dim_per_pe` (64) | f32 | FFN up+gate in one reduce — `decode.csl:1466` |
| `all_reduce_bsz_gqa_group` | `comm_pe.csl:767-845` | `gqa_group_size·bsz` (4) | f32 | softmax **sum** — `decode.csl:1294` |
| `all_reduceMax_bsz_gqa_group` | `comm_pe.csl:848-926` | `gqa_group_size·bsz` (4) | fp16 | softmax **max** (`@fmaxh`, `@mov16` bcast) — `decode.csl:1265` |

Three observations that matter:

- **The two `*_fusion` variants fuse a second reduction into an adjacent one.** Q, K and V are three
  separate GEMVs contracting over the same Y-sharded hidden dim, so their partial sums concatenate
  into one buffer and ride one chain (`decode.csl:1428-1432`). Same for FFN up and gate
  (`decode.csl:1464-1467`). Legal because the two reductions share an axis and neither input depends
  on the other's output. This is why decode does **6 collectives per layer, not 9**.
- **`all_reduce_bsz_dim` is axis-polymorphic.** It is called with `(local_py, quotient_y, remainder_y)`
  at `decode.csl:1346` and with `(local_px, quotient_x, remainder_x)` at `1353` and `1413` — the
  *same* function, the *same* colors, a different axis. The axis is entirely a property of the
  painted route plus which coordinate triple you hand it.
- **A latent identity, not a guarantee.** `decode.csl:1346-1347` reduces `bsz·attn_per_pe` worth of
  Score×V output through the `bsz·dim_per_pe`-extent DSDs. That is only correct because every shipped
  config has `head_dim_shard == head_dim ⇒ attn_per_pe == dim_per_pe` (`launch.py:437-448`). A config
  that triggers head-dim padding breaks the count on one side of the link — i.e. a **silent hang**.

**Softmax is P-8 done the decode way:** two-pass safe softmax — `all_reduceMax_*` for the global max,
then subtract, then `all_reduce_bsz_gqa_group` for the plain sum (`decode.csl:1265, 1294`). Both run
on the Y axis (KV positions). Prefill instead carries FA-2 `(max, sum)` rescale across chunks;
neither `flash_combine` nor any rescale exists here.

- **Colors/queues:** `reduce_1st_color_0` = c1/IQ3+OQ3, `reduce_1st_color_1` = c2/IQ4+OQ4,
  `reduce_2nd_color_0` = c3/IQ5+OQ5, `reduce_2nd_color_1` = c4/IQ6+OQ6,
  `broadcast_color` = c5/IQ7+OQ7 (`comm_pe.csl:77-88`; ids at `launch.py:592-596`).
- **Deadlock-free:** fully synchronous `@fadds`/`@fmaxh`/`@mov32` — no continuation task, no
  microthread. Parity (`% 2`) picks which of the two chain colors carries rx vs tx at each hop, so
  adjacent PEs never both block on the same color. A chain endpoint emits with `@fmovs`/`@fmovh`
  (send-only) so its dangling rx never fires. `group_num` **must** divide `P_BLOCK_SIZE` or a
  stranded PE deadlocks the reduce — asserted at `launch.py:411-415`.

### P-7 band-scoped reduce — QK-Norm and the Q·Kᵀ score (kv-head band, along X)

A **single-phase** bidirectional chain confined to one kv-head band of `pes_per_kv_head` X-PEs, rooted
at the band middle, then a band-scoped P-2 broadcast. `reduce_2nd_color_0/1` are **unused** in this
mode and left untouched by the repaint (`comm_pe.csl:566-572`).

- **`all_reduce_qk_kv_head_scoped`** (`comm_pe.csl:987-1033`) — Qwen3 QK-Norm per-head sumsq over
  head_dim, **fused Q+K**: extent `(gqa_group_size + 1)·bsz` (6 in ref cfg) = Q's `gqa_group_size·bsz`
  sums followed by K's `bsz` sums in one buffer. Driven from `decode.csl:1131`.
- **`all_reduce_bsz_gqa_group_kv_len_kv_head_scoped`** (`comm_pe.csl:931-980`) — the Q·Kᵀ score
  reduce, extent `gqa_group_size·bsz·kv_len_per_pe` (16). Driven from `decode.csl:1231`.
- Both **no-op entirely when `pes_per_kv_head == 1`** (`comm_pe.csl:939, 973, 993, 1026`) — one PE per
  kv-head means the local partial is already the full sum, and the guard also suppresses the
  broadcast so the counts stay exact on both sides.
- **Colors/queues:** `reduce_1st_color_0/1` (c1/q3, c2/q4) + `broadcast_color` (c5/q7), on the kv-head
  routes painted by `reconfig_allreduce_axis(3)`.
- **Contrast with prefill:** prefill's `attn_score_reduce` needs a *cycling root* and therefore splits
  the band across two disjoint color pairs (south c1,c2 / north c3,c4) to get zero-repaint root
  advance. Decode's root is **fixed** at `kv_head_root`, so one color pair suffices and colors 3,4
  stay free for the second reduce phase. Decode has no `enter_qkt_reduce`, no
  `restore_k_band_routes`, no `paint_band_routes`.

### P-6 / P-2 — the inter-block pipeline handoff (replaces prefill's shuttle)

Decode does **not** run a shift register across the block edge. The hidden tile moves once,
synchronously, point to point, and is then fanned out inside the receiving block.

- **`inter_block_send_z`** (`comm_pe.csl:1308-1318`) — one `@fmovh` of `bsz·dim_per_pe` bf16 words on
  the inter-block color **opposite** the one this PE receives on. No-op where `has_inter_send_rt == 0`.
- **`inter_block_recv_x_sync`** (`comm_pe.csl:1281-1290`) — the mirror `@fmovh` into `ptr_X`. No-op
  where `has_inter_recv_rt == 0`. Driven from `decode.csl:1780`.
- **Two globally-pinned colors alternating by edge parity.** `inter_block_a_color` = id 19,
  `inter_block_b_color` = id 20 (`launch.py:579-580`) — layout-global, *same physical id in every
  `row_y` region*, so a wavelet crosses the `row_y → row_y+1` boundary on the same color. Each PE
  binds **two** queues per direction at comptime (IQ0/IQ1 recv, OQ1/OQ2 send, `comm_pe.csl:95-98`) and
  picks by the runtime flag `is_recv_on_a_rt`, because which color it recvs on is a parity decision
  not known until `init()`.
- **`intra_block_x_broadcast_y_bsz_dim`** (`comm_pe.csl:1295-1306`) — the received per-column X tile is
  P-2 router-multicast along X on `intra_row_bcast_color` (c6, `launch.py:597`; IQ2 recv / OQ0 send,
  `comm_pe.csl:90-91`). Three modes: strip-is-source (every block PE receives), else the
  `root_2nd_phase` column sends and everyone else receives.
- **A hard placement invariant** (`comm_pe.csl:1387-1395`): OQ 0 carries `intra_row_bcast_color`
  *except* on the snake-end `is_result_sender` PE where it already carries `result_color`. So a
  result-sender must never also be the intra-row broadcast **source** — it would have no OQ 0 to send
  on. The host is responsible for not placing `is_result_sender` on the `root_2nd_phase` column.
- **`is_x_receiver` escape** (`comm_pe.csl:1408-1412`): on the chain-start block's host-X receive
  column, IQ0 binds `x_input_color` (id 23, HT_head's post-embed X stream) instead of
  `inter_block_a_color` — the same DSD, a different upstream producer.

### The `reconfig_allreduce_axis` machine (G-3 repaint, no fence)

**`reconfig_allreduce_axis(axis)`** (`comm_pe.csl:1335-1345`) is the **one** route-switch entry point.
Unlike prefill's `reconfig`, it switches the collective's **physical axis**, not its topology mode:

| axis | paints | colors touched | used for |
|---|---|---|---|
| `0` | `write_Y_routes` (`comm_pe.csl:558-564`) | reduce_1st (1,2) + reduce_2nd (3,4) + bcast (5) | hidden-dim / KV-sequence reduces |
| `1` | `write_X_routes` (`comm_pe.csl:550-556`) | same five | attention-column / FFN-width reduces |
| `3` | `write_X_kv_head_routes` (`comm_pe.csl:568-572`) | reduce_1st (1,2) + bcast (5) only | kv-head band reduces |

*(There is no axis 2; anything else hits `@assert(false)`.)*

Every repaint is a **replay of precomputed words**, not a recomputation: `precompute_route_words`
(`comm_pe.csl:599-628`) computes all 13 `(axis, color)` config words once in `init()` from the
layout-painted register base, and each `write_*_routes` is then just one `@set_config` per color
(`apply_route_word`). The preserved bits are axis-invariant, which is what makes the replay legal.
The route-writing helpers are `noinline` wrappers over `route_util` specifically to keep route writes
off decode's hot-path inline budget (`comm_pe.csl:520-531`).

**Per-layer axis schedule** (`decode.csl:1424-1484`) — six repaints per layer:

```
rmsnorm_x                      [Y]        all_reduce_bsz_f32
Q,K,V matvecs + QKV fusion     [Y]        all_reduce_bsz_dim_QKV_fusion
  reconfig(3) ─────────────────────────────────────────────────► kv-band
qk_norm_q_k                    [kv-band]  all_reduce_qk_kv_head_scoped
rope, process_kv (no comms)
score_matvec_mult              [kv-band]  ..._kv_len_kv_head_scoped
  reconfig(0) ─────────────────────────────────────────────────► Y
softmax_score                  [Y]        all_reduceMax + all_reduce (gqa_group)
output_matvec_mult (Score×V)   [Y]        all_reduce_bsz_dim
  reconfig(1) ─────────────────────────────────────────────────► X
o_matvec_mult                  [X]        all_reduce_bsz_dim
  reconfig(0) ─────────────────────────────────────────────────► Y
rmsnorm_z, up/gate + ZZ fusion [Y]        all_reduce_bsz_f32, ..._ZZ_fusion
  reconfig(1) ─────────────────────────────────────────────────► X
down_matvec_mult               [X]        all_reduce_bsz_dim
  reconfig(0) ─────────────────────────────────────────────────► Y  (restore for next layer)
```

### G-14 queue borrow — the KV-cache ingress (decode-only, and the one real drain)

The startup KV-cache ingress needs a fabric channel before any collective has run, and there is no
spare queue pair. It **borrows the broadcast queues** IQ7/OQ7 and hands them back once.

- **Comptime boot** (`comm_pe.csl:1373-1385`): when `kv_stream_ingress != 0`, OQ7 initializes to
  `kv_ingress_color_1` and IQ7 to `kv_ingress_color_0` — *not* to `broadcast_color` — and
  `kv_ingress_oq_empty` is installed as OQ7's empty-queue handler.
- **Per-PE parity swap** (`comm_pe.csl:668-680`): odd fabric **columns** swap the two colors (recv on
  c1, send on c0) so adjacent columns alternate, giving the west-shift chain its parity ordering.
  `init()` caches this PE's binding in `ing_iq_color_i16` / `ing_oq_color_i16` so the handler can
  restore exactly it.
- **`kv_ingress_flush_then_resume`** (`comm_pe.csl:1364-1367`) — sets the direction flag to 0 and
  `@queue_flush`es OQ7. The handler `kv_ingress_oq_empty` (`comm_pe.csl:1351-1363`) then re-encodes
  IQ7/OQ7 onto `broadcast_color`, calls `queue_flush.exit`, and `@activate`s `kv_ingress_resume_id`
  in `decode.csl`. Called from `decode.csl:1654`.
- **`kv_rebind_to_ingress_flush`** (`comm_pe.csl:1368-1371`) — **the S6a addition**: the reverse
  rebind, flag 1, broadcast → ingress, continuing to `round_reingress_id`. This is what makes the
  ingress channel re-armable **per round** instead of one-shot at startup, which is the plumbing the
  multi-round KV-retain work sits on. Called from `decode.csl:1825`.
- **Ingress colors reuse ids 17 and 21** (`launch.py:632-633`) = `kpipe_b k7` and `UP_A_color`. The
  disjointness proof is in the comment: those live on strip / HT_head cells while the KV west-shift
  lives on block-column cells, so the ids are wafer-physically disjoint. This is the comm-patterns
  "reuse an id on a PE-disjoint rectangle" preference, with the proof written next to the `Color(...)`
  call as the repo requires.
- Note the S6a `retain_rt` gate lives on the *caller* side (`decode.csl:1647`): when a round retains
  its KV, the per-layer ingress phases are skipped entirely and only the metainfo phase runs — the
  flush/rebind path is unchanged. Consistent with the skill's Gate-0 point that a retained cache is a
  **cursor edit, not a movement**.

### Colors and queues, whole file

| Queue | Color | Carries |
|---|---|---|
| IQ0 | `inter_block_a` (19), or `x_input_color` (23) on `is_x_receiver` | inter-block X recv (option A) |
| IQ1 | `inter_block_b` (20) | inter-block X recv (option B) |
| IQ2 | `intra_row_bcast` (6) | intra-block X fan-out recv |
| IQ3 / OQ3 | `reduce_1st_color_0` (1) | phase-1 chain, even parity |
| IQ4 / OQ4 | `reduce_1st_color_1` (2) | phase-1 chain, odd parity |
| IQ5 / OQ5 | `reduce_2nd_color_0` (3) | phase-2 chain, even parity |
| IQ6 / OQ6 | `reduce_2nd_color_1` (4) | phase-2 chain, odd parity |
| IQ7 / OQ7 | `broadcast_color` (5) — **or** `kv_ingress_color_0/1` (17/21) before the rebind | reduce broadcast; KV ingress at boot / per round |
| OQ0 | `intra_row_bcast` (6), **or** `result_color` on `is_result_sender` | intra-block X fan-out send |
| OQ1 / OQ2 | `inter_block_a` / `inter_block_b` | inter-block Z send |

Collective ids 1–5 are additionally reused by the K-pipe strip routes (`launch.py:588-591, 652-659`) —
block PEs and strip PEs live at disjoint X coordinates with disjoint router directions.
**Every queue is bound; none is free** — contrast prefill, which leaves q4 unused.

## Summary table

| Function | Pattern | Color(s) / queue | Axis | Role |
|---|---|---|---|---|
| `all_reduce_bsz_f32` (`:685`) | P-1 2-phase chain + P-2 bcast | c1/q3, c2/q4 · c3/q5, c4/q6 · c5/q7 | Y | RMSNorm sumsq, extent `bsz` |
| `all_reduce_bsz_dim` (`:1035`) | P-1 2-phase, **axis-polymorphic** | same five | Y *or* X | Score×V out, O-proj, FFN-down |
| `all_reduce_bsz_dim_QKV_fusion` (`:1115`) | P-1 + fused payload (G-3 step 0) | same five | Y | Q,K,V partials in one chain |
| `all_reduce_bsz_ffn_dim_ZZ_fusion` (`:1195`) | P-1 + fused payload | same five | Y | FFN up+gate in one chain |
| `all_reduce_bsz_gqa_group` (`:767`) | P-1 + P-8 pass 2 | same five | Y (KV positions) | softmax sum |
| `all_reduceMax_bsz_gqa_group` (`:848`) | P-1, operator swapped to `@fmaxh` | same five | Y (KV positions) | softmax global max (P-8 pass 1) |
| `all_reduce_qk_kv_head_scoped` (`:987`) | P-7 single-phase band reduce | c1/q3, c2/q4 · c5/q7 | kv-band (X) | Qwen3 QK-Norm, fused Q+K |
| `all_reduce_bsz_gqa_group_kv_len_kv_head_scoped` (`:931`) | P-7 single-phase band reduce | c1/q3, c2/q4 · c5/q7 | kv-band (X) | Q·Kᵀ score, fixed root |
| `inter_block_send_z` (`:1308`) / `inter_block_recv_x_sync` (`:1281`) | P-6 point-to-point along the snake | c19/OQ1, c20/OQ2 · IQ0, IQ1 | block edge | hidden-tile pipeline handoff |
| `intra_block_x_broadcast_y_bsz_dim` (`:1295`) | P-2 router multicast | c6 · IQ2 / OQ0 | X | fan the received X into every block row |
| `reconfig_allreduce_axis` (`:1335`) + `write_{Y,X,X_kv_head}_routes` (`:550-572`) | G-3 repaint, **fenceless** | the five collective colors | Y / X / kv-band | the one route-switch entry point |
| `precompute_route_words` (`:599`) / `init` (`:630`) | setup | — | — | 13 config words computed once; boots on Y |
| `kv_ingress_flush_then_resume` (`:1364`) / `kv_rebind_to_ingress_flush` (`:1368`) / `kv_ingress_oq_empty` (`:1351`) | G-14 drained queue borrow | IQ7/OQ7 ↔ {c5 \| c17,c21} | — | KV ingress borrows the broadcast queues, both directions (S6a) |

## What prefill has that decode does not

`two_hop_comm`, `left_matrix_shift`, `attn_right_hop`, `paint_band_routes` / `rebind_x_to_band` /
`restore_x_band` (the Score×V band Cannon), `run_shuttle` / `enter_source_shuttle` /
`enter_dest_shuttle_drained` / `rebind_shuttle_7_0` (the serpentine shuttle), `enter_qkt_reduce` /
`attn_score_reduce`'s cycling root, `restore_k_band_routes`, `reset_serve_state`,
`release_band_reduce_queues`, and the whole `RECFG_SH_OUT/IN` half of the reconfig machine.
Decode has **zero** microthreads and **zero** async fabric ops in this file.

## One line

Decode's `comm_pe.csl` is prefill's reduce skeleton with the pattern zoo deleted and the payload
table grown: because a decode step is `m = 1`, every GEMM collapses to a GEMV and every movement
collapses to **one two-phase chain all-reduce + multicast broadcast**, replayed at eight extents over
five colors that are repainted between three axes six times per layer — fenceless, safe only because
the collectives are synchronous and self-fencing, with the single genuine `@queue_flush` reserved for
the KV-ingress borrow of the broadcast queues.
