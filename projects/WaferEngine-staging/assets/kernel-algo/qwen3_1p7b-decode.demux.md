# demux.csl (decode) — host X[0] seed ingress (1×P column peel + east fan-out)

> Kernel algorithm walkthrough. Model `qwen3_1p7b-decode`, ref config `test_sim_2x2block_kv_varlen.json`.
> Diagram: `qwen3_1p7b-decode.demux.svg`. Comms taxonomy per the `cerebras-kernel-comm-patterns` skill.
> **Git state:** branch `lexu/staging/s6a-inner-pe-kv-route-a`, working tree dirty with the uncommitted
> S6a KV-retain work. `src/demux.csl` and `launch.py`'s demux region are themselves **unmodified vs
> `fcfc8c1`**, so this doc describes code identical at HEAD and in the tree.

## Core idea — peel your own row, pass the rest SOUTH, drop it EAST

Same store-and-forward skeleton as prefill's demux, rotated 90° and carrying different cargo.

| | prefill demux | decode demux |
|---|---|---|
| Shape | `HWh × 1` — a **row**, one row NORTH of HT_head | `1 × P_BLOCK_SIZE` — a **column**, one col WEST of the HT band (`launch.py:739-740, 720-721`) |
| Chain direction | W → E | **N → S** (`demux.csl:1-2`; `launch.py:773-775`) |
| Emit direction | SOUTH into HT_head | **EAST** into HT_head's west edge (`launch.py:799-801`) |
| Cargo | **token ids** + a 3-word metainfo prefix, for every chunk of every request | the **pre-embedded hidden vector `X[0]`** for the seed tokens — fp16, already looked up **on the host** (`launch.py:2399-2413`) |
| Duty cycle | every chunk of every request | **once per decode round**, then idle; steps 1+ are pure on-chip (`demux.csl:1-4`) |
| Extra sentinel | emits a **kickoff TSC** sentinel south | **receives** a **ready barrier** from HT_head before it may start (`:104-107`) |

The reason for the difference is the same one that reshapes decode's `ht_head`: decode embeds one
sampled token per step, fed back on-chip from HT_tail, so the host only ever supplies the **step-0
seed**. The host embeds that seed itself in numpy rather than paying a device lookup for it, so the
demux carries hidden-state fp16 (packed 2-per-u32), not token ids.

The distribution problem is unchanged and so is the answer: the host has one flat stream, the hidden
state is sharded along **Y**, the fabric cannot address a wavelet to "row *k*" (Gate 1), so the column
is a peel-and-forward chain. Every hop is a static permutation computed from `my_idx`.

## Data distribution on PEs

demux region = **1 column (X) × `P_BLOCK_SIZE` rows (Y)** at `fabric_x = DEMUX_FAB_X = 2`, `y = PLACE_Y`
(`launch.py:568, 720-721, 825`). Ref config: **8 PEs** (`P_BLOCK_SIZE = Pw/P_X_BLOCK_NUM = 16/2 = 8`).

| Quantity | Value / sharding | Notes |
|---|---|---|
| `OWN_B` | `batch_per_pe_step = bsz·dim_per_pe/2` (ref: `2·8/2 = **8** u32`) | one row's slice of `X[0]`: `bsz` lanes × `dim_per_pe` fp16, packed 2 per u32 (`demux.csl:18, 34`; `launch.py:494`). |
| `FWD_EXTENT` | `(P_BLOCK_SIZE−1−my_idx)·OWN_B`; **1** (unused stub) on the last PE | wavelets relayed south = all downstream rows' slices (`demux.csl:35-39`). |
| `own_buf[OWN_B]` | local staging | the peeled slice, re-emitted east (`demux.csl:45-50`). |
| host stream total | `P_BLOCK_SIZE · OWN_B` u32 per round | `x_per_col = X[0].reshape(bsz, P, dim_per_pe).transpose(1,0,2)` — **row-major by PE row** so PE `k`'s slice sits at offset `k·OWN_B` (`launch.py:2412-2414`). |

There is **no metainfo prefix** here — prefill's 3 opaque words have no decode counterpart; the per-round
budget `N` travels the *token* path instead (HT_tail → HT_head), not this one.

## Communications + which task owns each step

**Phase 0 · `init` — wait for HT_head to finish painting (`:104-107`)**
- `@mov32(ready_buf_dsd, ready_recv_dsd, .{ .async = true, .activate = main_id })`: each demux PE parks
  on **1 wavelet** from the HT_head col-0 PE at the same `fabric_y`, arriving on `ht_ready_color`
  (**id 0**) through the 1-column gap (`launch.py:816-824, 2330`).
- **Why it exists:** HT_head paints `pre_embed_x_color`'s per-row route at *runtime* inside its `init`
  (`ht_head.csl:264-268`), but the demux could otherwise emit at load time. The barrier converts that
  race into an ordering. Without it, `bsz=1` configs stall (`launch.py:997-999`). This is the
  G-8 repaint-fence idea applied to a *first*-paint rather than a re-paint.

**Phase 1 · `main` — peel `OWN_B` off the head of the stream (`:109-120`)**
- PE 0 receives the whole `P·OWN_B` stream from the **host** on `in_color` via `Edge.TOP`
  (`launch.py:804-808, 2341-2342`); PE `k ≥ 1` receives `(P−k)·OWN_B` from PE `k−1` on a chain color.
- One `@mov32` drains the first `OWN_B` into `own_buf`. Both fabin DSDs share `src_q` (iq2), so FIFO
  order guarantees this PE's slice is at the front — **G-2 FIFO peel** (`demux.csl:61-70`).
- Branches on `is_last_pe`: `→ send_out` if last, else `→ forward_and_out`.

**Phase 2 · forward + emit (P-5 store-and-forward + G-1 parity chain)**
- `forward_and_out` (`:127-134`, PE `k < P−1`) — two concurrent async ops: a second `@mov32` streams the
  remaining `FWD_EXTENT` wavelets straight `fabin → fabout` **south** on `forward_color`
  (`.unblock = next_cycle`), and another emits `own_buf` **east** on `out_color` (`.activate =
  next_cycle`). They join at the initially-`@block`ed `next_cycle` (`:157-160`).
- `send_out` (`:122-125`, PE `P−1`) — no south forward; emit `own_buf` east only.
- **Parity colors:** adjacent hops alternate `chain_color_a` (even hops) / `chain_color_b` (odd), so no
  two neighbouring routers paint the same color. Routes are `RAMP→SOUTH` on senders and `NORTH→RAMP` on
  receivers, assigned per row at `launch.py:773-797`; the last PE and PE 0 get stub `recv` paints so no
  color is left unpainted on a transited PE.

**Phase 3 · EAST emit into HT_head (P-6 p2p, per row)**
- `out_color` **is** `pre_embed_x_color` (**id 18**), painted `RAMP→EAST` on every demux PE
  (`launch.py:752, 799-801`) and connected demux-right → HT_head-left (`launch.py:2322`). Inside the
  band it runs east along row `py` and terminates `WEST→RAMP` at that row's **diag column**
  (`ht_head.csl:264-268`), where the diag PE drains it as its step-0 `embed_buf`. Note the asymmetry
  with prefill: there the demux's south emit is picked up by a **multicast**; here it is a plain
  point-to-point run that dies at one PE per row.

**Phase 4 · `next_cycle` — per-round re-arm (`:136-144`)**
- With `kv_stream_ingress != 0` (i.e. `KV_TRANSFER=1`): re-`@block(next_cycle_id)` so the next
  `forward_and_out`'s `.unblock` has something to clear, then `@activate(main_id)` to re-park on
  `src_q` for the next round's `X[0]`. The one-time ready barrier is **not** repeated.
- With `KV_TRANSFER=0`: single-shot, the PE simply goes idle for the rest of the run.

## Communication summary

| Movement | color / queue | direction | pattern | task(s) |
|---|---|---|---|---|
| ready barrier (1 u32) | `ht_ready_color`(0) / `ready_iq`=iq3 | WEST ← HT_head col 0 | **1-wavelet barrier / first-paint fence** | `init` (`:104-107`) |
| host `X[0]` stream in | `in_color` / `src_q`=iq2 | host → PE 0, `Edge.TOP` | **P-5 store-and-forward head** | `main` (`:109-120`) |
| forward remainder south | `chain_color_a`·`chain_color_b` / `forward_oq`=oq2 | Y south, 1 hop | **G-1 parity chain + G-2 FIFO peel** | `forward_and_out` (`:130-131`) |
| emit own slice east | `out_color` = `pre_embed_x_color`(18) / `out_oq`=oq3 | EAST into HT_head row `py` | **P-6 p2p**, terminating at the row's diag col | `forward_and_out` / `send_out` (`:123, 132`) |

Correctness = **count-exactness**: each PE derives `OWN_B` and `FWD_EXTENT` from its own `my_idx` and
`P_BLOCK_SIZE`, and the host sends exactly `P_BLOCK_SIZE · OWN_B` u32 per round. Any disagreement
between what a PE peels+forwards and what its neighbour expects is a **silent hang**. The same applies
to the east side: `OWN_B` u32 = `bsz·dim_per_pe` fp16 must equal what the diag PE's
`pre_embed_x_recv_dsd` drains (`ht_head.csl:94`).

## One line

Same program on every row; `my_idx` gives each PE a different peel offset and `FWD_EXTENT`. A keyed
host→row scatter becomes a column of peel-forward-drop hops on two parity colors — prefill's demux
turned on its side, carrying a host-embedded `X[0]` seed once per round instead of token ids every chunk.
