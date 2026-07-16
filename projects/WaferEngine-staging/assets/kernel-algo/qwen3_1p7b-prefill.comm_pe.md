# comm_pe.csl — the prefill block's communication toolbox

> Kernel algorithm walkthrough. Model `qwen3_1p7b-prefill`, ref config `test_sim_2x4_kv_varlen.json`
> (2×4 blocks, 8×8 PE/block). Diagram: `qwen3_1p7b-prefill.comm_pe.svg`.
> Comms taxonomy per the `cerebras-kernel-comm-patterns` skill (P-*/G-*).
> This file has **no `main()`** — every function here is *called by* `prefill.csl`'s drivers.

## Core idea — one scarce color/queue pool, time-shared across every phase

`comm_pe.csl` is the library that carries every cross-PE byte in a prefill layer: the RMSNorm/QK-Norm
reduces, the MeshGEMM (Cannon) matmul shifts, the GQA attention reduces, and the inter-block serpentine
shuttle that moves a block's hidden tile to the next block. It exposes **no new mechanism** — it is the
concrete implementation of the skill's P-1/P-3/P-5/P-6/P-7 patterns, wired onto a **fixed, small color +
queue budget** (`comm_pe.csl:110-131`). The design tension it resolves is that these patterns run in
different phases of the same layer but there are not enough fabric colors/queues to give each its own, so
resources are **time-multiplexed** and every rebind is fenced.

Two invariants make that safe, and they are the whole correctness story (no acks, no credits):

- **Count-exactness.** Both ends of every link derive the *same* wavelet count from their own
  block-local coordinates (`local_px_rt` / `local_py_rt` / `k_py_in_band_rt`, set in `init()` at
  `comm_pe.csl:239-274`). A mismatch is a **silent hang**, never an error.
- **Backpressure + parity ordering.** Bounded queues plus an acyclic movement graph are the entire
  flow control. The blocking shift register alternates send-then-recv (even PEs) vs recv-then-send (odd
  PEs) so adjacent hops never both block on each other (`run_shuttle`, `comm_pe.csl:916-925`).

Every queue rebind is either **drained by a synchronous reduce** that precedes it, or explicitly
**`@queue_flush`-drained** through a T29 empty-queue handler before the rebind fires. The header's
ownership map (`comm_pe.csl:110-131`) is the single source of truth for who owns what, when.

## Data distribution the collectives assume

A block is one `P_BLOCK_SIZE × P_BLOCK_SIZE` square (8×8 in the ref config). Within a block:

| Axis | Owns | Used by |
|---|---|---|
| **Y (rows, `local_py`)** | HIDDEN dim shard — PE owns `dim_per_pe` feature columns | RMSNorm reduce, QK-Norm band reduce, Q@Kᵀ / softmax band reduces, **left-matrix Cannon hop** (after the 90° rotation the left operand hops along Y). |
| **X (cols, `local_px`)** | SEQUENCE — PE owns `chunk_len_per_pe` tokens (`reduce_len = bsz·chunk_len_per_pe`) | **right-matrix Cannon hop** (weights hop along X), K\|V attention hops. |
| **kv-head band** (a contiguous run of `pes_per_kv_head` Y-PEs) | one KV head's Y-slice | P-7 band-scoped reduces (`all_reduce_k_band`, `attn_score_reduce`, `attn_vec_allreduce`). |
| **block boundary (X or Y edge)** | serpentine hop to the next block | P-5/P-6 shuttle (`run_shuttle`). |

Everything a reduce contracts lives on **Y** (the hidden shard); the matmul contraction is sharded both
ways after the Cannon rotation (left along Y, right along X); the shuttle crosses a single **block-edge**
axis chosen per block by `out_shuttle_dir` / `in_shuttle_dir`. No collective ever crosses a block boundary
— blocks exchange data only through the point-to-point shuttle (skill P-6).

The reduces all move a length-`reduce_len` **f32** vector and share **one DSD set** (`vector_buf_dsd` +
the `reduce_1st_*` / `bdcast_*` fabric DSDs, `comm_pe.csl:147-158`); only the painted routes differ. f32
throughout for HF parity (`comm_pe.csl:18-19`).

## The functions, grouped by pattern

### P-1 chain all-reduce — full-column Y reduce (RMSNorm)

Prefill's layer reduce is **one-phase** (a single bidirectional chain over all `P_BLOCK_SIZE` Y-PEs to
`root_2nd_phase`), not the two-phase `√P` split decode uses — the header notes this freed the
`reduce_2nd` color pair for the shuttle (`comm_pe.csl:120-123`).

- **`all_reduce_full`** (`comm_pe.csl:323-325`) → delegates to `all_reduce_band(local_py_rt,
  P_BLOCK_SIZE, root_2nd_phase, …)` — the whole Y column is one band.
- **`all_reduce_band`** (`comm_pe.csl:332-383`) is the shared engine: a bidirectional chain toward
  `band_root` (each PE `@fadds` its upstream neighbour's wavelet into its own partial and emits
  onward; parity picks which of the two chain colors carries rx vs tx), then a **P-2 router-multicast
  broadcast back** (`@mov32` from root on `bc_send`; every other PE does one `@mov32` from `bc_recv`,
  `comm_pe.csl:376-382`).
- **Colors/queues:** `reduce_1st_color_0`=c1/q5, `reduce_1st_color_1`=c2/q6, `broadcast_color`=c5/q1.
- **Deadlock-free:** synchronous `@fadds`/`@mov32` chain, no continuation task; a chain endpoint's
  dangling `rx` never fires because its path is send-only (`@fmovs`). Routes come from
  `reconfig(RECFG_FULL)`, painted before any wavelet (`init` boots in full mode, `comm_pe.csl:262`).

### P-7 band-scoped reduce — QK-Norm + GQA attention

A single-phase chain confined to one kv-head band (`pes_per_kv_head` Y-PEs) — cheaper than the two-phase
split because the band is small.

- **`all_reduce_k_band`** (`comm_pe.csl:385-387`) — QK-Norm sum-of-squares over the K (and Q, collapsed)
  band on the fixed `kv_head_root`. Same reduce colors, `RECFG_K` routes.
- **`attn_score_reduce`** (`comm_pe.csl:457-497`) — the Q@Kᵀ score reduce with a **cycling root and
  ZERO route repaint**. The trick (header `comm_pe.csl:404-408, 424-429`): split the band chain onto
  **two disjoint color pairs** — a SOUTH chain on `reduce_1st` colors 1,2 (q5,q6) and a NORTH chain on
  `north_south_aux` colors 3,4 (q7,q0). Each color's rx/tx then depends **only on band parity** (painted
  once by `enter_qkt_reduce`), so the per-step root advances in pure data logic with no repaint. Band
  edges are isolated by an `@fmovs` endpoint special-case, not by route termination.
- **`enter_qkt_reduce`** (`comm_pe.csl:430-450`) — rebinds queues 7,0 from the shuttle colors to the
  north-chain colors 3,4, then paints the four-color reduce routes **once** for the whole Q@Kᵀ.
- **`attn_vec_allreduce`** (`comm_pe.csl:501-539`) — softmax max/sum allreduce over the band on the
  **fixed** `kv_head_root` (`@fmaxs` or `@fadds`), then P-2 broadcast on `broadcast_color`. `RECFG_K`
  routes, restored by `restore_k_band_routes` (`comm_pe.csl:547-549`) after stage A's root cycling.
- **Colors/queues:** south = c1/q5 + c2/q6; north = c3/q7 + c4/q0; broadcast = c5/q1. Axis = Y within
  the kv band.
- **Deadlock-free:** routes painted once at entry on drained queues; the synchronous reduce leaves 7,0
  empty for the next rebind.

### P-3 Cannon / MeshGEMM — the two-hop systolic matmul comm

Textbook Cannon (both operands cyclically shift; **no broadcast in the GEMM**), embedded on a physical
line by the host's `trace_perm` snake. After the 90° rotation the **left** operand (activations) hops
along **Y** on the `x_*` channel and the **right** operand (weights) hops along **X** on the `y_*`
channel.

- **`two_hop_comm`** (`comm_pe.csl:823-852`) — one systolic step: left `@mov16` on the x channel
  (queue 2, ut1/2), right `@mov16` on the y channel (queue 3, ut3/4). Completions fire
  `left_matrix_finish_id` / `right_matrix_finish_id` (driver tasks in `prefill.csl`), which rendezvous
  before the next step's local MAC.
- **`left_matrix_shift`** (`comm_pe.csl:805-820`) — the initial left skew, `P/2` hops. **Reuses the x
  channel** (no dedicated x_shift color) — the skew runs to completion before the systolic steps, so the
  same color+queue carry both (`comm_pe.csl:80-82`). Its own completion task
  `left_matrix_shift_finish_id` keeps the skew rendezvous distinct from the step rendezvous.
- **`attn_right_hop`** (`comm_pe.csl:694-709`) — the right-channel-only X hop for the K tile (stage A)
  and V tile (stage C) of attention: one `@mov16` hop of `size` bf16 words on the y channel (queue 3),
  completion fires `attn_finish_id`.
- **Score×V band shift** — the LEFT (score) channel of `left_matrix_shift`/`two_hop_comm` is steered
  onto **band colors 18,19,20** (a 3-color interleave that reflects at kv-band edges,
  `trace_perm(pes_per_kv_head)`) which **time-share reduce queues 5,6,1** while the reduce is idle
  during attention. `band_active` (`comm_pe.csl:563`) picks the band DSDs (`_band_in_dsd`/`_band_out_dsd`,
  `comm_pe.csl:807-808, 827-828`); V stays on queue 3. `paint_band_routes` (`comm_pe.csl:577-618`) picks
  each PE's recv/send/transit role and paints the band-local two-hop routes at runtime.
- **Colors/queues:** left = `x_inter` c6,7,8 / q2; right = `y_inter` c9,10,11 / q3; band-shift =
  `band_color_0/1/2` c18,19,20 borrowing q5,q6,q1. Axis: left along Y, right along X, band along Y.
- **Deadlock-free:** async microthreads (`mm_ut1..4`) overlap the two channels; the driver's rendezvous
  is the step barrier. The band borrow is drained-safe — the preceding synchronous softmax leaves 5,6,1
  empty (`rebind_x_to_band`, `comm_pe.csl:648-652`); the async band send OQ is `@queue_flush`-drained on
  exit (`restore_x_band` → `band_drain_q5/q6/q1` T29 handlers → `band_resume`, `comm_pe.csl:663-678`)
  before 5,6,1 return to the reduce colors.

### P-5 / P-6 — inter-block serpentine shuttle

Moves this PE's `[dim_per_pe, reduce_len]` hidden tile (plus a 2-word metainfo tail) to the same-local-
coordinate PE one block over, along the serpentine.

- **`run_shuttle`** (`comm_pe.csl:886-931`) — the `P`-step **blocking shift register**. Zeros shift
  through a dest that starts empty; the source loads its tile into `buf_0`; ping-pong `bufA`/`bufB`
  swap each step. **Parity ordering** (even PE: send-then-recv; odd PE: recv-then-send,
  `comm_pe.csl:917-923`) is what makes it deadlock-free.
- **`enter_source_shuttle`** / **`enter_dest_shuttle`** (`comm_pe.csl:950-971`) — rebind queues 7,0 to
  this hop's axis colors (`rebind_shuttle_7_0`), paint **this hop's** route (`reconfig(RECFG_SH_OUT/IN)`
  — a per-hop repaint, because a pure-N/S serpentine middle block shares colors 3,4 for both its in-hop
  and out-hop and painting both at init left only the last-written, hanging the 1×N serpentine,
  `comm_pe.csl:953-958`), then `run_shuttle`.
- **`is_turn_block`** (`comm_pe.csl:980-983`) — true when in-hop and out-hop axes differ (a serpentine
  corner). Such a block ships chunk `c` then immediately wants chunk `c+1` as dest with no layer body
  between, so its OUT-axis send OQ still holds residual data.
- **`enter_dest_shuttle_drained`** (`comm_pe.csl:990-1002`) + **`shuttle_drain_q7`/`q0`** +
  **`shuttle_resume_dest`** (`comm_pe.csl:1003-1026`) — the turn-block per-chunk dest drain:
  `@queue_flush` the OUT-axis send OQ (the block blocks on the `c+1` recv anyway, so the drain is
  ~free), and the T29 handler rebinds 7,0 to the IN axis and runs the dest hop, then
  `chunk_resume_callback` (= prefill's `start_layers`).
- **`rebind_shuttle_7_0`** (`comm_pe.csl:937-944`) — bare queue-7↔c0 / queue-0↔c1 encode; MUST be
  called only when 7,0 are empty (every caller satisfies that structurally, so no flush).
- **Colors/queues:** N/S = `north_south_aux` c3,c4 / q7,q0; E/W = `shuttle_east_west` c12,c13 **reusing
  q7,q0** via the rebind. Axis: one block-edge (X or Y) per block.
- **Deadlock-free:** the pipeline is strictly sequential (each block parks at `init` until its
  predecessor ships; the dest parks event-driven on its first recv, not a spin loop). Both shuttle axes
  paint their shift routes once at init and the per-hop repaint on drained queues covers the same-axis
  overwrite.

### The `reconfig()` route-repaint machine (G-3 / G-9)

**`reconfig`** (`comm_pe.csl:283-317`) is the **one** route-switch entry point. Modes:

| mode | paints | on colors |
|---|---|---|
| `RECFG_FULL` | full-col Y reduce | reduce_1st (1,2) + broadcast (5) |
| `RECFG_K` | kv-head band reduce (Q collapses into K, interleaved layout) | reduce_1st + broadcast |
| `RECFG_SH_OUT` | this block's out-hop as a shift chain (source) | the hop's axis colors |
| `RECFG_SH_IN` | this block's in-hop as a shift chain (dest) | the hop's axis colors |

Reduce modes replay precomputed config words (`precompute_route_words` / `compute_band_words`,
`comm_pe.csl:216-237`). Shuttle modes compute send/recv direction from parity + block-edge guards
(`at_start`/`at_end`), and clamp at the physical block boundary via `route_calc.terminate_dir` (G-9)
because prefill runs one region spanning the whole fabric. Send color = rx:RAMP, tx:downstream; recv
color = rx:upstream, tx:RAMP; parity picks which of the two colors is send vs recv.

### Queue / color reuse and drained rebinds (G-14)

Two queue pairs and one channel are shared across phases; each borrow is drained before the rebind:

- **queues 7,0** — `north_south_aux` colors 3,4 carry the **N/S shuttle** *and* the **Q@Kᵀ north chain**;
  `shuttle_east_west` colors 12,13 carry the **E/W shuttle** — all three time-share q7,q0, rebound by
  `rebind_shuttle_7_0`. Safe because the synchronous reduce / shuttle leaves them empty (the header
  flags this as ASSERTED, not enforced — `comm_pe.csl:128-131`).
- **queues 5,6,1** — reduce colors 1,2,5 lend them to **band-shift** colors 18,19,20 during attention
  (`rebind_band_q_to_band` / `rebind_band_q_to_reduce`, `comm_pe.csl:623-644`). Exit is `@queue_flush`-
  gated through per-OQ T29 handlers.
- **queue 2** — the x (left) channel is shared by `two_hop_comm` and the `left_matrix_shift` skew (the
  skew completes before the steps).
- **queue 4 is free** (`comm_pe.csl:1041`).

Supporting state: `reset_serve_state` (`comm_pe.csl:567`) clears `band_active` at each request boundary
so a stale flag can't route the next request's shuttle through the band DSDs;
`release_band_reduce_queues` (`comm_pe.csl:684-689`) re-points the x DSRs back to the x channel after a
band shift so a following blocking reduce on 5/6/1 doesn't collide with the band's lingering async hold.

## Summary table

| Function | Pattern | Color(s) / queue | Axis | Role |
|---|---|---|---|---|
| `all_reduce_full` / `all_reduce_band` | P-1 chain all-reduce (one-phase) + P-2 bcast | reduce_1st c1/q5, c2/q6 · broadcast c5/q1 | Y (hidden) | RMSNorm sum-of-squares over full column |
| `all_reduce_k_band` | P-7 band reduce | reduce_1st c1,c2 · broadcast c5 | Y (kv band) | QK-Norm reduce on fixed kv root |
| `attn_score_reduce` / `enter_qkt_reduce` | P-7 band reduce, cycling root, zero repaint | south c1/q5,c2/q6 · **north c3/q7,c4/q0** | Y (kv band) | Q@Kᵀ score chain-to-root |
| `attn_vec_allreduce` | P-7 band reduce (max/sum) + P-2 bcast | reduce_1st c1,c2 · broadcast c5 | Y (kv band) | softmax max/sum on fixed kv root |
| `two_hop_comm` | P-3 Cannon step | left `x_inter` c6-8/q2 · right `y_inter` c9-11/q3 | left→Y, right→X | one systolic matmul step |
| `left_matrix_shift` | P-3 Cannon skew | `x_inter` c6-8/q2 (reused) | Y | initial left-operand skew |
| `attn_right_hop` | P-3 right-only hop | `y_inter` c9-11/q3 | X | K\|V tile shift |
| `paint_band_routes` / `rebind_x_to_band` / `restore_x_band` | P-3 Score×V rectangular Cannon | `band` c18/q5,c19/q6,c20/q1 (borrowed) | Y (kv band) | score (LEFT) band-local shift |
| `run_shuttle` | P-5 parity shift register / P-6 cross-block | N/S `north_south_aux` c3/q7,c4/q0 · E/W `shuttle_east_west` c12,c13 (reuse q7,q0) | one block-edge | move hidden tile to serpentine-next block |
| `enter_source_shuttle` / `enter_dest_shuttle` / `enter_dest_shuttle_drained` | P-5 shuttle drive + G-14 drained rebind | q7,q0 (rebound per axis) | block-edge | drive source / dest hop; flush-drain turn blocks |
| `reconfig` (+ `write_*_routes`) | G-3 route repaint / G-9 block-edge terminate | reduce_1st + broadcast · shuttle axis colors | Y / X / band-edge | the one route-switch entry point |
| `rebind_shuttle_7_0` / `rebind_band_q_to_*` | G-14 queue/color reuse | q7,q0 ↔ {c3,4 \| c12,13}; q5,6,1 ↔ {c1,2,5 \| c18,19,20} | — | time-share scarce queues, drained-safe |

## One line

`comm_pe.csl` runs decode's reduce/route skeleton plus prefill-only attention, Cannon, and serpentine
shuttle over **one scarce color+queue pool** — every phase borrows queues 7,0 (shuttle ↔ Q@Kᵀ north) or
5,6,1 (reduce ↔ Score×V band) from another, and every borrow is safe because the movement is a
compile-time permutation with count-exact endpoints and each rebind lands only on a drained queue.
