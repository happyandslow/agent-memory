# ht_tail.csl — lm_head mesh-GEMV + top-K sampling (the output head)

> Kernel algorithm walkthrough. Model `qwen3_1p7b-prefill`, ref config `test_sim_2x4_kv_varlen.json`.
> Diagram: `qwen3_1p7b-prefill.ht_tail.svg`. Comms taxonomy per the `cerebras-kernel-comm-patterns` skill.

## Core idea — turn the last hidden state into one sampled token

`ht_tail` is the final stage of the prefill pipeline. It takes the **last token's hidden vector** `Z`
(dim-sharded, shipped west out of the last serpentine block), and produces **one next-token id** plus its
top-K logits, handed south to the host. Prefill is one-shot: the whole flow runs **once per request**
(`tail_main`, `ht_tail.csl:1110`), unlike decode which loops it per generated step.

Five acts, all on a `HT_WIDTH × P_BLOCK_SIZE` band (ref: 4×8):
1. **Drain `Z`** — the last block multicasts `Z` west across the vocab columns; every tail PE taps its own dim shard (`:1120`, route `:1035-1039`).
2. **Final `LlamaModel.norm`** (RMSNorm, fp32) in place on `Z` — a Y-axis all-reduce of the per-batch sum-of-squares over the dim shards (`tail_final_rmsnorm`, `:352-415`).
3. **lm_head GEMV** — each PE does a *local* matvec `partials[V_per_pe_x, bsz] = lm_head_tile @ Z` over its vocab slice (`tail_lm_head_matvec`, `:334-343`), then a **Y-axis 2-phase reduce (no broadcast)** contracts the dim shards → full logits land on the phase-2 root row (`tail_logits_reduce_bsz_vocab`, `:655`, `:1127`).
4. **Top-K** — the root row runs a local top-K over each PE's vocab slice (`tail_local_topk`, `:774-804`), then an **X-axis 2-phase merge-reduce** combines them into the global top-K (`tail_topk_mergereduce_x`, `:834`), replicated across the root row.
5. **Sample + emit** — the single sampling PE draws one token (temperature → softmax → top-p → categorical PRNG; `tail_sample_token`, `:963-996`); the root-row east-most PE emits `{topk_val, topk_arg, sampled token}` south to the mux → host (`:1157-1162`).

The one clever reuse: the **same 5 reduce colors + queues carry both the Y-axis dim-contraction reduce and
the X-axis top-K merge-reduce**. Between them the root row *repaints the routes at runtime* (Y→X via
`write_X_routes_tail`, `:531`, then back via `write_Y_routes_tail`, `:419`), fenced by a one-wavelet
cross-column barrier so no PE emits an X-mode wavelet into a neighbor still painted for Y
(`tail_xready_color`, `:1137-1141`). This is the skill's G-3 route-repaint + G-8 fence idiom, and it is why
the tail spends zero new color ids on the horizontal reduce.

## Data distribution on PEs

Tail band = **HT_WIDTH columns (X, vocab shard) × P_BLOCK_SIZE rows (Y, dim shard)** (ref 2×4 config: 4×8).
Vocab is sharded on **X**; the hidden dim (the GEMV contraction axis) is sharded on **Y**.

| Tensor | Sharding | Notes |
|---|---|---|
| `lm_head_tile` (`:105`) | vocab on **X**, dim on **Y** → `[dim_per_pe, V_per_pe_x]` per PE | dim-outer / vocab-inner (K-outer) so the GEMV reads `K=dim` outer; host `.T`s the `(vocab,dim)` HF slice before upload (`launch.py:1386`), else logits scramble. Tied to `W_E`. ref: `[8, 16]`. |
| `z_slice_buf` (`:106`) | dim on **Y**, **replicated on X** | the post-norm hidden shard; `Z` multicasts west so every vocab column in a Y-row holds the same `dim_per_pe` slice. ref: `[bsz=1, 8]`. |
| `partials_buf` (`:109`) | vocab on **X**, per-Y **partial** (fp32) | this PE's logit slice `[bsz, V_per_pe_x]`; only a partial until the Y-reduce contracts the dim shards. ref: `[1, 16]`, fp32 for HF parity. |
| `W_final_norm_tile` (`:117`) | dim on **Y**, replicated on X | RMSNorm weight slice `[dim_per_pe]`. |
| `topk_val` / `topk_arg` (`:238-239`) | seeded local, then **global** on the root row | after the X merge-reduce + broadcast, every root-row X-PE holds the global top-K `[TOP_K*bsz]` (round-outer / batch-inner). `topk_arg` is i32 (device vocab id can exceed u16). |
| `pred_token_buf` (`:232`) | root row, i32 | the sampled next-token id per batch; X-broadcast across the root row for the south emit. |

Derived dims (ref config): `P_BLOCK_SIZE=8`, `dim_per_pe=8`, `HT_WIDTH_tail=4`, `V_per_pe_x=16`, `bsz=1`,
`TOP_K=20`. Y chain: `pe_num_per_group=4`, `root_2nd_phase=6`. X chain: `pe_num_per_group_x=2`,
`root_2nd_phase_x=3` — which lands the sampling PE, the south emitter, and the TSC PE all on the **east-most
root cell** `(x=HT_WIDTH-1, y=root_2nd_phase)`.

## Communications + which task owns each step

**Phase 0 · setup (`tail_init`, `:1017`)** — reads its wafer coord, derives local `(x, py)` + both chain
ids, paints Y routes (`write_Y_routes_tail`), the `Z`-drain multicast route (`:1035`), the south-emit route
(`:1044`), the X-phase barrier tree (`:1051`), and the TSC kickoff route (`:1082`); seeds the PRNG on the
sampling PE (`:1079`); `@activate(tail_main)`.

**Phase 1 · drain Z (P-2 router multicast, west-flowing)**
- `tail_main` parks on `z_recv_dsd` (`:1120`, event-driven) until the last block ships `Z` east into the
  tail's east edge. `Z` multicasts **EAST→WEST** on `z_drain_color` (color 16); the west-most PE terminates
  (`EAST→RAMP`), interior/east PEs tap + forward (`EAST→{RAMP,WEST}`, `:1035-1039`). Each Y-row PE keeps its
  own `dim_per_pe` slice.

**Phase 2 · final RMSNorm (P-1 two-phase all-reduce, with broadcast)**
- `tail_final_rmsnorm` (`:352`): each PE squares its dim shard to a local sumsq (fp32), then
  `tail_reduce_bsz_f32` (`:754`) → `tail_reduce_2phase` (`:661`) does a **Y-axis 2-phase chain all-reduce**
  of the `bsz` sums *with* the broadcast leg (`do_broadcast=1`), so every Y-PE gets the full-dim variance.
  Normalize + cast + `* W_final_norm`, in place over `z_slice_buf`.

**Phase 3 · lm_head GEMV + dim-contraction reduce (local matvec + P-1 two-phase reduce, no broadcast)**
- `tail_lm_head_matvec` (`:334`): purely **local** `@fmachs` GEMV (`vecmat_computation_lm`, `:313`) →
  `partials_buf[V_per_pe_x, bsz]` fp32. No comms.
- `tail_logits_reduce_bsz_vocab` (`:655`, `:1127`): reuses `tail_reduce_2phase` with the *longer* extent
  `bsz*V_per_pe_x` and **no** broadcast — the full logits land only on `root_2nd_phase`. (Same fabric DSDs,
  different `@set_dsd_length` — the skill's "widen an existing payload" idiom, done safely by resetting base
  addr + length on entry, `:662-663`.)

**Phase 4 · top-K (root row only; P-1 two-phase reduce with a merge combiner, on repainted X routes)**
- `write_X_routes_tail` (`:531`) repaints reduce colors 1–5 from Y to X; the sampling PE broadcasts a
  1-wavelet "go" on `tail_xready_color` (`:1137-1141`) and every other root column blocks on it (G-8 fence)
  before any X send.
- `tail_local_topk` (`:774`): K masked-argmax passes over this PE's `V_per_pe_x` logit slice → seeds
  `topk_val`/`topk_arg`; padded vocab entries are masked to `NEG_SENT` first (`:781`, no-op here since
  `vocab_pad_count=0`).
- `tail_topk_mergereduce_x` (`:834`): **X-axis 2-phase reduce** whose per-hop combine is a K-list 2-pointer
  merge (`topk_merge_local`, `:808`), **not** a sum — each hop recvs `KB` fp16 vals + `KB` i32 ids, merges
  into the running top-K, sends it on. Final broadcast replicates the global top-K to every root-row X-PE.
  Then `write_Y_routes_tail` restores Y routes (`:1152`).

**Phase 5 · sample + emit (single PE draws; east-most PE ships south)**
- `tail_sample_token` (`:963`, `root_2nd_phase_x` only): temperature scale → fp32 softmax over the sorted
  top-K → top-p nucleus truncation → categorical draw via the hardware PRNG → `pred_token_buf`. The sampled
  id is **X-broadcast** to every root column (`predtok_bcast`, `:1148-1151`) so the east-most PE has it.
- South emit (`:1157-1162`, `x==HT_WIDTH-1 & y==root_2nd_phase` only): `TOP_K*bsz` fp16 values + `TOP_K*bsz`
  i32 ids + `bsz` sampled token (+ even-count pad) on `logits_south_color` (OQ 0). It transits down the east
  column to `Edge.BOTTOM` → the mux (`launch.py:1398-1418`) → host output stream (`launch.py:1421-1425`).
- **TSC timing** (`is_tsc_pe`, the same east-most root cell): samples `start` on the forward-start kickoff
  sentinel (`:1115-1118`) and `end` after the blob (`:1166-1175`), piggybacking an 8-u32 burst on the south
  path. The kickoff sentinel arrives from demux PE 0 via manual fabric (`kickoff_color`, color 17).

## Communication summary

| Movement | color / queue | axis / direction | pattern | task / fn |
|---|---|---|---|---|
| `Z` drain into tail | `z_drain_color` (16) / IQ0 | X, **E→W** multicast | **P-2 router multicast** | `tail_init` route / `tail_main` `z_recv` |
| RMSNorm sumsq reduce | reduce 1st/2nd + bcast / IQ·OQ 2-6 | Y (dim), reduce+bcast | **P-1 two-phase all-reduce** | `tail_reduce_bsz_f32`→`tail_reduce_2phase` |
| lm_head dim-contract | same reduce colors / IQ·OQ 2-5 | Y (dim), reduce **no bcast** | **P-1 two-phase reduce** (widened DSD) | `tail_logits_reduce_bsz_vocab` |
| top-K merge | same reduce colors, **repainted** / IQ·OQ 2-6 | X (vocab), reduce+bcast | **P-1 two-phase reduce, merge combiner** (G-3 repaint + G-8 fence) | `tail_topk_mergereduce_x` |
| X-phase barrier | `tail_xready_color` / IQ·OQ 1 | X, 1-wavelet | **G-8 fence** (sentinel barrier) | `tail_main` (`:1137`) |
| sampled-token spread | `broadcast_color` / OQ·IQ 6 | X, 1→many | **P-2 broadcast** | `predtok_bcast` (`:1148`) |
| top-K + token → host | `logits_south_color` / OQ0 | Y, **RAMP→S** then N→S | **P-6 p2p south emit** → mux → host | `tail_main` (`:1157`) |
| forward-start kickoff | `kickoff_color` (17) / IQ7 | manual fabric → RAMP | 1-wavelet TSC anchor | `tail_main` (`:1116`) |

Correctness is **count-exactness**: both ends of every reduce/emit compute the same wavelet count from
`local_px` / chain ids / `V_per_pe_x` / `TOP_K` — a mismatch is a silent hang. The repaint fence exists for
the same reason: without the barrier a column still in Y-route mode would receive an X-mode wavelet it
cannot route.

## One line

Same program on every tail PE; the wafer coord picks each PE's vocab slice (X) and dim slice (Y). `ht_tail`
does a local lm_head GEMV, contracts the dim shards with a Y-axis two-phase reduce, then **reuses those very
reduce colors — repainted to X and fenced — to merge per-column top-K lists into one global top-K**, samples
a single token on one PE, and ships it south to the host. A vocab-parallel output head becomes two
orthogonal two-phase reductions plus one local sample.
