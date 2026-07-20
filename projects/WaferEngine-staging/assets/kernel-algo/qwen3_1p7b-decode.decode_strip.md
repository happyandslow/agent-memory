# decode_strip.csl — the K-pipe strip: inter-region Z handoff as an 8-way interleaved shift register

> Kernel algorithm walkthrough. Model `qwen3_1p7b-decode`, ref config `test_sim_2x2block_kv_varlen.json`.
> Diagram: `qwen3_1p7b-decode.decode_strip.svg`. Comms taxonomy per the `cerebras-kernel-comm-patterns` skill.
> **Git state: the CURRENT WORKING TREE of branch `lexu/staging/s6a-inner-pe-kv-route-a`, with the
> uncommitted S6a KV-retain work applied** (this is what makes `kv_stream_ingress=1` the continuous-relay
> path described below). Not a committed ref.

## Core idea — the snake's row-to-row seam needs a wire, and there is only one column

`decode_strip.csl` is **not a standalone region**. It is a module `@import_module`'d by `decode.csl`
(`decode.csl:1527-1531`) and it runs on the **two placeholder columns that bracket every row region**:
`lcl_x = 0` (west strip) and `lcl_x = Pw+1` (east strip) (`launch.py:1050-1056,1072-1073`). Every PE in a
row region loads the same `decode.csl` binary; `dispatch_init_task` recovers "am I a strip cell?" at
runtime from fabric coordinates and branches (`decode.csl:1657-1672`).

The problem it solves: decode lays its blocks out as a **serpentine snake**, and when the pipeline leaves
row `r` it must enter row `r+1`. The activation `Z` at that seam is sharded on **Y** — PE at region-row
`py` owns `bsz × dim_per_pe` values of it. Those shares must land on the **same `py`** one row region
south. Physically they can only travel down **one column of PEs**, so all `P_BLOCK_SIZE` shares contend
for one wire.

A naive per-cell store-and-forward down that column is exactly what the skill's hard constraints forbid:
depth `P`, and the top cell's forward extent is `(P-1)·B`, which is the kind of quantity that overflows
the i16 fabric-DSD extent at real block sizes. The K-pipe answer is to **interleave `K=8` independent
pipes on 8 color pairs** (`launch.py:642,658-661`). Pipe `k` owns the cells with `py ≡ k (mod K)`, so each
pipe has only `M = P_BLOCK_SIZE / K` own-cells per column (`decode.csl:1514`). Relay depth drops from `P`
to `M`, and the worst-case forward extent from `(P-1)·B` to `(M-1)·B`
(`decode_strip.csl:44`). Non-own cells are pure **router pass-through** — zero buffered state, which is
the uniform-peak-memory rule (`launch.py:1273`, `kpipe_pass_route`).

So the strip is a **P-5 parity shift chain used as a G-2 FIFO peel**, replicated 8× on disjoint colors,
with a **P-6 point-to-point** feeding it at the top and a **P-2 router multicast** draining it at the
bottom. It is the only cross-block movement in decode, per the skill's Gate-2 table.

## Data distribution on PEs

Ref config `test_sim_2x2block_kv_varlen.json`: `Pw=Ph=16`, `P_X_BLOCK_NUM=P_Y_BLOCK_NUM=2`,
`P_BLOCK_SIZE=16`, `bsz=2`, `dim=64`, `MAX_SEQ_LEN=32`, `NUM_ROUNDS=3`, `KV_TRANSFER=1`.
Derived: `dim_per_pe = 64/16 = 4`, `B = bsz·dim_per_pe = 8` f16 wavelets per cell per step,
`KPIPE_K = 8`, `KPIPE_M_PER_PIPE = 16/8 = 2`,
`MAX_OUTPUT_LEN(strip) = max_output_len_worst × num_rounds = (32-16) × 3 = 48` (`launch.py:381,1118`).

| Quantity | Value / sharding | Notes |
|---|---|---|
| `strip_buf[bsz·dim_per_pe]` | f16, **Y-sharded**: cell at `region_py` holds exactly that `py`'s slice of the hidden dim | the only per-cell state; `decode_strip.csl:34-35` |
| pipe id `k_own` | `region_py mod 8` | which of the 8 color pairs this cell rides (`decode.csl:1693`) |
| own-cell index `i_own` | `region_py div 8` ∈ `[0, M)` | position **within** the pipe (`decode.csl:1694`) |
| `strip_fwd_extent` | sender `i_own·B`; receiver `(M-1-i_own)·B` | how many *other* cells' wavelets this cell relays (`decode_strip.csl:150-159`) |
| `strip_iter` | 0 … `MAX_OUTPUT_LEN` (=48) | continuous-relay ceiling across **all rounds**, not per round (`decode_strip.csl:16,70,111`) |

**Gate 0 check.** `Z` is genuinely sharded along Y (`dim_per_pe` per row) and the movement is a
**Y-preserving translation by one region height** — a permutation, not a reduction. Nothing is summed
here, so no all-reduce is indicated, and no cross-block collective is being smuggled in: this is the
sanctioned `inter_block_*` point-to-point path.

**Which strips are real.** Every row region has both columns for uniform shape, but only sides carrying
inter-region traffic are "real" (`launch.py:140-163`, `strip_realness`). At 2×2: row 0 is even (snakes
east) → real **east** strip, role **sender**; row 1 is odd (snakes west) → real **east** strip, role
**receiver**. The two sit in the **same fabric column**, stacked vertically — that column is the K-pipe.
Fake strips return immediately (`decode.csl:1674-1679`); their `pre_embed_x` / `result_color` transit is
painted at compile time only.

## Communications + which task owns each step

### 0 · Identity + queue rebind (once, before any relay)

`dispatch_init_task` (`decode.csl:1657`) is the gate. It computes `region_px/py` from
`get_fabric_coord`, branches block-vs-strip, drops fake strips, then derives role and parity:

- **role**: `strip_role = 1` (receiver) iff `strip_side == row_y_parity`, else `0` (sender)
  (`decode.csl:1683-1686`).
- **parity**: `i_glob = i_own` for the sender, `M + i_own` for the receiver — the `+M` offset makes the
  a/b alternation **continue unbroken across the region boundary** (`decode.csl:1695-1704`). This is
  **G-1 two-color parity alternation**: consecutive own-cells swap which of `kpipe_a_k` / `kpipe_b_k` is
  rx and which is tx, so no cell ever receives and transmits on the same color.
- **queue rebind (G-14-flavored, but at init, not mid-run)**: `comm_pe.csl` has already bound IQ3–IQ7 as
  masters for collective colors 1–5, and the K-pipe **reuses those same ids**. The strip parks IQ3–IQ7 on
  the unrouted `x_input_color` first, precisely so the IQ2 rebind does not trip "two master input queues
  for the same color" (`decode.csl:1706-1714`). Then IQ2 ← `rx_color`, OQ7 ← `tx_color`
  (`decode.csl:1712-1714`; endpoint map `decode_strip.csl:9-12,29-32`).
- Finally `activate_sender(i_own)` / `activate_receiver(i_own)` (`decode.csl:1727,1733`), which set
  `strip_fwd_extent` and fire the head task (`decode_strip.csl:150-160`).

The color-id reuse is legal by the **disjoint-rectangle** rule and launch.py writes the proof beside it:
block PEs and strip PEs live at disjoint X with disjoint router directions (`launch.py:588-591`).

### 1 · Block → sender strip (P-6 point-to-point, one hop)

The sender block's snake-tail edge column emits its Y-share on `inter_block_a_color` / `inter_block_b_color`
(ids 19/20). The strip column is painted `block_facing → RAMP` for both — `EAST` for a west strip, `WEST`
for an east strip (`launch.py:1266,1293-1297`). Which of a/b is live alternates by the sender block's
**pipeline index**, so the strip swaps IQ0/IQ1 on odd parity to keep q0 always the active one
(`decode.csl:1717-1724`) — G-1 again, one level up.

- **`strip_sender_recv_t`** (`decode_strip.csl:69-81`) — guards on `strip_iter >= MAX_OUTPUT_LEN` and on
  `strip_stop`, increments, then `@fmovh(strip_buf_dsd, sender_recv_dsd, .{.async=true, .activate=fwd})`
  pulls its own `B` wavelets off IQ0.

### 2 · Down the K-pipe (P-5 parity shift chain, cut-through)

Routes, painted per-cell in `_paint_real_strip_col` (`launch.py:1245-1303`):

| route | painted on | direction |
|---|---|---|
| `kpipe_pass_route` | **whole** strip column, both a and b, all 8 pipes | `NORTH → SOUTH` |
| `kpipe_rx_route` | own-cells only (`py ≡ k mod 8`), on `rx_c` | `NORTH → RAMP` |
| `kpipe_tx_route` | own-cells only, on `tx_c` | `RAMP → SOUTH` |

The per-cell rx/tx paints override the pass-through on exactly the two colors of that cell's pipe; every
other pipe streams past untouched. `global_offset = 0` for the sender column and `M` for the receiver
column (`launch.py:1277`) — the same `+M` that keeps parity continuous.

**Sender ordering: forward first, then inject.**
- **`strip_sender_fwd_t`** (`decode_strip.csl:83-100`) — relays `strip_fwd_extent = i_own·B` wavelets
  fabric→fabric via `@set_dsd_length` on the max-extent templates (`decode_strip.csl:45-50,93-96`). If the
  extent is zero (the topmost own-cell) it just `@activate`s the next task.
- **`strip_sender_inject_t`** (`decode_strip.csl:102-107`) — appends its **own** `B` wavelets, then
  re-activates `recv_t` for the next step.

Because own-cells forward everything above them before injecting, the stream leaving the bottom of the
sender column is exactly `own_0 ‖ own_1 ‖ … ‖ own_{M-1}`, `M·B` wavelets per pipe per step.

**Receiver ordering: consume first, then forward** — this is the **G-2 FIFO peel**.
- **`strip_recv_consume_t`** (`decode_strip.csl:110-122`) — same guards, then takes the **first** `B`
  wavelets off IQ2 into `strip_buf`. Receiver `own_0` is the topmost cell, so it peels sender `own_0`'s
  share; `own_j` peels `own_j`'s. The translation is therefore **Y-preserving**, which is the whole point.
- **`strip_recv_postfwd_t`** (`decode_strip.csl:124-140`) — relays the remaining
  `(M-1-i_own)·B` wavelets south to the cells below.

Deadlock-freedom is **count-exactness**, computed independently on both sides from `i_own` alone:
sender `own_i` emits `(i+1)·B`, receiver `own_j` consumes `B` and passes `(M-1-j)·B`. Every link's two
ends derive the same number from their own coordinates. A one-sided change is a **silent hang**.

### 3 · Receiver strip → block (P-2 router multicast along X)

- **`strip_recv_broadcast_t`** (`decode_strip.csl:142-146`) — `@fmovh(recv_broadcast_dsd, strip_buf_dsd)`
  onto `intra_row_bcast_color` (id 6) via **OQ0**, painted `RAMP → block_facing`
  (`launch.py:1299-1302`). The router replicates along the row, so all `Pw` block columns at that `py`
  receive the same Y-share in one send — a genuine multicast, not a software fan-out. Then it
  re-activates `consume_t`.

### 4 · Early stop (G-5 sentinel-in-payload)

When a block exits early it relays a **STOP-X**: `strip_buf[0] = NEG_INF`, detected against
`STRIP_STOP_THRESHOLD_F16 = -60000.0` (`decode_strip.csl:62`). The critical discipline, stated in the code
comments and worth repeating: **the STOP step still runs the full relay**
(`decode_strip.csl:84-90,125-130`). Every cell injects its own STOP-X so the per-step wavelet count is
unchanged; skipping the forward would desync the shift register and hang the device. `strip_stop` only
suppresses the **re-loop** afterwards.

### 5 · Rounds — the S6a continuous-relay change

With `kv_stream_ingress = 1` (`KV_TRANSFER: 1` in the ref config) the head tasks do **not** end the chain
on `strip_stop`; they clear it and continue, parking on the next recv until the block re-arms
(`decode_strip.csl:18-20,73-76,114-117`). The strip therefore relays **continuously across all
`NUM_ROUNDS` rounds**, bounded only by the single ceiling `MAX_OUTPUT_LEN = W × NUM_ROUNDS = 48`
(`launch.py:1115-1118`). With `kv_stream_ingress = 0` the chain simply ends. This is the one place where
the strip's control flow is round-aware, and it is the reason `MAX_OUTPUT_LEN` is scaled by `num_rounds`
for the strip while `n_steps` stays per-round for the blocks.

## Communication summary

| Movement | color / queue | direction | pattern | task(s) |
|---|---|---|---|---|
| block edge col → sender strip (`B` per cell) | `inter_block_{a,b}_color` (19/20) / **IQ0** | `block_facing → RAMP` | **P-6 point-to-point** + G-1 parity by pipeline index | `strip_sender_recv_t` |
| upstream relay through sender own-cell | `kpipe_{a,b}_k` / IQ2 → OQ7 | `NORTH → SOUTH` (cut-through) | **P-5 parity shift chain**, G-12 payload-opaque relay | `strip_sender_fwd_t` |
| own share injected onto the pipe | `kpipe_{a,b}_k` / **OQ7** | `RAMP → SOUTH` | **P-5** chain append | `strip_sender_inject_t` |
| non-own cells (all 8 pipes) | both pipe colors | `NORTH → SOUTH` | router pass-through, zero state | *(no task — pure route)* |
| pipe → receiver own-cell (peel `B`) | `kpipe_{a,b}_k` / **IQ2** | `NORTH → RAMP` | **G-2 FIFO peel** | `strip_recv_consume_t` |
| downstream relay through receiver own-cell | `kpipe_{a,b}_k` / IQ2 → OQ7 | `NORTH → SOUTH` | **P-5** chain | `strip_recv_postfwd_t` |
| receiver strip → whole receiver row | `intra_row_bcast_color` (6) / **OQ0** | `RAMP → block_facing` | **P-2 router multicast** | `strip_recv_broadcast_t` |
| STOP-X | *(in-band, `buf[0]`)* | rides every leg | **G-5 sentinel-in-payload** | fwd / postfwd |

Colors 1–5 are **shared ids** between the block collectives and K-pipe pipes 0–2; the disjointness proof
(block cells vs strip cells at disjoint X, disjoint router directions) is written beside the allocation at
`launch.py:588-591,653-657`. K-pipe pipe 3 (ids 8/9) is further aliased by HT_head's SOUTH chain, again on
a disjoint fabric-x band (`launch.py:689-694`).

## One line

The strip is the snake's seam: `K=8` interleaved parity shift-chains running down the one column that
connects two row regions, where each own-cell forwards everything above it and then appends its own
`bsz·dim_per_pe` slice — so the stream arrives pre-ordered and the receiving cells peel it FIFO,
Y-share for Y-share, before multicasting into their row. Splitting into 8 pipes is not bandwidth
engineering, it is what keeps relay depth at `M = P/8` and the forward extent inside the i16 fabric-DSD
limit.
